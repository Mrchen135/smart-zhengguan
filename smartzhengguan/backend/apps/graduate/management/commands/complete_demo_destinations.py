"""Apply the user-confirmed demonstration cohort policy with a reversible audit."""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.graduate.models import Student, EmploymentRecord
from apps.graduate.portrait import latest_destinations

FIELDS = ('graduation_year','destination_type','unit_nature','industry','province','employer_name','is_signed','is_further_study','status','data_source')

def graduation_date(student):
    # Confirmed policy: masters take three years; retain the existing four-year doctoral schedule.
    years = 4 if student.degree_type == 'doctoral' else 3
    return date(int(student.grade[:4]) + years, 6, 30)

def destination_values(student, category):
    common = dict(graduation_year=graduation_date(student).year, destination_type=category,
        unit_nature='',industry='',province='',employer_name='',is_signed=False,is_further_study=False,
        status='pending',data_source='demo_cohort_policy_v2')
    if category == '在读': return dict(common,status='in_progress')
    if category == '考公': return dict(common,status='in_progress',unit_nature='公务员考试准备')
    if category == '未知': return common
    digest=hashlib.sha256(('demo-employer-v2:'+student.student_id).encode()).digest()
    employers=[('模拟单位·公共服务中心','事业单位','公共管理'),('模拟单位·政策研究机构','科研机构','科学研究'),('模拟单位·咨询服务企业','民营企业','商务服务'),('模拟单位·城市运营企业','国有企业','城市服务')]
    employer,nature,industry=employers[digest[0]%len(employers)]
    province=['山东省','北京市','上海市','江苏省','浙江省','广东省'][digest[1]%6]
    return dict(common,status='completed',employer_name=employer,unit_nature=nature,industry=industry,province=province,is_signed=True)

class Command(BaseCommand):
    help='Normalize verified demo cohorts: 2023 masters graduated; doctoral schedule preserved; 2025 studying; graduate destinations employment/civil exam/unknown'
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--report',type=Path)
    def handle(self,*args,**options):
        today=timezone.localdate()
        students=list(Student.objects.all())
        unsupported=[s.student_id for s in students if not (s.gender_source=='demo_expansion_v1' or s.created_at.date()==date(2026,10,25))]
        if unsupported: raise CommandError(f'{len(unsupported)} non-demo students found; no writes performed')
        latest=latest_destinations(EmploymentRecord.objects.select_related('student').all())
        groups=defaultdict(list)
        categories={}
        for student in students:
            if graduation_date(student)>today or student.grade=='2025级': categories[student.pk]='在读'
            else: groups[student.grade].append(student)
        for grade,group in groups.items():
            ordered=sorted(group,key=lambda s:hashlib.sha256(('demo-destination-v2:'+s.student_id).encode()).hexdigest())
            unknown=max(1,round(len(group)*.03))
            civil=round(len(group)*.25)
            for index,student in enumerate(ordered):
                categories[student.pk]='未知' if index<unknown else '考公' if index<unknown+civil else '就业'
        student_changes,record_changes,changed_students,changed_records,new_records=[],[],[],[],[]
        for student in students:
            after={'current_status':'active' if categories[student.pk]=='在读' else 'graduated', 'expected_graduation_date':graduation_date(student)}
            before={k:getattr(student,k) for k in after}
            if before!=after:
                student_changes.append({'student_id':student.student_id,'before':before,'after':after})
                for key,value in after.items():setattr(student,key,value)
                student.updated_at=timezone.now();changed_students.append(student)
            record=latest.get(student.pk)
            values=destination_values(student,categories[student.pk])
            before={k:getattr(record,k) for k in FIELDS} if record else None
            if before!=values:
                record_changes.append({'record_id':record.pk if record else None,'student_id':student.student_id,'before':before,'after':values})
                if record:
                    for key,value in values.items():setattr(record,key,value)
                    record.updated_at=timezone.now();changed_records.append(record)
                else:new_records.append(EmploymentRecord(student=student,student_name=student.name,**values))
        report={'student_updates':len(student_changes),'destination_updates':len(record_changes),
            'counts':dict(Counter(categories.values())),
            'cohorts':{g:dict(Counter(categories[s.pk] for s in students if s.grade==g)) for g in sorted({s.grade for s in students})},
            'policy':'User-confirmed demo policy: 2023 masters graduated, doctoral four-year schedule preserved, 2025 studying; graduated cohorts approximately 72% employment, 25% civil-exam preparation, 3% unknown. Not observed outcomes.',
            'student_changes':student_changes,'destination_changes':record_changes}
        if options['apply']:
            with transaction.atomic():
                Student.objects.bulk_update(changed_students,['current_status','expected_graduation_date','updated_at'],batch_size=50)
                EmploymentRecord.objects.bulk_update(changed_records,list(FIELDS)+['updated_at'],batch_size=30)
                EmploymentRecord.objects.bulk_create(new_records)
        if options['report']:options['report'].write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        self.stdout.write(json.dumps({k:v for k,v in report.items() if k not in ('student_changes','destination_changes')},ensure_ascii=False))
