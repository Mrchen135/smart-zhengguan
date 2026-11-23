"""Complete verified demo records and reconcile lifecycle facts across portrait modules."""
import hashlib,json,calendar
from collections import defaultdict,Counter
from datetime import date,datetime,timedelta
from pathlib import Path
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from apps.graduate.models import Student,TrainingPlan,DegreeApplication,ScholarshipAward,PredictionSnapshot,PredictionMonthlyMetric,EmploymentRecord
from .complete_demo_destinations import graduation_date

SOURCE='demo_portrait_v3'
def seed(s): return hashlib.sha256(('portrait-v3:'+s.student_id).encode()).digest()
def group(model):
    rows=defaultdict(list)
    for row in model.objects.all():rows[row.student_id].append(row)
    return rows

def audit():
    students=Student.objects.all()
    return {'students':students.count(),'gender_missing':students.exclude(gender__in=['男','女']).count(),
       'origin_missing':students.filter(source_region='').count(),'advisor_missing':students.filter(advisor_name='').count(),
       'enrollment_missing':students.filter(enrolled_on__isnull=True).count(),'credits_missing':students.filter(required_credits=0).count(),
       'training_missing':students.filter(training_plans__isnull=True).count(),'degree_missing':students.filter(degree_applications__isnull=True).count(),
       'snapshot_missing':students.filter(prediction_snapshots__isnull=True).count(),'destination_missing':students.filter(employment_records__isnull=True).count(),
       'graduates_without_award':students.filter(current_status='graduated').exclude(degree_applications__award_status='completed').count(),
       'active_with_award':students.filter(current_status='active',degree_applications__awarded_at__isnull=False).distinct().count(),
       'award_before_enrollment':ScholarshipAward.objects.filter(awarded_on__lt=F('student__enrolled_on')).count(),
       'award_after_graduation':ScholarshipAward.objects.filter(student__current_status='graduated',awarded_on__gt=F('student__graduated_on')).count(),
       'award_date_missing':ScholarshipAward.objects.filter(awarded_on__isnull=True).count()}

class Command(BaseCommand):
    help='Complete synthetic portrait data, retaining source flags; audit-only unless --apply'
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true');parser.add_argument('--report',type=Path)
    def handle(self,*args,**options):
        before=audit()
        if not options['apply']:
            self.stdout.write(json.dumps(before,ensure_ascii=False));return
        students=list(Student.objects.all())
        if any(s.gender_source!='demo_expansion_v1' and s.created_at.date()!=date(2026,10,25) and s.profile_source!=SOURCE for s in students):
            raise CommandError('Unverified non-demo student detected; no writes performed')
        plans,degrees,awards,snaps=(group(m) for m in [TrainingPlan,DegreeApplication,ScholarshipAward,PredictionSnapshot])
        changed=Counter();today=timezone.localdate()
        with transaction.atomic():
            for s in students:
                # An unchanged completed fixture needs no repeated historical rewrites.
                if s.profile_source==SOURCE and plans[s.pk] and degrees[s.pk] and snaps[s.pk]:continue
                d=seed(s);graduated=s.current_status=='graduated';grad=graduation_date(s)
                captured=min(today,grad) if graduated else today
                at=timezone.make_aware(datetime.combine(captured,datetime.min.time()))
                training=100 if graduated else (65+d[0]%20 if s.grade=='2024级' else 32+d[0]%20)
                credit=100 if graduated else (90+d[1]%11 if s.grade=='2024级' else 55+d[1]%25)
                stage='培养完成' if graduated else ('论文研究' if s.grade=='2024级' else '课程与开题')
                advanced_doctor = not graduated and s.degree_type=='doctoral' and s.grade=='2023级'
                if advanced_doctor: training,credit,stage=80+d[0]%15,100,'论文研究'
                s.enrolled_on=date(int(s.grade[:4]),9,1);s.graduated_on=grad if graduated else None
                s.required_credits=18 if s.degree_type=='doctoral' else 32
                if not s.source_region:s.source_region=['山东','河南','河北','江苏','安徽','浙江','山西','湖北'][d[2]%8]
                s.profile_source=SOURCE;s.save(update_fields=['enrolled_on','graduated_on','required_credits','source_region','profile_source','updated_at']);changed['student_profiles']+=1
                values=dict(student_name=s.name,grade=s.grade,major=s.major,degree_type=s.degree_type,advisor_name=s.advisor_name,
                    stage=stage,status='completed' if graduated else 'in_progress',status_tag='success' if graduated else 'primary',
                    completion_percent=training,business_updated_at=captured,data_source=SOURCE)
                if plans[s.pk]:
                    TrainingPlan.objects.filter(pk__in=[r.pk for r in plans[s.pk]]).update(**values);changed['training_updated']+=len(plans[s.pk])
                else:TrainingPlan.objects.create(student=s,**values);changed['training_created']+=1
                values=dict(student_name=s.name,application_year=grad.year,application_type='博士学位' if s.degree_type=='doctoral' else '硕士学位',discipline=s.major,
                    paper_submitted_at=grad-timedelta(days=60) if graduated else None,paper_review_result='通过' if graduated else '未到评阅阶段',
                    defense_result='通过' if graduated else '未到答辩阶段',award_status='completed' if graduated else 'draft',awarded_at=grad if graduated else None,data_source=SOURCE)
                if degrees[s.pk]:DegreeApplication.objects.filter(pk__in=[r.pk for r in degrees[s.pk]]).update(**values);changed['degree_updated']+=len(degrees[s.pk])
                else:DegreeApplication.objects.create(student=s,**values);changed['degree_created']+=1
                if not awards[s.pk] and d[3]%10<7:
                    ScholarshipAward.objects.create(student=s,student_name=s.name,award_year=captured.year,grade=s.grade,major=s.major,
                        award_category='scholarship',award_type='学业奖学金',award_name='学业奖学金（演示）',amount=6000+(d[4]%3)*2000,
                        awarded_on=min(captured,date(captured.year,5,20)),data_source=SOURCE);changed['awards_created']+=1
                # Preserve measured-looking original course/research values; reconcile stage-dependent fields.
                snapshot=sorted(snaps[s.pk],key=lambda r:(r.captured_at,r.pk),reverse=True)[0] if snaps[s.pk] else None
                if not snapshot:
                    snapshot=PredictionSnapshot(student=s,course_average=76+d[5]%20,attendance_rate=91+d[6]%10,
                       research_task_completion_rate=72+d[7]%26,research_output_count=d[8]%5,project_participation_count=1+d[9]%4,
                       activity_hours=12+d[10]%60,activity_count=2+d[11]%9,practice_hours=24+d[12]%80,practice_report_count=1+d[13]%4,
                       advisor_evaluation_score=78+d[14]%20,advisor_meeting_count_60d=2+d[15]%7,advisor_avg_response_days=1+d[16]%5,
                       missed_checkins=0,wellbeing_score=85,overdue_tasks_count=0 if graduated else d[17]%3)
                    changed['snapshots_created']+=1
                else:changed['snapshots_updated']+=1
                snapshot.data_source=SOURCE;snapshot.sample_range='近6个月';snapshot.captured_at=at
                snapshot.credit_completion_rate=credit;snapshot.training_plan_completion_rate=training
                snapshot.graduation_progress_rate=100 if graduated else (85 if advanced_doctor else 65 if s.grade=='2024级' else 35)
                if graduated:snapshot.research_task_completion_rate=100;snapshot.overdue_tasks_count=0;snapshot.missed_checkins=0
                snapshot.risk_level='low' if graduated or snapshot.overdue_tasks_count==0 else 'medium'
                snapshot.risk_type='已毕业归档' if graduated else '培养进度';snapshot.risk_field='已毕业归档' if graduated else '培养节点'
                snapshot.suggestion='已完成培养，关注职业发展与校友联系。' if graduated else '按培养阶段确认下一项任务与交付日期。'
                snapshot.save()
                # Reconcile six synthetic monthly points; archived students stop at graduation.
                old_months={r.month:r for r in snapshot.monthly_metrics.all()}
                months=[]
                for i in range(6):
                    ordinal=captured.year*12+captured.month-1-(5-i);year,month=divmod(ordinal,12);label=f'{year:04d}-{month+1:02d}';months.append(label)
                    progress=(5-i)*3
                    values=dict(course_average=max(0,float(snapshot.course_average)-progress*.25),credit_completion_rate=max(0,credit-progress),
                        attendance_rate=float(snapshot.attendance_rate),research_task_completion_rate=max(0,float(snapshot.research_task_completion_rate)-progress),
                        activity_hours=max(0,snapshot.activity_hours//6),practice_hours=max(0,snapshot.practice_hours//6),advisor_meeting_count=max(1,snapshot.advisor_meeting_count_60d//2),
                        advisor_evaluation_score=float(snapshot.advisor_evaluation_score),wellbeing_score=float(snapshot.wellbeing_score))
                    PredictionMonthlyMetric.objects.update_or_create(snapshot=snapshot,month=label,defaults=values)
                # Existing out-of-window observations remain available as historical records.
            # Legacy fixtures included awards outside enrollment; reconcile only verified demo records.
            by_id={s.pk:s for s in students}
            fixed=[]
            for award in ScholarshipAward.objects.all():
                student=by_id.get(award.student_id)
                if not student:continue
                end=student.graduated_on or today
                original=award.awarded_on or date(award.award_year,5,20)
                award_date=min(max(original,student.enrolled_on),end)
                if award.awarded_on==award_date and award.award_year==award_date.year and award.data_source==SOURCE:continue
                award.awarded_on=award_date;award.award_year=award_date.year;award.data_source=SOURCE
                fixed.append(award)
            ScholarshipAward.objects.bulk_update(fixed,['awarded_on','award_year','data_source'],batch_size=100)
            changed['award_dates_reconciled']=len(fixed)
            after=audit()
        report={'before':before,'after':after,'changed':dict(changed),'source':SOURCE,
            'not_applicable':'在读学生的授位日期和论文提交日期可为空；考公/未知/在读不填虚构就业单位；未获奖学生奖助记录为零。',
            'history':'All generated fields and monthly metrics are synthetic demonstration values; backup retains pre-repair history.'}
        if options['report']:options['report'].write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(report,ensure_ascii=False))
