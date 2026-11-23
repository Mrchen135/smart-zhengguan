import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, TestCase
from .catalog import seed_sources
from .collectors import CollectionError, PublicFetcher, collect_source, upsert_opportunity
from .expanded_collectors import (parse_netease, netease_payloads, parse_guopin, parse_nankai, nankai_links, track_of, company_group)
from .models import EmploymentSource, Opportunity, SyncRun


class ExpandedParserTests(SimpleTestCase):
    def test_direct_position_keeps_requirements_locations_and_update_provenance(self):
        p = parse_netease({'id': 42, 'positionName': '人力资源校招生', 'positionDescription': '参与组织管理',
            'positionRequirement': '行政管理专业硕士', 'workPlaceName': '杭州,北京', 'updateTime': 1795000000000},
            {'id': '103', 'title': '2027校招'}, None)
        self.assertIsNone(p['published_at'])
        self.assertIsNone(p['registration_end'])
        self.assertEqual(p['metadata']['entryType'], 'position')
        self.assertEqual(set(p['metadata']['locations']), {'浙江', '北京'})
        self.assertIn('sourceUpdatedAt', p['metadata'])
        self.assertIn('行政管理专业硕士', p['requirements'])
        self.assertEqual(p['related_majors'], ['行政管理'])
        self.assertEqual(p['canonical_url'], 'https://campus.163.com/app/detail/index?id=42&projectId=103')

    def test_navigation_discovers_current_project_and_reads_all_pages(self):
        f = Mock()
        f.get_json.side_effect = [
            {'code': 200, 'data': [{'children': [{'title': '新批次', 'link': 'https://campus.163.com/app/job/position?id=108'},
                {'link': 'https://outside.example/app/job/position?id=999'}]}]},
            {'code': 200, 'data': {'total': 21, 'list': [{'id': 1, 'positionName': '岗位一'}]}},
            {'code': 200, 'data': {'total': 21, 'lastPage': True, 'list': [{'id': 2, 'positionName': '岗位二'}]}},
        ]
        rows = list(netease_payloads(None, f))
        self.assertEqual(len(rows), 2)
        self.assertIn('projectId=108', rows[1]['canonical_url'])
        self.assertIn('currentPage=2', f.get_json.call_args.args[0])
        self.assertEqual(f.get_json.call_count, 3)

    def test_error_json_is_not_a_successful_empty_sync(self):
        f = Mock(); f.get_json.return_value = {'code': 403, 'message': 'unavailable'}
        with self.assertRaises(CollectionError): list(netease_payloads(None, f))

    def test_guopin_index_does_not_invent_jobs_qualifications_or_dates(self):
        p = parse_guopin({'id': 1, 'title': '测试集团2027校园招聘', 'link_url': 'https://example.org/notice',
                         'create_time': '2026-11-20 10:00:00', 'content': ''}, None,
                         [('测试集团', '测试集团有限公司', '央企')])
        self.assertEqual(p['employer_type'], '央企')
        self.assertEqual(p['employer'], '测试集团有限公司')
        self.assertEqual(p['metadata']['entryType'], 'announcement_index')
        self.assertEqual(p['requirements'], '')
        self.assertEqual(p['related_majors'], [])
        self.assertIsNone(p['registration_end'])
        self.assertEqual(p['published_at'], date(2026, 11, 20))
        self.assertIsNone(parse_guopin({'title': '活动回顾', 'link_url': 'https://example.org/a'}, None, []))

    def test_nankai_content_excludes_navigation_and_preserves_apply_link(self):
        html = '''<nav>导航含应急管理</nav><div class="top"><div class="title1">阿里云校园招聘</div>
        <div class="company"><a>阿里巴巴（中国）有限公司</a></div><div class="date">发布时间：2026-11-20 浏览量：1</div>
        <div class="zpxx">职位投递网址链接：https://campus.example.org/apply</div>
        <div class="zpxx">工作地域：北京 浙江省</div></div>
        <div class="zpnr"><p>行政管理专业硕士，参与人力资源工作。</p><a href="/job.xlsx">岗位表</a></div>'''
        p = parse_nankai(html, {'url': 'https://career.nankai.edu.cn/correcruit/content/id/12.html', 'title': '列表'}, None)
        self.assertEqual(p['title'], '阿里云校园招聘')
        self.assertEqual(p['metadata']['applyUrl'], 'https://campus.example.org/apply')
        self.assertEqual(p['metadata']['companyGroup'], '阿里巴巴')
        self.assertEqual(p['published_at'], date(2026, 11, 20))
        self.assertNotIn('应急管理', p['requirements'])
        self.assertEqual(len(p['attachments']), 1)
        links = nankai_links('<a href="/correcruit/content/id/12.html">招聘</a><a href="/correcruit/content/id/12.html">重复</a><a href="https://external.org">外部</a>')
        self.assertEqual(len(links), 1)

    def test_similar_company_names_and_school_publisher_are_distinguished(self):
        self.assertEqual(company_group('京东方科技集团股份有限公司'), '京东方')
        self.assertEqual(company_group('京东2027届管培生'), '京东')
        html = '<div class="top"><div class="title1">美团校园招聘</div><div class="company">南开大学就业指导中心代发</div></div><div class="zpnr">招聘管理培训生</div>'
        p = parse_nankai(html, {'url': 'https://career.nankai.edu.cn/correcruit/content/id/12.html', 'title': ''}, None)
        self.assertEqual(p['employer'], '美团')
        self.assertIn('代发', p['metadata']['publisherName'])

    @patch('apps.employmenthub.collectors.validate_fetch_url')
    def test_json_and_post_still_obey_robots(self, validate):
        f = PublicFetcher({'example.org'})
        with patch.object(f, '_read', return_value='User-agent: *\nDisallow: /api/') as read:
            with self.assertRaises(CollectionError): f.get_json('https://example.org/api/query', {'page': 1})
            self.assertEqual(read.call_count, 1)
        with patch.object(f, 'get', return_value='<html>login</html>'):
            with self.assertRaises(CollectionError): f.get_json('https://example.org/public')


class ExpandedCollectionTests(TestCase):
    def test_registry_refresh_connects_verified_adapters_only(self):
        source = EmploymentSource.objects.create(key='iguopin-jobs', name='旧入口', url='https://job.iguopin.com/', adapter='manual')
        seed_sources(); source.refresh_from_db()
        self.assertEqual(source.adapter, 'manual')
        seed_sources(update_existing=True); source.refresh_from_db()
        self.assertTrue(source.enabled)
        self.assertEqual(source.adapter, 'guopin_public')
        self.assertEqual(EmploymentSource.objects.filter(enabled=True, adapter='manual').count(), 0)

    def test_repeated_position_sync_is_idempotent_and_protects_teacher_edits(self):
        source = EmploymentSource.objects.create(key='net-test', name='网易', url='https://campus.163.com/', adapter='netease_campus', enabled=True)
        payload = parse_netease({'id': 42, 'positionName': '人力资源', 'positionRequirement': '行政管理专业'}, {'id': '103', 'title': '2027'}, source)
        self.assertEqual(upsert_opportunity(payload), 'created')
        self.assertEqual(upsert_opportunity(payload), 'unchanged')
        row = Opportunity.objects.get(); row.title = '教师核对标题'; row.review_state = '已核对'; row.save()
        changed = {**payload, 'title': '来源新标题'}
        upsert_opportunity(changed); row.refresh_from_db()
        self.assertEqual(row.title, '教师核对标题')
        self.assertEqual(Opportunity.objects.count(), 1)

    def test_expanded_collection_failure_is_reported(self):
        source = EmploymentSource.objects.create(key='net-test', name='网易', url='https://campus.163.com/', adapter='netease_campus', enabled=True)
        f = Mock(); f.get_json.return_value = {'code': 403}; f.requests = 1
        run = SyncRun.objects.create(source=source)
        with patch('apps.employmenthub.collectors.PublicFetcher', return_value=f):
            with self.assertRaises(CollectionError): collect_source(source, run)
        self.assertEqual(Opportunity.objects.count(), 0)
