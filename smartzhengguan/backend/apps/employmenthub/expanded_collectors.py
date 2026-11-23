"""Adapters for anonymous public recruitment queries used by the source websites."""
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from django.utils import timezone
from .collectors import (CollectionError, PublicHTML, clean, canonical_url, parse_iso_date,
    extract_registration, match_majors, employer_type, attachments_from, upsert_opportunity,
    touch, DATE_ZONE)
from .models import PROVINCES, EmploymentSource
from .serializers import public_url

COMPANY_KEYWORDS = ('阿里', '腾讯', '字节', '美团', '京东', '百度', '快手', '小米', '小红书', '携程', '华为', '哔哩哔哩')
STATE_KEYWORDS = ('国家电网', '中国石油', '中国石化', '华润', '中国建筑', '中国中铁', '中国移动', '中国联通', '中国电信', '国投', '中粮', '国家能源')
BRANDS = ('腾讯音乐', '阿里国际', '阿里巴巴', '阿里云', '字节跳动', '腾讯', '美团', '京东方', '京东', '百度', '网易', '快手', '小米', '小红书', '携程', '华为', '哔哩哔哩', 'Shopee')


def company_group(text):
    return next((name for name in BRANDS if name.casefold() in text.casefold()), '')


def track_of(row):
    if row.employer_type in {'央企', '国企'}:
        return 'state'
    if row.metadata.get('companyGroup') or company_group(row.title + ' ' + row.employer):
        return 'internet'
    return 'other'


def class_node(root, name):
    return next((n for n in root.all() if name in n.attrs.get('class', '').split()), None)


def region_values(text):
    cities = {'杭州': '浙江', '宁波': '浙江', '广州': '广东', '深圳': '广东', '成都': '四川',
              '武汉': '湖北', '南京': '江苏', '苏州': '江苏', '西安': '陕西', '厦门': '福建',
              '济南': '山东', '青岛': '山东', '长沙': '湖南', '大连': '辽宁'}
    regions = set(p for p in PROVINCES if p not in {'全国', '境外', '港澳台'} and p in text)
    regions.update(p for city, p in cities.items() if city in text)
    return sorted(regions)


def base_payload(source, url, title, employer='', body='', locations='', published=None, kind='announcement'):
    related, match_kind, reasons = match_majors(body)
    regions = region_values(locations)
    start, end = extract_registration(body)
    group = company_group(title + ' ' + employer)
    return {'source': source, 'canonical_url': canonical_url(public_url(url)), 'title': title[:300],
        'category': '企业招聘', 'employer': employer[:200], 'employer_type': employer_type(body, '企业招聘'),
        'province': regions[0] if len(regions) == 1 else '全国', 'published_at': published,
        'registration_start': start, 'registration_end': end, 'exam_at': None,
        'summary': body[:650], 'requirements': body[:18000], 'related_majors': related,
        'match_kind': match_kind, 'match_reasons': reasons, 'attachments': [], 'review_state': '待核对',
        'metadata': {'entryType': kind, 'companyGroup': group, 'locations': regions, 'locationText': locations.strip()[:300]}}


def parse_netease(row, project, source):
    if not row.get('id') or not row.get('positionName'):
        raise CollectionError('网易职位缺少编号或名称')
    url = 'https://campus.163.com/app/detail/index?' + urlencode({'id': row['id'], 'projectId': project['id']})
    description = row.get('positionDescription') or ''
    requirements = row.get('positionRequirement') or ''
    body = '岗位职责：\n' + description + '\n任职要求：\n' + requirements
    payload = base_payload(source, url, '网易 · ' + row['positionName'], '网易', body,
        row.get('workPlaceName') or '', kind='position')
    payload['employer_type'] = '民企'
    payload['summary'] = description[:650]
    payload['metadata'].update({'project': project['title'], 'positionCategory': row.get('positionTypeName', ''),
        'sourceRecordId': str(row['id']), 'companyGroup': '网易'})
    if row.get('updateTime'):
        try:
            payload['metadata']['sourceUpdatedAt'] = datetime.fromtimestamp(int(row['updateTime'])/1000, DATE_ZONE).isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            pass
    # updateTime is not the original publication date.
    return payload


def netease_payloads(source, fetcher):
    nav = fetcher.get_json('https://campus.163.com/api/campuspc/project/navigation/list')
    if nav.get('code') != 200 or not isinstance(nav.get('data'), list):
        raise CollectionError('网易公开招聘导航结构变化')
    projects, seen = [], set()
    def visit(nodes):
        for item in nodes:
            parts = urlsplit(item.get('link') or '')
            pid = parse_qs(parts.query).get('id', [''])[0]
            if parts.hostname == 'campus.163.com' and parts.path == '/app/job/position' and pid.isdigit() and pid not in seen:
                seen.add(pid); projects.append({'id': pid, 'title': item.get('title', '校园招聘')})
            visit(item.get('children') or [])
    visit(nav['data'])
    if not projects:
        raise CollectionError('当前未发现本站公开的校招职位批次')
    for project in projects[:3]:
        for page in range(1, 7):
            url = 'https://campus.163.com/api/campuspc/position/getJobList?' + urlencode({'projectId': project['id'], 'currentPage': page, 'pageSize': 20})
            response = fetcher.get_json(url)
            if response.get('code') != 200 or not isinstance(response.get('data'), dict):
                raise CollectionError('网易公开职位查询未成功')
            data = response['data']; rows = data.get('list')
            if not isinstance(rows, list):
                raise CollectionError('网易职位列表格式变化')
            for row in rows:
                yield parse_netease(row, project, source)
            if data.get('lastPage') or not rows or page * 20 >= int(data.get('total', 0)):
                break


def company_natures(fetcher):
    catalog = []
    for page in range(1, 4):
        data = fetcher.get_json('https://gp-api.iguopin.com/api/activity/activity/v1/company',
            {'alias': 'gpxd3s', 'is_online_jobs': True, 'page_size': 50, 'page': page})
        if data.get('code') != 200 or not isinstance(data.get('data'), dict):
            raise CollectionError('国聘公开企业名录未成功返回')
        rows = data['data'].get('list', [])
        for row in rows:
            nature = '央企' if '央企' in row.get('classify_cn', '') else '国企' if '国企' in row.get('nature_cn', '') else '未说明'
            names = {row.get('name', ''), row.get('short_name', '')}
            names.add(re.sub(r'(?:集团)?(?:股份)?有限公司$', '', row.get('name', '')))
            catalog.extend((name, row.get('name', ''), nature) for name in names if len(name) >= 4)
        if not rows or page * 50 >= int(data['data'].get('total', 0)):
            break
    return sorted(catalog, key=lambda item: len(item[0]), reverse=True)


def parse_guopin(row, source, catalog):
    title = clean(row.get('title') or '')
    url = row.get('link_url') or ''
    if not title or not url or not re.search(r'招聘|校招|招募|岗位|诚邀加盟', title) or re.search(r'精彩回顾|就业指导专场预告|^中国气象局', title):
        return None
    body = clean(PublicHTML(row.get('content') or '').root.text())
    employer, nature = '', '未说明'
    for name, full_name, value in catalog:
        if name in title:
            employer, nature = full_name, value
            break
    payload = base_payload(source, url, title, employer, body, published=parse_iso_date(row.get('create_time') or ''),
        kind='announcement' if len(body) >= 50 else 'announcement_index')
    payload['employer_type'] = nature
    if employer:
        payload['metadata']['recruitingGroup'] = employer
        title_unit = re.search(r'([\u4e00-\u9fff]+(?:有限公司|有限责任公司))', title)
        if title_unit:
            payload['employer'] = title_unit.group(1)
    payload['metadata']['sourceRecordId'] = str(row['id'])
    if nature != '未说明':
        payload['metadata']['employerTypeEvidence'] = '国聘行动公开企业名录的单位性质 / 央企分类'
    if not body:
        payload['summary'] = '国聘行动发布的招聘公告。岗位、专业条件、报名时间和投递方式请打开公告原文查看。'
        payload['match_reasons'] = ['当前取得公告索引及原文链接，尚未取得完整岗位条件；不推测专业资格。']
    return payload


def guopin_payloads(source, fetcher):
    catalog = company_natures(fetcher)
    source.metadata = {**source.metadata, 'companyCatalog': catalog}
    source.save(update_fields=['metadata'])
    for page in range(1, 4):
        data = fetcher.get_json('https://api4.iguopin.com/api/notice/list?' + urlencode({'type': 'gpxd', 'per_page': 20, 'page': page}))
        if data.get('code') != 1 or not isinstance(data.get('data'), dict):
            raise CollectionError('国聘招聘公告公开列表未成功返回')
        rows = data['data'].get('data')
        if not isinstance(rows, list):
            raise CollectionError('国聘招聘公告列表结构变化')
        for row in rows:
            payload = parse_guopin(row, source, catalog)
            if payload:
                yield payload
        if not rows:
            break


def nankai_links(content):
    root = PublicHTML(content).root
    result, seen = [], set()
    for anchor in root.all('a'):
        href = anchor.attrs.get('href', '')
        if re.fullmatch(r'/correcruit/content/id/\d+\.html', href) and href not in seen:
            title = clean(anchor.text())
            if title:
                seen.add(href); result.append({'url': urljoin('https://career.nankai.edu.cn', href), 'title': title})
    return result


def parse_nankai(content, listing, source, catalog=()):
    root = PublicHTML(content).root
    top, body = class_node(root, 'top'), class_node(root, 'zpnr')
    if not top or not body:
        raise CollectionError('未识别到南开公开招聘正文')
    title_node = class_node(top, 'title1')
    company = class_node(top, 'company')
    date_node = class_node(top, 'date')
    fields = [clean(n.text()) for n in top.all() if 'zpxx' in n.attrs.get('class', '').split()]
    locations = next((s.split('：', 1)[-1] for s in fields if s.startswith('工作地域')), '')
    apply_url = next((s.split('：', 1)[-1].strip() for s in fields if s.startswith('职位投递网址链接')), '')
    text = '\n'.join(fields) + '\n' + clean(body.text())
    title = clean(title_node.text()) if title_node else listing['title']
    publisher = clean(company.text()) if company else ''
    employer = company_group(title) if '代发' in publisher else publisher
    payload = base_payload(source, listing['url'], title, employer, text, locations,
        parse_iso_date(clean(date_node.text())) if date_node else None)
    payload['metadata']['publisherName'] = publisher
    for name, full_name, nature in catalog:
        if nature in {'央企', '国企'} and (name in employer or name in title):
            payload['employer_type'] = nature
            payload['metadata']['recruitingGroup'] = full_name
            payload['metadata']['employerTypeEvidence'] = '国聘公开企业名录与公告单位名称匹配'
            break
    payload['summary'] = clean(body.text())[:650]
    payload['attachments'] = attachments_from(body, listing['url'])
    if apply_url:
        try:
            payload['metadata']['applyUrl'] = public_url(apply_url)
        except Exception:
            pass
    return payload


def nankai_payloads(source, fetcher):
    # Round-robin company search results prevents one employer consuming the whole budget.
    groups = []
    keywords = STATE_KEYWORDS if source.key == 'nankai-state-owned' else COMPANY_KEYWORDS
    registry = EmploymentSource.objects.filter(key='iguopin-jobs').first()
    catalog = registry.metadata.get('companyCatalog', []) if registry else []
    for keyword in keywords:
        try:
            html = fetcher.post_form(source.url, {'type': '0', 'keywords': keyword})
            groups.append(nankai_links(html)[:4])
        except Exception as error:
            yield CollectionError(keyword + '公开查询失败：' + str(error)[:180])
    seen = set()
    cutoff = timezone.localdate() - timedelta(days=180)
    for index in range(4):
        for group in groups:
            if index >= len(group):
                continue
            listing = group[index]
            if listing['url'] in seen:
                continue
            seen.add(listing['url'])
            try:
                payload = parse_nankai(fetcher.get(listing['url']), listing, source, catalog)
                if payload['published_at'] and payload['published_at'] < cutoff:
                    continue
                yield payload
            except Exception as error:
                yield CollectionError(listing['title'][:50] + '：' + str(error)[:180])


def collect_expanded(source, run, fetcher):
    adapters = {'netease_campus': netease_payloads, 'guopin_public': guopin_payloads, 'nankai_company': nankai_payloads}
    counts = {'created': 0, 'updated': 0, 'checked': 0}
    errors, titles, seen = [], [], set()
    try:
        for payload in adapters[source.adapter](source, fetcher):
            touch(run.pk)
            if isinstance(payload, Exception):
                errors.append(str(payload)); continue
            if payload['canonical_url'] in seen:
                continue
            seen.add(payload['canonical_url'])
            try:
                result = upsert_opportunity(payload)
                counts['checked'] += 1
                if result != 'unchanged':
                    counts[result] += 1
                if len(titles) < 5:
                    titles.append(payload['title'])
            except Exception as error:
                errors.append(payload['title'][:50] + '：' + str(error)[:180])
    except Exception as error:
        errors.append(str(error)[:250])
    if not counts['checked']:
        raise CollectionError('未取得可入库的公开招聘记录；' + '；'.join(errors[:2]))
    source.last_success = timezone.now()
    source.status = 'partial' if errors else 'success'
    source.last_error = '；'.join(errors[:5])
    source.metadata = {**source.metadata, 'lastResult': counts, 'lastFetchedTitles': titles,
        'requestCount': fetcher.requests, 'detailErrors': len(errors)}
    source.save(update_fields=['last_success', 'status', 'last_error', 'metadata'])
    return counts, errors
