from datetime import date
from django.test import TestCase
from apps.graduate.models import Student, EmploymentRecord
from apps.graduate.portrait import destination_state, summarize_destinations
from apps.graduate.services import build_cross_module_context, build_cross_module_row, get_employment_data

class PortraitTests(TestCase):
    def student(self, sid, **extra):
        return Student.objects.create(student_id=sid,name='测试',gender='女',grade='2023级',major='国际关系',degree_type='academic_master',**extra)
    def record(self, student, year, label, status='completed'):
        return EmploymentRecord.objects.create(student=student,graduation_year=year,destination_type=label,status=status)
    def test_latest_record_overrides_old_resolved_destination(self):
        student=self.student('1')
        old=self.record(student,2025,'单位就业')
        new=self.record(student,2026,'去向待核实','draft')
        counts={r['key']:r['count'] for r in summarize_destinations([student],[old,new])}
        self.assertEqual(counts['verify'],1)
        self.assertEqual(counts['employment'],0)
        self.assertEqual(sum(counts.values()),1)
    def test_in_study_and_expired_dates_do_not_mean_unemployed(self):
        student=self.student('2',expected_graduation_date=date(2027,6,30))
        self.assertEqual(destination_state(student,today=date(2026,11,23)),'in_study')
        self.assertEqual(destination_state(student,today=date(2028,1,1)),'verify')
        record=self.record(student,2027,'在读（暂不纳入）','draft')
        self.assertEqual(destination_state(student,record,today=date(2028,1,1)),'verify')
    def test_group_counts_match_people_not_records(self):
        a=self.student('3'); b=self.student('4'); c=self.student('5',expected_graduation_date=date(2099,6,30))
        self.record(a,2025,'单位就业');self.record(a,2026,'升学')
        self.record(b,2026,'未就业','pending');self.record(c,2099,'在读（暂不纳入）','draft')
        row=build_cross_module_row(('2023级','国际关系'),build_cross_module_context())
        self.assertEqual(row['totalStudents'],3)
        self.assertEqual(row['employedCount'],1)
        self.assertEqual(row['unresolvedCount'],1)
        self.assertEqual(row['inStudyCount'],1)
        self.assertEqual(sum(d['count'] for d in row['destinations']),3)
        self.assertEqual(row['destinationTrackingCount'],3)
        self.assertEqual(row['trainingCoverageCount'],0)
        card=get_employment_data()['statCards'][3]
        self.assertEqual(card['number'],50)
    def test_pending_approval_does_not_count_as_resolved(self):
        student=self.student('6');record=self.record(student,2026,'单位就业','pending')
        self.assertEqual(destination_state(student,record),'verify')

    def test_civil_service_preparation_is_not_employment(self):
        student=self.student('7')
        record=self.record(student,2026,'考公','in_progress')
        self.assertEqual(destination_state(student,record),'civil_service')
        row=build_cross_module_row(('2023级','国际关系'),build_cross_module_context())
        self.assertEqual(row['employedCount'],0)
        self.assertEqual(row['civilServiceCount'],1)

    def test_explicit_unknown_is_not_missing_or_unemployed(self):
        student=self.student('8')
        record=self.record(student,2026,'未知','pending')
        self.assertEqual(destination_state(student,record),'unknown')
        row=build_cross_module_row(('2023级','国际关系'),build_cross_module_context())
        self.assertEqual(row['unknownDestinationCount'],1)
        self.assertEqual(row['destinationPendingCount'],0)
        self.assertEqual(row['unresolvedCount'],0)
