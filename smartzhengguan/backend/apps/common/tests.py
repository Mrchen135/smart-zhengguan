import tempfile
from datetime import date, timedelta
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.models import AccountActivity, NoticeRead, PrivacyExecution, WorkspaceSetting
from apps.graduate.models import AcademicStatusEvent, ExportRecord, FieldCatalog, HomeGradeMajorSummary, ModuleNotice, Student
from apps.graduate import services


@override_settings(PREDICTION_LLM_ENABLED=False, PRIVACY_DEMO_ALLOW_CLOUD=False)
class DatabasePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='db_admin', password='Local-Test!2026', role='admin')
        self.other = User.objects.create_user(username='other', password='Other-Test!2026', role='teacher')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_authentication_uses_database_and_rejects_mock_credentials(self):
        client = APIClient()
        for path in ['personal-center', 'home', 'intelligent-prediction', 'search', 'cross-module-query', 'upload/batches', 'export/records']:
            self.assertEqual(client.get('/api/v1/' + path + '/').status_code, 401)
        bad = client.post('/api/v1/auth/token/', {'username': 'missing', 'password': '123456'})
        self.assertEqual(bad.status_code, 401)
        result = client.post('/api/v1/auth/token/', {'username': 'db_admin', 'password': 'Local-Test!2026'})
        self.assertEqual(result.status_code, 200, result.data)
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + result.data['access'])
        self.assertEqual(client.get('/api/v1/auth/me/').data['username'], 'db_admin')
        self.assertTrue(AccountActivity.objects.filter(user=self.user, module='登录').exists())

    def test_every_page_api_works_with_an_empty_business_database(self):
        for path in ['home', 'admission', 'academic-status', 'academic-change', 'training', 'training-course',
                     'degree', 'degree-defense', 'scholarship', 'employment', 'shared-options',
                     'search', 'cross-module-query', 'intelligent-prediction', 'personal-center',
                     'change-password', 'system-settings', 'notifications', 'upload/batches',
                     'upload/templates', 'export/fields', 'export/records', 'export/templates',
                     'privacy-collaboration/scenarios']:
            with self.subTest(path=path):
                response = self.client.get('/api/v1/' + path + '/')
                self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        empty = self.client.get('/api/v1/cross-module-query/?grade=2024级')
        self.assertEqual(empty.data['mode'], 'empty')

    def test_portrait_counts_follow_student_inserts_over_stale_summaries(self):
        HomeGradeMajorSummary.objects.create(grade='2024级', major='政治学', total_count=99, male_count=50, female_count=49)
        Student.objects.create(student_id='DB-1', name='数据库测试', grade='2024级', major='政治学', gender='女', degree_type='academic_master')
        response = self.client.get('/api/v1/cross-module-query/?grade=2024级&major=政治学')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['focusRow']['totalStudents'], 1)
        self.assertEqual(response.data['focusRow']['femaleCount'], 1)
        self.assertEqual(response.data['focusRow']['awardCount'], 0)

    def test_missing_snapshots_and_gender_are_not_fabricated(self):
        student = Student.objects.create(student_id='NO-SNAPSHOT', name='缺项测试', grade='2024级', major='政治学理论', degree_type='academic_master')
        self.assertEqual(services.build_prediction_sources(), [])
        self.assertEqual(services.derive_gender_counts([student]), {'male': 0, 'female': 0})
        AcademicStatusEvent.objects.create(external_id='ACTUAL-1', student_name='测试', change_type='休学', occurred_on=date.today(), status='pending')
        result = self.client.get('/api/v1/academic-status/').data
        self.assertEqual(result['statCards'][-1]['number'], 1)

    def test_profile_save_reload_and_role_protection(self):
        data = {'name': '资料测试', 'department': '学院', 'phone': '12345', 'email': 'test@example.com', 'role': 'student', 'jobNo': 'replaced'}
        response = self.client.patch('/api/v1/personal-center/', data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'admin')
        self.assertEqual(self.user.username, 'db_admin')
        self.assertEqual(self.client.get('/api/v1/personal-center/').data['profile']['name'], '资料测试')
        self.assertEqual(AccountActivity.objects.filter(user=self.user, module='个人中心').count(), 1)

    def test_password_validation_and_token_revocation(self):
        client = APIClient()
        tokens = client.post('/api/v1/auth/token/', {'username': 'db_admin', 'password': 'Local-Test!2026'}).data
        data = {'currentPassword': 'wrong', 'newPassword': 'New-Strong!2026', 'confirmPassword': 'New-Strong!2026'}
        self.assertEqual(self.client.post('/api/v1/change-password/', data, format='json').status_code, 400)
        data['currentPassword'] = 'Local-Test!2026'
        self.assertEqual(self.client.post('/api/v1/change-password/', data, format='json').status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-Strong!2026'))
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + tokens['access'])
        self.assertEqual(client.get('/api/v1/auth/me/').status_code, 401)
        refresh = client.post('/api/v1/auth/token/refresh/', {'refresh': tokens['refresh']})
        if refresh.status_code == 200:
            client.credentials(HTTP_AUTHORIZATION='Bearer ' + refresh.data['access'])
            self.assertEqual(client.get('/api/v1/auth/me/').status_code, 401)

    def test_workspace_settings_persist_and_require_admin(self):
        data = {'default_page': '/data-management', 'batch_page_size': 50}
        self.assertEqual(self.client.patch('/api/v1/system-settings/', data, format='json').status_code, 200)
        self.assertEqual(WorkspaceSetting.objects.get(key='batch_page_size').value, 50)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/v1/system-settings/').data['values'], data)
        self.assertEqual(self.client.patch('/api/v1/system-settings/', data, format='json').status_code, 403)

    def test_notification_reads_are_per_account_and_survive_reload(self):
        notice = ModuleNotice.objects.create(module='home', title='数据库通知', notice_date=date.today())
        self.assertFalse(self.client.get('/api/v1/notifications/').data[0]['read'])

        response = self.client.post('/api/v1/notifications/', {'ids': [notice.pk]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.get('/api/v1/notifications/').data[0]['read'])
        self.assertEqual(NoticeRead.objects.count(), 1)
        self.assertTrue(self.client.get('/api/v1/home/').data['notices'][0]['read'])
        self.client.force_authenticate(self.other)
        self.assertFalse(self.client.get('/api/v1/notifications/').data[0]['read'])

    def test_search_history_is_persisted_and_scoped_to_current_account(self):
        for keyword in ['培养', '奖助', '培养']:
            result = self.client.post('/api/v1/search-history/', {'keyword': keyword}, format='json')
            self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/search-history/').data, ['培养', '奖助'])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/v1/search-history/').data, [])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete('/api/v1/search-history/').data, [])

    def test_privacy_audit_persists_without_raw_student_payload(self):
        response = self.client.post('/api/v1/privacy-collaboration/execute/', {'scenario': 'individual', 'executionMode': 'local'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(PrivacyExecution.objects.filter(user=self.user).count(), 1)
        history = self.client.get('/api/v1/privacy-collaboration/scenarios/').data['auditEntries']
        self.assertEqual(history[0]['requestId'], response.data['audit']['requestId'])
        self.assertNotIn('sourceData', history[0])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/v1/privacy-collaboration/scenarios/').data['auditEntries'], [])

    def test_academic_record_changes_are_saved_and_reloaded(self):
        event = AcademicStatusEvent.objects.create(external_id='DB-EVENT', student_name='测试', change_type='休学', occurred_on=date.today(), status='pending')
        data = {'changeType': '复学', 'handler': '管理员', 'reason': '回读验证', 'date': '2026-11-18', 'status': '已通过'}
        response = self.client.patch('/api/v1/academic-status/records/DB-EVENT/', data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        event.refresh_from_db()
        self.assertEqual(event.change_type, '复学')
        self.assertEqual(event.status, 'completed')
        self.assertEqual(self.client.get('/api/v1/academic-status/').data['records'][0]['status'], '已通过')
        self.assertEqual(self.client.get('/api/v1/academic-status/').data['records'][0]['reason'], '回读验证')

    def test_export_reads_database_and_download_checks_owner_and_expiry(self):
        Student.objects.create(student_id='EXPORT-1', name='导出测试', grade='2024级', major='政治学', degree_type='academic_master')
        FieldCatalog.objects.create(module='student', field_code='student.student_id', field_name_cn='学号', data_type='string', is_exportable=True)
        with tempfile.TemporaryDirectory() as temp, override_settings(BASE_DIR=Path(temp)):
            result = self.client.post('/api/v1/export/student-list/', {'fields': ['student.student_id'], 'filters': {}}, format='json')
            self.assertEqual(result.status_code, 200, result.data)
            record = ExportRecord.objects.get(record_id=result.data['record_id'])
            self.assertEqual(record.row_count, 1)
            response = self.client.get('/api/v1/export/download/' + record.record_id + '/')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(b''.join(response.streaming_content).startswith(b'PK'))
            response.close()
            self.client.force_authenticate(self.other)
            self.assertEqual(self.client.get('/api/v1/export/download/' + record.record_id + '/').status_code, 404)
            self.client.force_authenticate(self.user)
            record.expires_at = timezone.now() - timedelta(seconds=1)
            record.save()
            self.assertEqual(self.client.get('/api/v1/export/download/' + record.record_id + '/').status_code, 410)
