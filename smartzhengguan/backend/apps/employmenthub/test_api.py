from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import EmploymentSource, Opportunity, SavedOpportunity, SchedulerState, SyncRun
from .serializers import opportunity_status


BASE = "/api/v1/employment-hub/"


class HubApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.teacher = user_model.objects.create_user(username="hub_teacher", password="Strong-test-845!", role="teacher")
        cls.student = user_model.objects.create_user(username="hub_student", password="Strong-test-845!", role="student")
        cls.other = user_model.objects.create_user(username="hub_other", password="Strong-test-845!", role="student")
        cls.admin = user_model.objects.create_user(username="hub_admin", password="Strong-test-845!", role="admin")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.teacher)
        self.source = EmploymentSource.objects.create(key="api-test", name="测试来源", url="https://example.org/list", enabled=True, adapter="html", status="success")
        self.now = timezone.now()
        self.row = Opportunity.objects.create(source=self.source, canonical_url="https://example.org/jobs/1", title="综合行政岗位",
                                             category="企业招聘", province="山东", employer_type="国企", summary="招聘行政管理专业应届硕士",
                                             related_majors=["行政管理"], match_kind="明确提及",
                                             registration_start=self.now - timedelta(days=1), registration_end=self.now + timedelta(days=2))

    def payload(self, **overrides):
        return {"title": "高校公开招聘公告", "url": "https://example.org/jobs/2", "category": "事业单位", "province": "山东",
                "summary": "本测试资料为接口测试夹具", "relatedMajors": ["政治学理论"], **overrides}

    def test_all_reads_require_actual_login(self):
        self.client.force_authenticate(None)
        for suffix in ["", "meta/", "sources/", "calendar/", "sync/", str(self.row.pk) + "/"]:
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.get(BASE + suffix).status_code, 401)

    def test_student_cannot_mutate_public_information(self):
        self.client.force_authenticate(self.student)
        for method, suffix, payload in [("post", "", self.payload()), ("patch", f"{self.row.pk}/", {"title": "改名"}),
                                        ("post", f"{self.row.pk}/feature/", {"featured": True}), ("post", "sync/", {})]:
            with self.subTest(suffix=suffix):
                self.assertEqual(getattr(self.client, method)(BASE + suffix, payload, format="json").status_code, 403)
        self.row.refresh_from_db()
        self.assertEqual(self.row.title, "综合行政岗位")

    def test_teacher_create_and_admin_feature(self):
        response = self.client.post(BASE, self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        created = Opportunity.objects.get(pk=response.data["id"])
        self.assertEqual(created.related_majors, ["政治学理论"])
        self.assertEqual(created.source_id, None)
        self.assertEqual(response.data["status"], "时间待核实")
        self.assertEqual(response.data["sourceName"], "老师补充")
        self.client.force_authenticate(self.admin)
        featured = self.client.post(BASE + f"{created.pk}/feature/", {"featured": True}, format="json")
        self.assertEqual(featured.status_code, 200)
        self.assertTrue(featured.data["featured"])

    def test_unknown_and_oversized_fields_do_not_persist(self):
        for payload in [self.payload(is_superuser=True), self.payload(title="过" * 301), self.payload(relatedMajors=["不存在专业"]),
                        self.payload(attachments=[{"name": "附件", "url": "javascript:alert(1)"}]), self.payload(matchReasons=["理由"] * 13),
                        self.payload(relatedMajors="行政管理"), self.payload(publishedAt="上周"), self.payload(registrationEnd="明天")]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(BASE, payload, format="json").status_code, 400)
        self.assertEqual(Opportunity.objects.count(), 1)

    def test_date_order_rejected_on_create_and_patch(self):
        end = self.now.isoformat()
        start = (self.now + timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post(BASE, self.payload(registrationStart=start, registrationEnd=end), format="json").status_code, 400)
        response = self.client.patch(BASE + f"{self.row.pk}/", {"registrationStart": (self.now + timedelta(days=3)).isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)
        self.row.refresh_from_db()
        self.assertLess(self.row.registration_start, self.row.registration_end)

    def test_public_url_validation_and_deduplication(self):
        for url in ["javascript:alert(1)", "file:///etc/passwd", "http://127.0.0.1/a", "http://localhost/a", "http://192.168.1.1/a",
                    "https://user:pass@example.org/a", "https://example.org:8080/a", "http://intranet.local/a"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(BASE, self.payload(url=url), format="json").status_code, 400)
        duplicate = self.client.post(BASE, self.payload(url=self.row.canonical_url + "?utm_source=forward#top"), format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(Opportunity.objects.count(), 1)

    def test_save_is_idempotent_and_account_scoped(self):
        self.client.force_authenticate(self.student)
        for _ in range(2):
            response = self.client.post(BASE + f"{self.row.pk}/save/", {"saved": True}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["saved"])
        self.assertEqual(SavedOpportunity.objects.count(), 1)
        self.assertEqual(self.client.get(BASE, {"saved": "1"}).data["count"], 1)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(BASE, {"saved": "1"}).data["count"], 0)
        self.assertFalse(self.client.get(BASE + f"{self.row.pk}/").data["saved"])
        self.client.post(BASE + f"{self.row.pk}/save/", {"saved": False}, format="json")
        self.assertEqual(SavedOpportunity.objects.count(), 1)
        self.client.force_authenticate(self.student)
        self.client.post(BASE + f"{self.row.pk}/save/", {"saved": False}, format="json")
        self.assertEqual(SavedOpportunity.objects.count(), 0)

    def test_channel_major_and_combined_filters(self):
        other = Opportunity.objects.create(canonical_url="https://example.org/jobs/exam", title="人才引进", category="人才引进", province="北京",
                                           related_majors=["国际关系"], summary="政策研究", employer_type="不适用")
        self.assertEqual(self.client.get(BASE, {"channel": "exam"}).data["items"][0]["id"], other.pk)
        result = self.client.get(BASE, {"channel": "company", "major": "行政管理", "province": "山东", "employerType": "国企", "q": "应届硕士"})
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(self.client.get(BASE, {"major": "国际关系", "province": "山东"}).data["count"], 0)
        for params in [{"page": "oops"}, {"pageSize": "999"}, {"major": "杜撰专业"}, {"channel": "other"}, {"saved": "maybe"}, {"status": "可报考"}]:
            self.assertEqual(self.client.get(BASE, params).status_code, 400)

    def test_status_boundaries_and_missing_dates(self):
        cases = [(self.now - timedelta(days=1), self.now, "已截止"),
                 (self.now - timedelta(days=1), self.now + timedelta(days=3), "即将截止"),
                 (self.now - timedelta(days=1), self.now + timedelta(days=4), "报名中"),
                 (self.now + timedelta(hours=1), self.now + timedelta(days=4), "尚未开始"),
                 (None, self.now + timedelta(days=1), "时间待核实"), (None, None, "时间待核实")]
        for start, end, expected in cases:
            self.row.registration_start, self.row.registration_end = start, end
            self.assertEqual(opportunity_status(self.row, self.now), expected)

    def test_closing_soon_stats_match_list_when_registration_start_is_missing(self):
        Opportunity.objects.create(canonical_url="https://example.org/jobs/deadline-only", title="缺少报名开始时间", category="公务员",
                                   registration_end=self.now + timedelta(days=2))
        self.assertEqual(Opportunity.objects.count(), 2)
        stats = self.client.get(BASE + "meta/").data["stats"]
        closing = self.client.get(BASE, {"status": "即将截止"}).data
        self.assertEqual(stats["closingSoon"], 1)
        self.assertEqual(closing["count"], stats["closingSoon"])
        unverified = self.client.get(BASE, {"status": "时间待核实"}).data
        self.assertEqual(unverified["count"], 1)

    def test_calendar_uses_full_month_events_not_first_list_page(self):
        november = timezone.make_aware(datetime(2026, 11, 30, 23, 30))
        december = november + timedelta(hours=1)
        self.row.registration_start = november
        self.row.registration_end = december
        self.row.save()
        target = Opportunity.objects.create(canonical_url="https://example.org/jobs/calendar", title="月内考试", category="公务员", province="山东", exam_at=november)
        for index in range(15):
            Opportunity.objects.create(canonical_url=f"https://example.org/jobs/no-event-{index}", title="无时间公告", category="公务员")
        response = self.client.get(BASE + "calendar/", {"month": "2026-11", "pageSize": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual({r["id"] for r in response.data["items"]}, {self.row.pk, target.pk})
        self.assertEqual(self.client.get(BASE + "calendar/", {"month": "2026-12"}).data["count"], 1)
        self.assertEqual(self.client.get(BASE + "calendar/", {"month": "not-a-month"}).status_code, 400)

    def test_update_preserves_revision_and_publication_link(self):
        self.row.content_hash = "a" * 64
        self.row.save(update_fields=["content_hash"])
        response = self.client.patch(BASE + f"{self.row.pk}/", {"summary": "官方延期，老师核对", "registrationEnd": (self.now + timedelta(days=5)).isoformat(),
                                                                "reviewState": "已核对"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_state, "已核对")
        self.assertEqual(len(self.row.revisions), 1)
        self.assertIn("registration_end", self.row.revisions[0]["changes"])
        self.assertEqual(self.row.canonical_url, "https://example.org/jobs/1")
        self.assertEqual(self.row.revisions[0]["actor"], self.teacher.username)
        self.assertEqual(self.row.content_hash, "a" * 64)

    def test_calendar_exposes_truncation_and_total_without_fake_pagination(self):
        moment = timezone.make_aware(datetime(2026, 12, 15, 12))
        Opportunity.objects.bulk_create([Opportunity(canonical_url=f"https://example.org/jobs/bulk-{index}", title="月内节点", category="公务员", exam_at=moment)
                                         for index in range(1001)])
        response = self.client.get(BASE + "calendar/", {"month": "2026-12"})
        self.assertEqual(response.data["count"], 1001)
        self.assertEqual(len(response.data["items"]), 1000)
        self.assertTrue(response.data["truncated"])

    def test_digest_preserves_order_sources_and_uncertainty(self):
        other = self.client.post(BASE, self.payload(), format="json").data
        self.client.force_authenticate(self.student)
        result = self.client.post(BASE + "digest/", {"ids": [other["id"], self.row.pk, self.row.pk]}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 2)
        text = result.data["text"]
        self.assertLess(text.index(other["title"]), text.index(self.row.title))
        self.assertIn("不代表报考资格认定", text)
        self.assertIn("公告未明确", text)
        self.assertIn(self.row.canonical_url, text)
        self.assertEqual(self.client.post(BASE + "digest/", {"ids": [99999]}, format="json").status_code, 400)
        self.assertEqual(self.client.post(BASE + "digest/", {"ids": []}, format="json").status_code, 400)

    def test_scheduler_is_not_claimed_running_without_fresh_heartbeat(self):
        response = self.client.get(BASE + "sync/")
        self.assertFalse(response.data["scheduler"]["running"])
        state = SchedulerState.objects.create(heartbeat_at=self.now - timedelta(minutes=3), status="running", interval_seconds=43200)
        self.assertFalse(self.client.get(BASE + "meta/").data["scheduler"]["running"])
        state.heartbeat_at = timezone.now()
        state.save()
        self.assertTrue(self.client.get(BASE + "meta/").data["scheduler"]["running"])
        state.stop_requested = True
        state.save()
        self.assertFalse(self.client.get(BASE + "meta/").data["scheduler"]["running"])

    def test_source_list_does_not_fetch_network_or_mark_pending_as_connected(self):
        EmploymentSource.objects.create(key="not-connected", name="仅入口", url="https://example.org/manual", enabled=False, status="pending")
        result = self.client.get(BASE + "sources/")
        self.assertEqual(result.data["summary"]["total"], 2)
        self.assertEqual(result.data["summary"]["pending"], 1)
        self.assertEqual(self.client.get(BASE + "meta/").data["stats"]["sourcesConnected"], 1)

    def test_sync_queues_asynchronously_and_validates_source(self):
        from . import collectors
        run = SyncRun.objects.create(source=self.source)
        with patch.object(collectors, "queue_sync", return_value=run) as queue:
            result = self.client.post(BASE + "sync/", {"sourceId": self.source.pk}, format="json")
            self.assertEqual(result.status_code, 202)
            queue.assert_called_once_with(source_id=self.source.pk, requested_by=self.teacher)
        with patch.object(collectors, "queue_sync", side_effect=ValueError("已有同步任务")):
            self.assertEqual(self.client.post(BASE + "sync/", {}, format="json").status_code, 409)
        self.source.enabled = False
        self.source.save()
        self.assertEqual(self.client.post(BASE + "sync/", {"sourceId": self.source.pk}, format="json").status_code, 400)

    def test_company_track_source_and_multiple_regions(self):
        row = Opportunity.objects.create(source=self.source, canonical_url='https://campus.163.com/job/42',
            title='网易 · 人力资源', category='企业招聘', employer_type='民企', province='全国',
            metadata={'entryType': 'position', 'companyGroup': '网易', 'locations': ['北京', '浙江']})
        result = self.client.get(BASE, {'companyTrack': 'internet', 'province': '浙江', 'sourceId': self.source.pk})
        self.assertEqual(result.status_code, 200)
        self.assertEqual([v['id'] for v in result.data['items']], [row.pk])
        self.assertEqual(result.data['items'][0]['metadata']['entryType'], 'position')
        state = self.client.get(BASE, {'companyTrack': 'state'})
        self.assertEqual([v['id'] for v in state.data['items']], [self.row.pk])
        self.assertEqual(self.client.get(BASE, {'companyTrack': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get(BASE, {'province': 'bad'}).status_code, 400)
