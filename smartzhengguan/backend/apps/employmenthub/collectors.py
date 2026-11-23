"""Bounded public-HTML collection. No student data, cookies, private APIs or LLM calls."""
import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, time as day_time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.graduate.constants import REAL_MAJORS
from .catalog import ADAPTER_HOSTS
from .models import EmploymentSource, Opportunity, PROVINCES, SchedulerState, SyncRun

USER_AGENT = "SmartZhengguanEmployment/1.0 (+public educational recruitment information)"
MAX_BYTES = 2_000_000
MAX_REQUESTS = 75
DATE_ZONE = ZoneInfo("Asia/Shanghai")


class CollectionError(ValueError):
    pass


class Element:
    def __init__(self, tag="root", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def all(self, tag=None):
        for child in self.children:
            if isinstance(child, Element):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.all(tag)

    def text(self):
        if self.tag in {"script", "style", "noscript"}:
            return ""
        return " ".join(child.text() if isinstance(child, Element) else child for child in self.children)


class PublicHTML(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.stack = [self.root]
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Element(tag, attrs))

    def handle_endtag(self, tag):
        for pos in range(len(self.stack) - 1, 0, -1):
            if self.stack[pos].tag == tag:
                self.stack = self.stack[:pos]
                break

    def handle_data(self, content):
        self.stack[-1].children.append(content)


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "www.job.sdu.edu.cn":
        host = "job.sdu.edu.cn"
    port = parts.port
    netloc = host + (f":{port}" if port and port not in {80, 443} else "")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not k.lower().startswith("utm_") and k.lower() not in {"eqid", "spm"}))
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", query, ""))


def validate_fetch_url(url, allowed_hosts, resolve=True):
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or parts.username or parts.password:
        raise CollectionError("仅允许无凭据的公开 HTTP(S) 地址")
    host = (parts.hostname or "").lower()
    if host not in allowed_hosts or parts.port not in {None, 80, 443}:
        raise CollectionError("来源域名或端口未列入采集白名单")
    if resolve:
        addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(record[4][0]).is_global for record in addresses):
            raise CollectionError("不允许访问本机、内网或保留网络地址")
    return url


class CheckedRedirect(HTTPRedirectHandler):
    def __init__(self, allowed_hosts, check_redirect=None):
        self.allowed_hosts = allowed_hosts
        self.check_redirect = check_redirect

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_fetch_url(newurl, self.allowed_hosts)
        if self.check_redirect:
            self.check_redirect(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicFetcher:
    def __init__(self, allowed_hosts, heartbeat=None):
        self.allowed_hosts = allowed_hosts
        self.robots = {}
        self.opener = build_opener(CheckedRedirect(allowed_hosts, self._check_redirect))
        self.last_request = {}
        self.requests = 0
        self.heartbeat = heartbeat or (lambda: None)

    def _check_redirect(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if parts.path == "/robots.txt":
            # A robots redirect is not evidence that another path may be collected.
            raise CollectionError("robots.txt 发生跳转，需先单独核验来源规则")
        parser = self.robots.get(origin)
        if parser is None or not parser.can_fetch(USER_AGENT, url):
            raise CollectionError("跳转目标的 robots 规则尚未允许采集")

    def _read(self, url, delay=2, *, data=None, content_type=None, json_response=False):
        validate_fetch_url(url, self.allowed_hosts)
        if self.requests >= MAX_REQUESTS:
            raise CollectionError("已到达本轮请求上限，保留已同步记录")
        host = urlsplit(url).hostname
        pause = delay - (time.monotonic() - self.last_request.get(host, 0))
        if pause > 0:
            time.sleep(pause)
        self.heartbeat()
        self.requests += 1
        self.last_request[host] = time.monotonic()
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json" if json_response else "text/html,text/plain;q=0.9", "Accept-Encoding": "identity"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(url, data=data, headers=headers)
        with self.opener.open(request, timeout=12) as response:
            validate_fetch_url(response.url, self.allowed_hosts)
            allowed_types = {"application/json", "text/json", "text/plain"} if json_response else {"text/html", "text/plain", "application/xhtml+xml"}
            if response.headers.get_content_type() not in allowed_types:
                raise CollectionError("来源不是可读取的公开文本页面")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise CollectionError("来源页面超过 2MB 限制")
            charset = response.headers.get_content_charset()
            if not charset:
                match = re.search(br"charset\s*=\s*[\"']?([\w-]+)", body[:4000], re.I)
                charset = match.group(1).decode("ascii") if match else "utf-8"
            try:
                return body.decode(charset, errors="replace")
            except LookupError:
                return body.decode("utf-8", errors="replace")

    def get(self, url, *, data=None, content_type=None, json_response=False):
        validate_fetch_url(url, self.allowed_hosts)
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            parser = RobotFileParser(origin + "/robots.txt")
            try:
                parser.parse(self._read(origin + "/robots.txt").splitlines())
            except HTTPError as error:
                if error.code not in {404, 410}:
                    raise CollectionError(f"robots 访问失败 HTTP {error.code}，未继续采集") from error
                parser.parse([])
            self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(USER_AGENT, url):
            raise CollectionError("robots.txt 禁止此路径采集")
        delay = max(2, parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 0)
        rate = parser.request_rate(USER_AGENT) or parser.request_rate("*")
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        if data is None and not json_response:
            return self._read(url, delay=delay)
        return self._read(url, delay=delay, data=data, content_type=content_type, json_response=json_response)

    def get_json(self, url, payload=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        raw = self.get(url, data=data, content_type="application/json" if data else None, json_response=True)
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as error:
            raise CollectionError("公开列表未返回有效 JSON，停止本来源") from error

    def post_form(self, url, payload):
        return self.get(url, data=urlencode(payload).encode(), content_type="application/x-www-form-urlencoded")


def parse_iso_date(value):
    match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", value)
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def at_day_end(value):
    return datetime.combine(value, day_time(23, 59, 59), DATE_ZONE) if value else None


def infer_province(title, fallback="全国"):
    # The audience's university is not the recruiting province.
    title = title.replace("山东大学", "").replace("北京大学", "").replace("上海交通大学", "")
    matches = [province for province in PROVINCES if province not in {"全国", "港澳台", "境外"} and province in title]
    return matches[0] if len(matches) == 1 else fallback


def classify_category(title, listed_kind="", fallback="企业招聘"):
    if "公开遴选" in title or ("公开选调" in title and "毕业生" not in title and "选调生" not in title):
        return None  # In-service recruitment is not graduate selection.
    if "选调" in title:
        return "选调生"
    if any(word in title for word in ["引进人才", "人才引进", "引进高层次", "引进优秀人才", "引进急需"]):
        return "人才引进"
    if "公务员" in title:
        return "公务员"
    if "事业单位" in title or listed_kind == "事业单位":
        return "事业单位"
    return fallback


DIRECTION_WORDS = {
    "政治学理论": ("政策研究", "公共事务", "政治学", "综合文秘"),
    "科学社会主义与国际共产主义运动": ("马克思主义", "党务", "思想政治", "党建"),
    "中共党史": ("党史", "党务", "党建", "企业文化"),
    "行政管理": ("人力资源", "综合行政", "行政管理", "综合管理", "组织管理"),
    "国际政治": ("国际业务", "国际合作", "国际事务", "公共事务"),
    "国际关系": ("海外业务", "国际业务", "国际合作", "海外事务"),
    "统一战线学": ("统战", "公共事务", "社会工作"),
    "应急管理": ("应急", "风险管理", "安全管理", "业务连续性"),
}


def match_majors(text):
    explicit = [major for major in REAL_MAJORS if major in text]
    if explicit:
        return explicit, "明确提及", ["原文出现专业名称：" + "、".join(explicit), "公告可能包含多个职位，须按具体岗位核验专业及其他条件"]
    if re.search(r"不限专业|专业不限", text):
        return list(REAL_MAJORS), "不限专业", ["部分原文提及不限专业，须核对适用岗位、学历、届别及其他条件"]
    hits = {major: [word for word in words if word in text] for major, words in DIRECTION_WORDS.items()}
    related = [major for major in REAL_MAJORS if hits.get(major)]
    if related:
        words = list(dict.fromkeys(word for major in related for word in hits[major]))
        return related, "方向相关", ["方向关键词：" + "、".join(words), "方向相关不代表满足专业目录或报考资格，需查看具体岗位表"]
    return [], "待核实", ["正文未识别到本院明确专业条件，附件和岗位表需进一步核对"]


def employer_type(text, category):
    if category != "企业招聘":
        return "不适用"
    # Ownership labels must describe the employer, not its customers or partners.
    declarations = re.findall(r"单位性质\s*[:：]?\s*([^。；;]{1,45})", text)
    declarations += re.findall(r"(?:本公司|本集团|本企业|本单位|公司|集团|企业)(?:是|系|为|属于|性质为)\s*([^。；;]{1,70})", text)
    declarations += re.findall(r"作为([^。；;，,]{0,18}私立教育机构)", text)
    ownership = " ".join(declarations)
    ownership = re.sub(r"(?:央企|中央企业|国有企业|民营企业)(?:客户|合作伙伴)", "", ownership)
    if re.search(r"央企|中央企业|中央直属企业|中央管理.{0,6}企业|国务院国资委.{0,15}(?:企业|监管)|国资委央企", ownership):
        return "央企"
    if re.search(r"国有企业|国有独资|国有全资|国有控股|市属国企|省属国企", ownership):
        return "国企"
    if re.search(r"民营企业|民营公司|私营企业|私立教育机构", ownership):
        return "民企"
    return "未说明"


def refine_unit_category(listed_category, introduction):
    """The list's generic 'enterprise' label is weaker than explicit unit identity."""
    private_school = re.search(r"民办[^。；;]{0,12}(?:高校|院校|大学|学院)", introduction)
    if private_school:
        return listed_category, "民办高校；聘用形式、编制性质以原公告为准"
    institution = re.search(r"单位性质\s*[:：]?\s*(?:机关|事业单位)", introduction)
    public_school = re.search(r"(?:学校|大学|学院)(?:是|为|系)[^。；;]{0,35}(?:公立|公办)[^。；;]{0,25}(?:高校|院校|大学|学院)", introduction)
    if listed_category == "企业招聘" and (institution or public_school):
        return "事业单位", "公办高校或明确事业单位；具体岗位是否纳编以原公告为准"
    return listed_category, ""


def extract_registration(text):
    """Only use an explicit registration-time context, never publication or exam dates."""
    stamp = r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2})[：:时](?:(\d{1,2})分?)?)?"
    for cue in re.finditer(r"报名时间[：:]?|(?:网上|网络)报名[。：:]?|报名。|报名为", text):
        segment = text[cue.end():cue.end() + 180]
        segment = re.split(r"[。；;\n]|另行通知|待定|笔试|面试|缴费|资格审查|体检|公示|准考证", segment, maxsplit=1)[0]
        match = re.search(stamp + r"\s*(?:至|到|—|–|~|～|-)\s*" + stamp, segment)
        if not match or not match.group(1):
            continue
        values = match.groups()
        try:
            year, month, day, hour, minute = values[:5]
            end_year, end_month, end_day, end_hour, end_minute = values[5:]
            if hour is None or end_hour is None:
                continue  # A date is not a verified time; never manufacture countdowns.
            start = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=DATE_ZONE)
            end = datetime(int(end_year or year), int(end_month), int(end_day), int(end_hour or 23), int(end_minute or (59 if end_hour is None else 0)), 59 if end_hour is None else 0, tzinfo=DATE_ZONE)
            if end >= start:
                return start, end
        except ValueError:
            continue
    # Some notices state only an end time. Preserve it without inventing a start.
    compact = re.sub(r"\s+", "", text)
    deadline = re.compile(
        r"(?:报名截止(?:时间|日期)?|报名时间(?:截止(?:到|至)|自公告发布之日起至))[:：]?"
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日(上午|下午|晚上)?"
        r"(\d{1,2})[:：时](?:(\d{1,2})分?)?"
    )
    ends = set()
    for match in deadline.finditer(compact):
        year, month, day, period, hour, minute = match.groups()
        hour = int(hour)
        if period in ('下午', '晚上') and 1 <= hour < 12:
            hour += 12
        try:
            ends.add(datetime(int(year), int(month), int(day), hour, int(minute or 0), tzinfo=DATE_ZONE))
        except ValueError:
            continue
    return (None, next(iter(ends))) if len(ends) == 1 else (None, None)


def attachments_from(root, base):
    result, seen = [], set()
    for anchor in root.all("a"):
        href = urljoin(base, anchor.attrs.get("href", ""))
        parts = urlsplit(href)
        if parts.scheme not in {"http", "https"} or parts.username or parts.password:
            continue
        if re.search(r"\.(?:pdf|docx?|xlsx?|zip|rar)(?:$|\?)|/resdownload\?|/download/|/DownloadAttach", href, re.I):
            if href not in seen:
                seen.add(href)
                result.append({"name": clean(anchor.text())[:200] or "公告附件", "url": href})
    return result[:20]


def selection_links(content, base):
    root = PublicHTML(content).root
    result = []
    for row in root.all("li"):
        anchors = [a for a in row.all("a") if re.search(r"(?:info/1130/\d+\.htm|nry\.jsp\?.*wbtreeid=1130)", a.attrs.get("href", ""))]
        if not anchors:
            continue
        anchor = anchors[0]
        title = clean(anchor.attrs.get("title") or anchor.text())
        category = classify_category(title, fallback="选调生")
        if not category or not re.search(r"公告|简章|招聘", title):
            continue
        result.append({"title": title[:300], "url": urljoin(base, anchor.attrs["href"]), "published_at": parse_iso_date(row.text()), "category": category})
    next_link = next((urljoin(base, a.attrs.get("href", "")) for a in root.all("a") if clean(a.text()) == "下页"), None)
    return result, next_link


def recruitment_links(content, base):
    result = []
    for row in PublicHTML(content).root.all("li"):
        anchors = [a for a in row.all("a") if "viewZpxx(" in a.attrs.get("onclick", "")]
        if len(anchors) < 4:
            continue
        match = re.search(r"viewZpxx\('([A-Za-z0-9]+)',\s*'jygl_zpxxck'\)", anchors[0].attrs.get("onclick", ""))
        if not match:
            continue
        title = clean(anchors[1].text())
        category = classify_category(title, clean(anchors[2].text()))
        if not category:
            continue
        # This URL is the public page explicitly opened by the list's viewZpxx link.
        url = urljoin(base, "/eweb/jygl/index.so?") + urlencode({"modcode": "jygl_zpxxck", "subsyscode": "zpfw", "rklx": "jyw", "lmxhV": "0402", "type": "ssoZxzpView", "id": match.group(1)})
        result.append({"title": title[:300], "url": url, "published_at": parse_iso_date(anchors[0].text()), "deadline_date": parse_iso_date(anchors[3].text()), "category": category})
    return result


def parse_opportunity(content, listing, source):
    root = PublicHTML(content).root
    if source.adapter == "sdu_selection":
        candidates = [n for n in root.all() if n.attrs.get("class", "").startswith("v_news_content") or n.attrs.get("id", "").startswith("vsb_content")]
        body = max(candidates, key=lambda n: len(n.text()), default=None)
        if body is None or len(clean(body.text())) < 50:
            raise CollectionError("未找到公告正文，可能需登录或页面结构已变化")
        text = clean(body.text())
        summary = text[:700]
        matching = text
        introduction = ""
    else:
        title_nodes = [n for n in root.all("p") if n.attrs.get("class") == "ggName"]
        cells = [n for n in root.all("td") if n.attrs.get("id") == "tdnr"]
        if not title_nodes or len(cells) < 2:
            raise CollectionError("未找到公开招聘正文，可能需登录或页面结构已变化")
        body = next((n for n in root.all("div") if "moreNewListR" in n.attrs.get("class", "")), root)
        text = clean(body.text())
        summary = clean(cells[1].text())[:700]
        # Company introductions often mention all departments; do not use them to infer position fit.
        position_tables = [n for n in body.all("table") if n.attrs.get("id") == "tab"]
        matching = clean(cells[1].text()) + " " + " ".join(clean(n.text()) for n in position_tables)
        introduction = clean(cells[0].text())
    # Some school announcements leave the separate introduction cell empty and put
    # their identity in the recruitment body. Still require an explicit declaration.
    unit_identity = introduction
    if any(word in listing["title"] for word in ("大学", "学院")):
        unit_identity += " " + matching[:2500]
    category, unit_note = refine_unit_category(listing["category"], unit_identity)
    if unit_note:
        summary = f"【单位类型：{unit_note}】 " + summary
    related, kind, reasons = match_majors(matching)
    start, end = extract_registration(matching)
    listed_end = listing.get("deadline_date")
    if listed_end and not end:
        summary += f" 【校就业网标注截止日期 {listed_end.isoformat()}，具体时刻待核实。】"
    province = infer_province(listing["title"], source.province)
    if category == "企业招聘":
        location = re.search(r"(?:工作地点|工作所在地|所在地区)[：:】\s]+([^。；;]{2,45})", matching)
        if location:
            province = infer_province(location.group(1), province)
    employer = re.sub(r"招聘.*$", "", listing["title"]).strip() if category == "企业招聘" else ""
    return {
        "canonical_url": canonical_url(listing["url"]), "title": listing["title"], "source": source,
        "category": category, "employer_type": employer_type(text, category), "province": province,
        "employer": employer[:200], "published_at": listing.get("published_at"), "registration_start": start,
        "registration_end": end, "exam_at": None, "summary": summary[:1500], "requirements": matching[:18000],
        "related_majors": related, "match_kind": kind, "match_reasons": reasons,
        "attachments": attachments_from(body, listing["url"]), "review_state": "待核对",
    }


def upsert_opportunity(payload):
    """Keep corrections intact, flag changed source text for a teacher to recheck."""
    value = dict(payload)
    source = value.pop("source")
    canonical = value.pop("canonical_url")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    content_hash = hashlib.sha256(encoded.encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        item = Opportunity.objects.filter(canonical_url=canonical).first()
        if item is None:
            Opportunity.objects.create(source=source, canonical_url=canonical, content_hash=content_hash, last_seen=now, **value)
            return "created"
        if item.content_hash == content_hash:
            Opportunity.objects.filter(pk=item.pk).update(last_seen=now)
            return "unchanged"
        revisions = list(item.revisions or [])
        revisions.append({"at": now.isoformat(), "kind": "source_update", "previousHash": item.content_hash, "newHash": content_hash, "previousTitle": item.title, "previousDeadline": item.registration_end.isoformat() if item.registration_end else None})
        protected = item.review_state == "已核对" or any(
            revision.get("type") == "老师更正" or "sourceCandidate" in revision
            for revision in (item.revisions or []) if isinstance(revision, dict)
        )
        if protected:
            # Preserve teacher edits. Store a bounded candidate for manual reconciliation.
            revisions[-1]["note"] = "原文有更新，保留人工更正，请重新核对"
            revisions[-1]["sourceCandidate"] = {k: str(v) if isinstance(v, (date, datetime)) else v for k, v in value.items() if k in {"title", "summary", "registration_start", "registration_end", "requirements", "related_majors", "match_kind"}}
            item.review_state = "待核对"
            item.content_hash = content_hash
            item.last_seen = now
            item.revisions = revisions[-20:]
            item.save(update_fields=["review_state", "content_hash", "last_seen", "revisions", "updated_at"])
        else:
            for field, data in value.items():
                setattr(item, field, data)
            item.content_hash, item.last_seen, item.revisions = content_hash, now, revisions[-20:]
            item.save()
        return "updated"


def touch(run_id):
    now = timezone.now()
    SyncRun.objects.filter(pk=run_id).update(heartbeat_at=now)


def collect_source(source, run):
    allowed = ADAPTER_HOSTS.get(source.adapter)
    if not source.enabled or not allowed:
        raise CollectionError("来源尚未接入自动同步")
    source.last_checked = timezone.now()
    source.save(update_fields=["last_checked"])
    fetcher = PublicFetcher(allowed, heartbeat=lambda: touch(run.pk))
    if source.adapter in {"netease_campus", "guopin_public", "nankai_company"}:
        from .expanded_collectors import collect_expanded
        return collect_expanded(source, run, fetcher)
    listings, seen = [], set()
    page_url = source.url
    for _ in range(2 if source.adapter == "sdu_selection" else 1):
        content = fetcher.get(page_url)
        if source.adapter == "sdu_selection":
            page_items, next_url = selection_links(content, page_url)
        else:
            page_items, next_url = recruitment_links(content, page_url), None
        for item in page_items:
            canonical = canonical_url(item["url"])
            if canonical not in seen:
                seen.add(canonical)
                listings.append(item)
        if not next_url:
            break
        page_url = next_url
    if not listings:
        raise CollectionError("列表未识别到公开公告，未将空结果视为成功；历史信息已保留")
    counts = {"created": 0, "updated": 0, "checked": 0}
    errors = []
    for listing in listings[:30 if source.adapter == "sdu_selection" else 20]:
        touch(run.pk)
        try:
            detail = fetcher.get(listing["url"])
            result = upsert_opportunity(parse_opportunity(detail, listing, source))
            counts["checked"] += 1
            if result != "unchanged":
                counts[result] += 1
        except Exception as error:
            errors.append(f"{listing['title'][:50]}：{str(error)[:180]}")
        SyncRun.objects.filter(pk=run.pk).update(heartbeat_at=timezone.now())
    if counts["checked"] == 0:
        raise CollectionError("未成功读取公告正文；" + "；".join(errors[:2]))
    source.last_success = timezone.now()
    source.status = "partial" if errors else "success"
    source.last_error = "；".join(errors[:5])
    source.metadata = {**source.metadata, "lastResult": counts, "lastFetchedTitles": [item["title"] for item in listings[:5]], "requestCount": fetcher.requests, "detailErrors": len(errors), "detailLimit": 30 if source.adapter == "sdu_selection" else 20}
    source.save(update_fields=["last_success", "status", "last_error", "metadata"])
    return counts, errors


def lock_path(name):
    root = Path(settings.BASE_DIR) / "tmp" / "employmenthub"
    root.mkdir(parents=True, exist_ok=True)
    return root / (name + ".lock")


@contextmanager
def process_lock(name, stale_seconds=900):
    """An OS lease, automatically released on process exit; never expires mid-sync."""
    path = lock_path(name)
    stream = path.open("a+b")
    if path.stat().st_size == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    locked = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (OSError, BlockingIOError) as error:
            raise CollectionError("已有同步或调度进程运行，请稍后重试") from error
        yield path
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def execute_run(run):
    close_old_connections()
    run.status, run.started_at, run.heartbeat_at = "running", timezone.now(), timezone.now()
    run.save(update_fields=["status", "started_at", "heartbeat_at"])
    sources = EmploymentSource.objects.filter(enabled=True)
    if run.source_id:
        sources = sources.filter(pk=run.source_id)
    failures, results = [], []
    try:
        # Refresh the public ownership registry before consuming school announcements.
        for source in sorted(sources, key=lambda item: item.adapter != "guopin_public"):
            try:
                counts, errors = collect_source(source, run)
                run.created_count += counts["created"]
                run.updated_count += counts["updated"]
                run.checked_count += counts["checked"]
                results.append({"sourceId": source.pk, "name": source.name, **counts})
                if errors:
                    failures.append(source.name + "：部分正文未读取，详见来源状态")
            except Exception as error:
                source.status, source.last_error, source.last_checked = "error", str(error)[:1500], timezone.now()
                source.save(update_fields=["status", "last_error", "last_checked"])
                failures.append(source.name + "：" + str(error)[:300])
            run.heartbeat_at = timezone.now()
            run.metadata = {**run.metadata, "sources": results}
            run.save(update_fields=["created_count", "updated_count", "checked_count", "heartbeat_at", "metadata"])
        run.status = ("partial" if results else "failed") if failures else "success"
        if not results and not failures:
            run.status, failures = "failed", ["没有已启用的自动同步来源，请先执行来源初始化"]
        run.error = "；".join(failures)[:3000]
    except Exception as error:
        run.status, run.error = "failed", str(error)[:3000]
    finally:
        run.finished_at = run.heartbeat_at = timezone.now()
        run.save()
        close_old_connections()
    return run


def run_sync(source_id=None, requested_by=None):
    with process_lock("sync"):
        if source_id and not EmploymentSource.objects.filter(pk=source_id, enabled=True).exists():
            raise CollectionError("来源不存在或尚未接入自动同步")
        run = SyncRun.objects.create(source_id=source_id, status="queued", heartbeat_at=timezone.now(), metadata={"requestedBy": getattr(requested_by, "pk", None)})
        return execute_run(run)


def queue_sync(source_id=None, requested_by=None):
    """The lock is acquired before returning 202, including across web processes."""
    if source_id and not EmploymentSource.objects.filter(pk=source_id, enabled=True).exists():
        raise CollectionError("来源不存在或尚未接入自动同步")
    guard = process_lock("sync")
    guard.__enter__()
    try:
        run = SyncRun.objects.create(source_id=source_id, status="queued", heartbeat_at=timezone.now(), metadata={"requestedBy": getattr(requested_by, "pk", None)})

        def worker():
            try:
                execute_run(run)
            finally:
                guard.__exit__(None, None, None)

        thread = threading.Thread(target=worker, name="employment-public-sync", daemon=True)
        thread.start()
        return run
    except Exception:
        guard.__exit__(None, None, None)
        raise


def watch_sources(interval=43200):
    interval = max(600, int(interval))
    with process_lock("scheduler", stale_seconds=120) as path:
        state, _ = SchedulerState.objects.get_or_create(key="default")
        state.status, state.pid, state.interval_seconds, state.stop_requested = "running", os.getpid(), interval, False
        state.heartbeat_at = timezone.now()
        state.save()
        stop = threading.Event()

        def heartbeat():
            close_old_connections()
            try:
                while not stop.wait(10):
                    if SchedulerState.objects.filter(key="default", stop_requested=True).exists():
                        stop.set()
                        break
                    SchedulerState.objects.filter(key="default").update(heartbeat_at=timezone.now())
                    path.touch()
            finally:
                close_old_connections()

        pulse = threading.Thread(target=heartbeat, name="employment-scheduler-heartbeat", daemon=True)
        pulse.start()
        try:
            while not stop.is_set():
                try:
                    run_sync()
                except CollectionError:
                    pass  # A manual sync already owns the same lease.
                if stop.wait(interval):
                    break
        finally:
            stop.set()
            pulse.join(timeout=12)
            SchedulerState.objects.filter(key="default", pid=os.getpid()).update(status="idle", heartbeat_at=timezone.now(), stop_requested=False)


def stop_watcher():
    return SchedulerState.objects.filter(key="default", status="running").update(stop_requested=True)
