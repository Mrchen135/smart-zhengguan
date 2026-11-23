import json
from datetime import date
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from apps.common.models import CollaborationTask
from apps.graduate.models import Student
from apps.graduate import collaboration_tasks as tasks


class CustomTaskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='task-owner', password='test-only')
        self.other = get_user_model().objects.create_user(username='task-other', password='test-only')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        for i in range(10):
            Student.objects.create(student_id=f'TEST-{i:03}', name=f'测试人员{i}', gender='女',
                major='国际关系', grade='2025级', degree_type='academic_master', profile_source='demo_test',
                expected_graduation_date=date(2099, 6, 1))
        self.body = {'title': '培养分析', 'question': '分析课程培养情况并提供三条行动建议', 'topic': 'training', 'grade': '2025级', 'major': ''}
        self.url = '/api/v1/privacy-collaboration/tasks/'

    def create(self, **extra):
        response = self.client.post(self.url, {**self.body, **extra}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def execute(self, task, mode='local', **extra):
        return self.client.post(self.url+str(task['id'])+'/execute/',
            {'executionMode': mode, 'payloadDigest': task['plan']['payloadDigest'], **extra}, format='json')

    def test_authentication_and_ownership(self):
        task = self.create()
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data['tasks'], [])
        self.assertEqual(self.client.get(self.url+str(task['id'])+'/').status_code, 404)
        self.assertEqual(self.execute(task).status_code, 404)

    def test_snapshot_has_no_individual_records_and_rejects_client_payload(self):
        task = self.create()
        approved = json.dumps(task['plan']['cloudPayload'], ensure_ascii=False)
        self.assertEqual(task['plan']['studentCount'], 10)
        self.assertEqual(task['plan']['demoRecordCount'], 10)
        for forbidden in ('测试人员', 'TEST-000', 'student_id', 'advisor_name'):
            self.assertNotIn(forbidden, approved)
        response = self.client.post(self.url, {**self.body, 'cloudPayload': {'name': 'tampered'}}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.execute(task, cloudPayload={}).status_code, 400)

    def test_text_identity_and_small_complement_block_cloud(self):
        personal = self.create(question='请分析测试人员0的课程情况并给建议')
        self.assertEqual(personal['plan']['route'], 'local')
        self.assertIsNone(personal['plan']['cloudPayload'])
        self.assertEqual(self.execute(personal, 'cloud').status_code, 409)
        Student.objects.filter(student_id='TEST-000').update(profile_source='imported')
        small = self.create()
        self.assertEqual(small['plan']['route'], 'local')
        self.assertIn('互补', small['plan']['reason'])

    def test_scope_is_inferred_and_conflicts_are_rejected(self):
        task = self.create(grade='', question='请比较2025级国际关系专业的课程与培养进度')
        self.assertEqual(task['grade'], '2025级')
        self.assertEqual(task['major'], '国际关系')
        Student.objects.filter(student_id='TEST-000').update(grade='2024级')
        response = self.client.post(self.url, {**self.body, 'question': '分析2024级培养进展并提出具体建议'}, format='json')
        self.assertEqual(response.status_code, 400)

    @patch.object(tasks.llm, 'invoke_prediction_chat_completion')
    def test_local_execution_and_repeat_requests_are_idempotent(self, invoke):
        task = self.create()
        first = self.execute(task)
        second = self.execute(task)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['result'], second.data['result'])
        self.assertEqual(first.data['status'], 'completed')
        self.assertFalse(first.data['result']['audit']['cloudAttempted'])
        invoke.assert_not_called()
        self.assertEqual(self.client.get(self.url+str(task['id'])+'/').data['result'], first.data['result'])

    @patch.object(tasks.privacy, 'cloud_available', return_value=True)
    @patch.object(tasks.llm, 'invoke_prediction_chat_completion')
    def test_custom_question_reaches_cloud_and_result_is_saved_once(self, invoke, available):
        invoke.return_value = {'used': True, 'answer': {'directAnswer': '该群体全部在读，建议核对培养计划。', 'reasoning': ['共10人，均为演示记录。'], 'actionPlan': ['安排课程核对。'], 'citations': []}}
        task = self.create()
        response = self.execute(task, 'cloud')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['result']['audit']['cloudUsed'])
        self.assertEqual(invoke.call_args.args[0]['messages'][1]['content'], self.body['question'])
        self.execute(task, 'cloud')
        self.assertEqual(invoke.call_count, 1)

    @patch.object(tasks.privacy, 'cloud_available', return_value=True)
    @patch.object(tasks.llm, 'invoke_prediction_chat_completion', side_effect=TimeoutError('secret provider error'))
    def test_cloud_failure_is_honest_and_does_not_leak_errors(self, invoke, available):
        response = self.execute(self.create(), 'cloud')
        self.assertEqual(response.data['status'], 'fallback')
        self.assertTrue(response.data['result']['audit']['cloudAttempted'])
        self.assertFalse(response.data['result']['audit']['cloudUsed'])
        self.assertNotIn('secret provider error', json.dumps(response.data))

    @patch.object(tasks.llm, 'invoke_prediction_chat_completion')
    def test_stale_digest_and_running_task_cannot_execute(self, invoke):
        task = self.create()
        self.assertEqual(self.execute(task, payloadDigest='stale').status_code, 409)
        CollaborationTask.objects.filter(pk=task['id']).update(status='running')
        self.assertEqual(self.execute(task).status_code, 409)
        invoke.assert_not_called()

    @patch.object(tasks.privacy, 'cloud_available', return_value=True)
    @patch.object(tasks.llm, 'invoke_prediction_chat_completion')
    def test_unsupported_phase_judgment_is_not_presented_as_valid_analysis(self, invoke, available):
        invoke.return_value = {'used': True, 'answer': {'directAnswer': '培养进度说明整体滞后', 'reasoning': [], 'actionPlan': [], 'citations': []}}
        response = self.execute(self.create(), 'cloud')
        self.assertEqual(response.data['status'], 'fallback')
        self.assertIn('阶段标准', response.data['result']['fallbackReason'])
        self.assertNotIn('整体滞后', response.data['result']['answer']['directAnswer'])

    def test_qualified_limit_is_not_mistaken_for_an_unsupported_claim(self):
        self.assertFalse(tasks.unsupported_judgment({'directAnswer': '缺少阶段目标，不能认定整体滞后。'}))
        self.assertTrue(tasks.unsupported_judgment({'directAnswer': '培养进度偏低，需要预警。'}))
