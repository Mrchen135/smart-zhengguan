from datetime import date
from io import StringIO
from django.test import TestCase
from django.core.management import call_command,CommandError
from apps.graduate.models import Student,ScholarshipAward,PredictionSnapshot
from apps.graduate.services import build_prediction_sources,serialize_prediction_student

class PortraitCompletionTests(TestCase):
    def student(self,sid,grade,status):
        return Student.objects.create(student_id=sid,name='演示样本',grade=grade,major='国际关系',
            gender='女',gender_source='demo_expansion_v1',degree_type='academic_master',advisor_name='演示导师',
            current_status=status,expected_graduation_date=date(int(grade[:4])+3,6,30))

    def test_completion_reconciles_lifecycle_awards_and_is_repeatable(self):
        graduate=self.student('demo001','2023级','graduated')
        active=self.student('demo002','2025级','active')
        award=ScholarshipAward.objects.create(student=active,award_year=2020,awarded_on=date(2020,5,20),amount=6000)
        call_command('complete_portrait_demo',apply=True,stdout=StringIO())
        graduate.refresh_from_db();active.refresh_from_db();award.refresh_from_db()
        self.assertEqual(graduate.graduated_on,date(2026,6,30))
        self.assertIsNone(active.graduated_on)
        self.assertEqual(active.required_credits,32)
        self.assertEqual(award.awarded_on,active.enrolled_on)
        self.assertEqual(award.award_year,2025)
        self.assertIsNone(active.degree_applications.get().awarded_at)
        self.assertEqual(graduate.degree_applications.get().award_status,'completed')
        self.assertEqual(graduate.prediction_snapshots.get().credit_completion_rate,100)
        self.assertLess(active.prediction_snapshots.get().training_plan_completion_rate,100)
        before=list(PredictionSnapshot.objects.order_by('pk').values('pk','captured_at','updated_at'))
        award_count=ScholarshipAward.objects.count()
        call_command('complete_portrait_demo',apply=True,stdout=StringIO())
        self.assertEqual(before,list(PredictionSnapshot.objects.order_by('pk').values('pk','captured_at','updated_at')))
        self.assertEqual(ScholarshipAward.objects.count(),award_count)
        payloads=[serialize_prediction_student(s) for s in build_prediction_sources()]
        self.assertEqual(len(payloads),2)
        self.assertEqual({p['recordKind'] for p in payloads},{'demonstration'})
        self.assertEqual({p['trainingStage'] for p in payloads},{'培养完成','课程与开题'})

    def test_real_records_are_never_filled_with_demo_values(self):
        student=Student.objects.create(student_id='real',name='Imported',gender='女',grade='2025级')
        with self.assertRaises(CommandError):call_command('complete_portrait_demo',apply=True,stdout=StringIO())
        student.refresh_from_db()
        self.assertIsNone(student.enrolled_on)
        self.assertEqual(PredictionSnapshot.objects.count(),0)
