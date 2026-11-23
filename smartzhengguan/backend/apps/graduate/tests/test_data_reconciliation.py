from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.graduate.data_reconciliation import reconcile, reconcile_doctoral_cohort, SOURCE
from apps.graduate.management.commands.import_excel_data import Command
from apps.graduate.models import (
    Student, TrainingPlan, DegreeApplication, EmploymentRecord,
    PredictionSnapshot, PredictionMonthlyMetric, AcademicStatusEvent,
    AcademicChangeRequest, DataRepairArchive, HomeAnnualSummary,
    HomeGradeMajorSummary, HomeSourceRegionSummary,
)
from apps.graduate.services import get_home_data


@patch('apps.graduate.data_reconciliation.timezone.localdate', return_value=date(2026, 11, 23))
class DataReconciliationTests(TestCase):
    def student(self, sid='demo1', **extra):
        values = dict(student_id=sid, name='演示样本', gender='女', profile_source='demo_test',
                      grade='2025级', major='国际关系', degree_type='academic_master',
                      enrolled_on=date(2025, 9, 1), current_status='active', source_region='山东')
        values.update(extra)
        return Student.objects.create(**values)

    def legacy_pair(self, student, day, change='复学', event_status='completed', request_status='completed'):
        event = AcademicStatusEvent.objects.create(student=student, student_name=student.name,
            external_id=f'event-{AcademicStatusEvent.objects.count()}', change_type=change,
            reason=f'{change}业务导入记录', occurred_on=day, status=event_status)
        request = AcademicChangeRequest.objects.create(student=student, student_name=student.name,
            change_type=change, current_step='审批', remark=f'Excel 导入生成的{change}申请',
            submitted_at=timezone.make_aware(datetime.combine(day, datetime.min.time())),
            status=request_status, status_type='warning' if request_status == 'pending' else 'success')
        return event, request

    def test_exact_duplicates_are_archived_and_rerun_is_empty(self, _today):
        student = self.student()
        values = dict(student=student, student_name=student.name, grade=student.grade,
                      major=student.major, degree_type=student.degree_type, stage='开题', status='pending')
        duplicate = TrainingPlan.objects.create(**values)
        keep = TrainingPlan.objects.create(**values)
        degree = dict(student=student, application_year=2026, application_type='硕士',
                      discipline=student.major, award_status='pending')
        DegreeApplication.objects.create(**degree)
        DegreeApplication.objects.create(**degree)
        draft = reconcile()
        self.assertEqual(draft['archiveCount'], 2)
        self.assertEqual(TrainingPlan.objects.count(), 2)
        self.assertEqual(DataRepairArchive.objects.count(), 0)
        reconcile(apply=True, batch_id='test-dedupe')
        self.assertEqual(list(TrainingPlan.objects.values_list('pk', flat=True)), [keep.pk])
        archived = DataRepairArchive.objects.get(model_label='graduate.TrainingPlan')
        self.assertEqual(archived.original_pk, duplicate.pk)
        self.assertEqual(archived.canonical_pk, keep.pk)
        self.assertEqual(archived.original['fields']['student'], student.pk)
        self.assertEqual(DegreeApplication.objects.count(), 1)
        again = reconcile()
        self.assertEqual((again['archiveCount'], again['updateCount'], again['createCount']), (0, 0, 0))

    def test_invalid_history_archived_without_altering_current_destination(self, _today):
        student = self.student(grade='2023级', enrolled_on=date(2023, 9, 1),
                               graduated_on=date(2026, 6, 30), current_status='graduated')
        old = EmploymentRecord.objects.create(student=student, student_name=student.name, graduation_year=2023)
        current = EmploymentRecord.objects.create(student=student, student_name=student.name,
            graduation_year=2026, destination_type='employment', data_source='demo_test', employer_name='演示单位')
        snap = PredictionSnapshot.objects.create(student=student, risk_level='low',
            captured_at=timezone.make_aware(datetime(2026, 6, 30, 12)))
        for month in ['2023-08', '2026-06', '2026-07']:
            PredictionMonthlyMetric.objects.create(snapshot=snap, month=month)
        reconcile(apply=True, batch_id='test-history')
        self.assertFalse(EmploymentRecord.objects.filter(pk=old.pk).exists())
        current.refresh_from_db()
        self.assertEqual(current.employer_name, '演示单位')
        self.assertEqual(list(snap.monthly_metrics.values_list('month', flat=True)), ['2026-06'])
        self.assertEqual(DataRepairArchive.objects.filter(action='archive').count(), 3)

    def test_academic_pairs_preserve_principal_state_and_track_sources(self, _today):
        student = self.student()
        invalid, invalid_request = self.legacy_pair(student, date(2024, 1, 1))
        valid, valid_request = self.legacy_pair(student, date(2026, 1, 1))
        pending, pending_request = self.legacy_pair(student, date(2026, 2, 1), '其他异动', 'in_progress', 'pending')
        conflict_student = self.student('conflict')
        conflict, _ = self.legacy_pair(conflict_student, date(2026, 2, 1), '休学')
        reconcile(apply=True, batch_id='test-academic')
        self.assertFalse(AcademicStatusEvent.objects.filter(pk__in=[invalid.pk, conflict.pk]).exists())
        self.assertFalse(AcademicChangeRequest.objects.filter(pk=invalid_request.pk).exists())
        valid.refresh_from_db(); valid_request.refresh_from_db(); pending.refresh_from_db()
        self.assertEqual(valid.data_source, SOURCE)
        self.assertEqual(valid_request.data_source, SOURCE)
        self.assertEqual((pending.status, pending.status_tag), ('pending', 'warning'))
        conflict_student.refresh_from_db()
        self.assertEqual(conflict_student.current_status, 'active')
        self.assertEqual(DataRepairArchive.objects.filter(action='archive', model_label__contains='Academic').count(), 4)

    def test_unmatched_academic_rows_stop_all_changes(self, _today):
        student = self.student()
        _, request = self.legacy_pair(student, date(2024, 1, 1))
        request.delete()
        with self.assertRaises(ValidationError):
            reconcile(apply=True, batch_id='test-mismatch')
        self.assertEqual(AcademicStatusEvent.objects.count(), 1)
        self.assertEqual(DataRepairArchive.objects.count(), 0)

    def test_summary_and_live_home_keep_populations_explicit(self, _today):
        active = self.student(is_international=True)
        self.student('graduate', grade='2023级', enrolled_on=date(2023, 9, 1),
                     graduated_on=date(2026, 6, 30), current_status='graduated', gender='男', source_region='北京')
        historic = HomeAnnualSummary.objects.create(year=2025, total_students=99, master_count=99)
        group = HomeGradeMajorSummary.objects.create(grade=active.grade, major=active.major, total_count=90)
        HomeSourceRegionSummary.objects.create(region='山东', student_count=90, percent_text='100%')
        # The homepage must already ignore outdated cached aggregates before a repair runs.
        before = get_home_data()
        self.assertEqual(before['headline']['totalStudents'], 2)
        self.assertEqual(before['statCards'][0]['number'], 1)
        reconcile(apply=True, batch_id='test-summary')
        active.refresh_from_db(); group.refresh_from_db(); historic.refresh_from_db()
        self.assertEqual(active.enrollment_type, 'international')
        self.assertEqual(active.degree_type, 'academic_master')
        self.assertEqual((group.total_count, group.male_count, group.female_count), (1, 0, 1))
        self.assertEqual(historic.total_students, 99)
        annual = HomeAnnualSummary.objects.get(year=2026)
        self.assertEqual((annual.total_students, annual.international_count, annual.annual_graduates), (1, 1, 1))
        self.assertEqual(sum(HomeSourceRegionSummary.objects.values_list('student_count', flat=True)), 2)
        home = get_home_data()
        self.assertEqual(home['headline']['totalStudents'], 2)
        self.assertEqual(home['headline']['annualGraduates'], 1)
        for chart in ['gender', 'grades', 'sourceRegions']:
            self.assertEqual(sum(row['value'] for row in home['charts'][chart]), 2)
        self.assertEqual(sum(row['master'] + row['doctor'] for row in home['charts']['trend']), 2)

    def test_non_demo_data_is_not_synthesized_or_rewritten(self, _today):
        self.student(profile_source='official_import')
        with self.assertRaises(ValidationError):
            reconcile(apply=True, batch_id='test-real')
        self.assertEqual(DataRepairArchive.objects.count(), 0)
        self.assertEqual(HomeAnnualSummary.objects.count(), 0)

    def test_failure_rolls_back_archives_deletes_and_updates(self, _today):
        student = self.student(is_international=True)
        old = EmploymentRecord.objects.create(student=student, graduation_year=2023)
        EmploymentRecord.objects.create(student=student, graduation_year=2028, data_source='demo_test')
        with patch.object(DataRepairArchive.objects, 'create', side_effect=RuntimeError('forced rollback')):
            with self.assertRaises(RuntimeError):
                reconcile(apply=True, batch_id='test-rollback')
        student.refresh_from_db()
        self.assertEqual(student.enrollment_type, 'master')
        self.assertTrue(EmploymentRecord.objects.filter(pk=old.pk).exists())
        self.assertEqual(DataRepairArchive.objects.count(), 0)

    def test_aggregate_import_does_not_generate_individual_events(self, _today):
        student = self.student()
        command = Command(stdout=StringIO())
        with patch.object(command, 'sheet_rows', return_value=[{'年份': 2025, '休学人数': 10}]):
            command.import_academic_records(None, {'all': [student]})
        self.assertEqual(AcademicStatusEvent.objects.count(), 0)
        self.assertEqual(AcademicChangeRequest.objects.count(), 0)
        self.assertIn('已跳过个人异动生成', command.stdout.getvalue())

    def test_only_masters_follow_three_year_policy_and_doctoral_data_is_consistent(self, _today):
        from apps.graduate.management.commands.complete_demo_destinations import graduation_date
        master = self.student('master', grade='2023级', enrolled_on=date(2023, 9, 1),
            graduated_on=date(2026, 6, 30), current_status='graduated')
        doctor = self.student('doctor', grade='2023级', degree_type='doctoral', enrollment_type='doctoral',
            enrolled_on=date(2023, 9, 1), graduated_on=date(2026, 6, 30), current_status='graduated',
            expected_graduation_date=date(2026, 6, 30))
        plan = TrainingPlan.objects.create(student=doctor, stage='培养完成', completion_percent=100, status='completed')
        degree = DegreeApplication.objects.create(student=doctor, application_year=2026,
            application_type='博士学位', award_status='completed', awarded_at=date(2026, 6, 30))
        job = EmploymentRecord.objects.create(student=doctor, graduation_year=2026,
            destination_type='就业', employer_name='模拟单位', is_signed=True, data_source='demo_test')
        snap = PredictionSnapshot.objects.create(student=doctor, risk_level='low', data_source='demo_portrait_v3',
            captured_at=timezone.make_aware(datetime(2026, 6, 30, 12)))
        old_month = PredictionMonthlyMetric.objects.create(snapshot=snap, month='2026-06')
        self.assertEqual(graduation_date(master), date(2026, 6, 30))
        self.assertEqual(graduation_date(doctor), date(2027, 6, 30))
        self.assertEqual(reconcile_doctoral_cohort()['students'], 1)
        doctor.refresh_from_db()
        self.assertEqual(doctor.current_status, 'graduated')
        result = reconcile_doctoral_cohort(apply=True, batch_id='test-doctor')
        self.assertEqual(result['students'], 1)
        doctor.refresh_from_db(); master.refresh_from_db(); plan.refresh_from_db()
        degree.refresh_from_db(); job.refresh_from_db(); snap.refresh_from_db()
        self.assertEqual(doctor.degree_type, 'doctoral')
        self.assertEqual(doctor.current_status, 'active')
        self.assertIsNone(doctor.graduated_on)
        self.assertEqual(master.current_status, 'graduated')
        self.assertEqual(plan.status, 'in_progress')
        self.assertLess(plan.completion_percent, 100)
        self.assertEqual(degree.application_year, 2027)
        self.assertIsNone(degree.awarded_at)
        self.assertEqual(job.destination_type, '在读')
        self.assertEqual(job.graduation_year, 2027)
        self.assertEqual(job.employer_name, '')
        self.assertFalse(job.is_signed)
        self.assertEqual(snap.monthly_metrics.count(), 6)
        self.assertEqual(snap.monthly_metrics.order_by('month').last().month, '2026-11')
        self.assertTrue(DataRepairArchive.objects.filter(action='archive', model_label='graduate.PredictionMonthlyMetric', original_pk=old_month.pk).exists())
        self.assertEqual(reconcile_doctoral_cohort()['students'], 0)

    def test_doctoral_correction_will_not_rewrite_real_student(self, _today):
        self.student('doctor', grade='2023级', degree_type='doctoral', profile_source='official', current_status='graduated')
        with self.assertRaises(ValidationError):
            reconcile_doctoral_cohort(apply=True, batch_id='test-doctor-real')
        self.assertEqual(DataRepairArchive.objects.count(), 0)
