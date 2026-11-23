import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .catalog import seed_sources
from .collectors import (
    CollectionError, PublicFetcher, canonical_url, classify_category, collect_source,
    employer_type, execute_run, extract_registration, infer_province, match_majors, parse_opportunity,
    process_lock, recruitment_links, refine_unit_category, selection_links, upsert_opportunity, validate_fetch_url,
)
from .models import EmploymentSource, Opportunity, SyncRun


SELECTION_LIST = '''<ul><li><span>2026-11-17</span><a title="福建省2027年度选调生公告" href="info/1130/34074.htm">福建省2027年度选调生公告</a></li>
<li><span>2026-11-16</span><a href="info/1130/34073.htm">关于查询选调生笔试成绩的通知</a></li>
<li><span>2026-11-16</span><a href="info/1130/34072.htm">中央机关公开遴选和公开选调公务员公告</a></li></ul><a href="xdgk/11.htm">下页</a>'''

SELECTION_BODY = '''<html><h3>福建省2027年度选调生公告</h3><div class="v_news_content">
<p>现面向应届优秀大学毕业生开展选调工作，政治学理论、国际关系等专业以岗位表为准。</p>
<p>报名时间：2026年11月18日8:30至11月30日18:00。具体条件及职位详见附件，须参加资格审核。</p>
<a href="/files/position.xlsx">职位表</a><a href="javascript:bad()">坏链接</a>
</div></html>'''

CAREER_LIST = '''<li><div><a onclick="viewZpxx('Abc123', 'jygl_zpxxck')">2026-11-21</a></div>
<div><a onclick="viewZpxx('Abc123', 'jygl_zpxxck')">某公司招聘</a></div>
<div><a onclick="viewZpxx('Abc123', 'jygl_zpxxck')">企业</a></div>
<div><a onclick="viewZpxx('Abc123', 'jygl_zpxxck')">2026-12-31</a></div></li>'''

CAREER_BODY = '''<div class="moreNewListR"><p class="ggName">某公司招聘</p>
<table><tr><td id="tdnr">公司是民营企业，公司介绍含应急管理和国际关系。</td></tr>
<tr><td id="tdnr">综合行政岗位，本科及以上，人力资源方向优先。工作地点：山东省济南市。</td></tr></table>
<table id="tab"><tr><td>职位名称</td><td>行政助理</td></tr></table></div>'''


class ParserTests(SimpleTestCase):
    def test_selection_filters_in_service_and_score_notices(self):
        items, next_page = selection_links(SELECTION_LIST, "https://job.sdu.edu.cn/xdgk.htm")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_at"].isoformat(), "2026-11-17")
        self.assertEqual(next_page, "https://job.sdu.edu.cn/xdgk/11.htm")
        self.assertIsNone(classify_category("中央机关公开遴选和公开选调公务员公告"))

    def test_province_does_not_confuse_audience_university_with_location(self):
        for province in ["云南", "湖北", "安徽", "四川"]:
            self.assertEqual(infer_province(f"{province}省2027年面向山东大学选调优秀毕业生公告"), province)
        self.assertEqual(infer_province("四川省宜宾市2026年下半年引进人才公告"), "四川")

    def test_career_public_link_and_date(self):
        items = recruitment_links(CAREER_LIST, "https://jobcareer.sdu.edu.cn/eweb/jygl/index.so?a=1")
        self.assertEqual(len(items), 1)
        self.assertIn("type=ssoZxzpView", items[0]["url"])
        self.assertIn("id=Abc123", items[0]["url"])
        self.assertEqual(items[0]["deadline_date"].isoformat(), "2026-12-31")

    def test_explicit_profession_and_attachment_preserved(self):
        source = EmploymentSource(adapter="sdu_selection", province="全国")
        listing = selection_links(SELECTION_LIST, "https://job.sdu.edu.cn/xdgk.htm")[0][0]
        item = parse_opportunity(SELECTION_BODY, listing, source)
        self.assertEqual(item["match_kind"], "明确提及")
        self.assertEqual(item["related_majors"], ["政治学理论", "国际关系"])
        self.assertEqual(item["province"], "福建")
        self.assertEqual(item["registration_end"].isoformat(), "2026-11-30T18:00:00+08:00")
        self.assertEqual(item["attachments"], [{"name": "职位表", "url": "https://job.sdu.edu.cn/files/position.xlsx"}])
        self.assertEqual(item["review_state"], "待核对")

    def test_company_intro_is_not_used_for_profession_matching(self):
        source = EmploymentSource(adapter="sdu_recruitment", province="全国")
        listing = recruitment_links(CAREER_LIST, "https://jobcareer.sdu.edu.cn/index.so")[0]
        item = parse_opportunity(CAREER_BODY, listing, source)
        self.assertEqual(item["related_majors"], ["行政管理"])
        self.assertEqual(item["match_kind"], "方向相关")
        self.assertEqual(item["employer_type"], "民企")
        self.assertEqual(item["province"], "山东")
        self.assertIn("不代表", item["match_reasons"][1])
        self.assertIsNone(item["registration_end"])
        self.assertIn("具体时刻待核实", item["summary"])

    def test_public_school_overrides_generic_enterprise_label_without_promising_establishment(self):
        category, note = refine_unit_category("企业招聘", "山东医药大学是省属公立全日制普通本科高校。")
        self.assertEqual(category, "事业单位")
        self.assertIn("是否纳编以原公告为准", note)
        category, note = refine_unit_category("企业招聘", "仰恩大学是全日制民办普通高校。")
        self.assertEqual(category, "企业招聘")
        self.assertIn("民办高校", note)
        self.assertEqual(refine_unit_category("企业招聘", "某某大学招聘，欢迎投递"), ("企业招聘", ""))
        source = EmploymentSource(adapter="sdu_recruitment", province="全国")
        listing = recruitment_links(CAREER_LIST, "https://jobcareer.sdu.edu.cn/index.so")[0]
        listing["title"] = "山东医药大学2026年公开招聘中高级人员公告"
        body = '<div class="moreNewListR"><p class="ggName">高校招聘</p><td id="tdnr"></td><td id="tdnr">山东医药大学是省属公立全日制普通本科高校。招聘博士研究生。</td></div>'
        item = parse_opportunity(body, listing, source)
        self.assertEqual(item["category"], "事业单位")
        self.assertEqual(item["employer_type"], "不适用")

    def test_no_inferred_dates_or_ownership_from_company_name(self):
        self.assertEqual(extract_registration("发布日期2026年11月10日，考试日期2026年12月1日"), (None, None))
        self.assertEqual(employer_type("中国某某有限公司", "企业招聘"), "未说明")
        self.assertEqual(employer_type("为央企客户提供服务，为民营企业提供咨询", "企业招聘"), "未说明")
        self.assertEqual(employer_type("本公司为央企客户提供专业服务", "企业招聘"), "未说明")
        self.assertEqual(employer_type("单位性质：企业 .国有企业 .国资委央企", "企业招聘"), "央企")
        self.assertEqual(extract_registration("报名时间：2026年11月1日至11月30日"), (None, None))
        self.assertEqual(extract_registration("报名时间另行通知。笔试时间2026年11月1日9时至2026年11月2日18时。"), (None, None))
        self.assertEqual(extract_registration("报名时间见附件。面试2026年11月1日9时至2026年11月2日18时。"), (None, None))
        self.assertEqual(extract_registration("报名时间待定；公示2026年11月1日9时至2026年11月2日18时。"), (None, None))
        self.assertEqual(match_majors("计算机科学与技术专业")[1], "待核实")
        self.assertEqual(match_majors("部分岗位专业不限")[1], "不限专业")

    def test_network_registration_does_not_use_later_qualification_deadline(self):
        text = "（二）网络报名 2026年11月9日9:00—11月13日18:00，考生进行网络报名并选择笔试地点。（三）资格审查 资格审查时间为2026年11月9日9:00—11月14日18:00"
        start, end = extract_registration(text)
        self.assertEqual(start.isoformat(), "2026-11-09T09:00:00+08:00")
        self.assertEqual(end.isoformat(), "2026-11-13T18:00:00+08:00")

    def test_precise_deadline_only_does_not_invent_start(self):
        for text in [
            '报名时间自公告发布之日起至2026年11月30日17:00。',
            '报名截止时间： 2026年11月30日下午17时。',
            '报名截止时间：2026年11月30日下午5时。',
        ]:
            start, end = extract_registration(text)
            self.assertIsNone(start)
            self.assertEqual(end.isoformat(), '2026-11-30T17:00:00+08:00')

    def test_deadline_only_requires_unambiguous_valid_time(self):
        for text in [
            '报名截止日期：2026年11月30日。',
            '报名截止时间另行通知。面试时间2026年11月30日17:00。',
            '报名截止时间：2026年2月30日17:00。',
            '第一批报名截止时间：2026年11月30日17:00。第二批报名截止时间：2026年12月30日17:00。',
        ]:
            self.assertEqual(extract_registration(text), (None, None))

    def test_canonicalization_keeps_position_identity(self):
        self.assertEqual(canonical_url("https://www.job.sdu.edu.cn/info/1.htm?utm_source=x#top"), "https://job.sdu.edu.cn/info/1.htm")
        self.assertNotEqual(canonical_url("https://jobcareer.sdu.edu.cn/x?id=1"), canonical_url("https://jobcareer.sdu.edu.cn/x?id=2"))

    def test_network_validation_prevents_ssrf(self):
        for url in ["http://127.0.0.1/", "file:///etc/passwd", "https://job.sdu.edu.cn@localhost/", "https://job.sdu.edu.cn:8000/x", "https://evil.invalid/x"]:
            with self.assertRaises(CollectionError):
                validate_fetch_url(url, {"job.sdu.edu.cn"}, resolve=False)
        with patch("apps.employmenthub.collectors.socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.1", 443))]):
            with self.assertRaises(CollectionError):
                validate_fetch_url("https://job.sdu.edu.cn/x", {"job.sdu.edu.cn"})

    def test_robots_disallow_stops_before_content_read(self):
        fetcher = PublicFetcher({"job.sdu.edu.cn"})
        with patch("apps.employmenthub.collectors.validate_fetch_url"), patch.object(fetcher, "_read", return_value="User-agent: *\nDisallow: /info/") as read:
            with self.assertRaises(CollectionError):
                fetcher.get("https://job.sdu.edu.cn/info/test.htm")
        self.assertEqual(read.call_count, 1)

    def test_cross_process_lease_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary, override_settings(BASE_DIR=Path(temporary)):
            with process_lock("sync"):
                with self.assertRaises(CollectionError):
                    with process_lock("sync"):
                        pass
            # File presence does not mean ownership: a released OS lease may be acquired again.
            with process_lock("sync"):
                pass


class CollectionDatabaseTests(TestCase):
    def setUp(self):
        self.source = EmploymentSource.objects.create(key="test", name="公开源", url="https://job.sdu.edu.cn/xdgk.htm", adapter="sdu_selection", enabled=True, category="选调生")
        listing = selection_links(SELECTION_LIST, self.source.url)[0][0]
        self.payload = parse_opportunity(SELECTION_BODY, listing, self.source)

    def test_idempotent_seed_does_not_enable_unconnected_sources(self):
        first = seed_sources()
        self.assertGreater(first, 1)
        self.assertEqual(seed_sources(), 0)
        self.assertEqual(EmploymentSource.objects.filter(adapter="manual", enabled=True).count(), 0)

    def test_repeated_source_does_not_overwrite_teacher_corrections(self):
        self.assertEqual(upsert_opportunity(self.payload), "created")
        item = Opportunity.objects.get()
        teacher_deadline = timezone.now() + timedelta(days=8)
        item.registration_end, item.review_state = teacher_deadline, "已核对"
        item.save()
        self.assertEqual(upsert_opportunity(self.payload), "unchanged")
        item.refresh_from_db()
        self.assertEqual(item.registration_end, teacher_deadline)
        changed = {**self.payload, "summary": "官方公告修订，报名时间发生变化"}
        self.assertEqual(upsert_opportunity(changed), "updated")
        item.refresh_from_db()
        self.assertEqual(item.registration_end, teacher_deadline)
        self.assertEqual(item.review_state, "待核对")
        self.assertIn("sourceCandidate", item.revisions[-1])
        self.assertEqual(upsert_opportunity(changed), "unchanged")
        changed_again = {**changed, "summary": "官方第二次修订，老师尚未重新核对"}
        self.assertEqual(upsert_opportunity(changed_again), "updated")
        item.refresh_from_db()
        self.assertEqual(item.registration_end, teacher_deadline)
        self.assertEqual(item.summary, self.payload["summary"])
        self.assertIn("sourceCandidate", item.revisions[-1])

    def test_source_failure_keeps_existing_opportunities(self):
        upsert_opportunity(self.payload)
        run = SyncRun.objects.create()
        with patch("apps.employmenthub.collectors.PublicFetcher.get", side_effect=CollectionError("robots denied")):
            result = execute_run(run)
        self.assertEqual(result.status, "failed")
        self.assertEqual(Opportunity.objects.count(), 1)
        self.source.refresh_from_db()
        self.assertEqual(self.source.status, "error")
        self.assertIn("robots denied", self.source.last_error)

    def test_bounded_full_sync_reads_actual_payload_and_updates_status(self):
        run = SyncRun.objects.create()
        with patch("apps.employmenthub.collectors.PublicFetcher.get", side_effect=[SELECTION_LIST.replace('<a href="xdgk/11.htm">下页</a>', ''), SELECTION_BODY]):
            counts, errors = collect_source(self.source, run)
        self.assertEqual(counts, {"created": 1, "updated": 0, "checked": 1})
        self.assertEqual(errors, [])
        self.source.refresh_from_db()
        self.assertEqual(self.source.status, "success")
        self.assertIsNotNone(self.source.last_success)
