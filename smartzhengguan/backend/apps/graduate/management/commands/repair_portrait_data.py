"""Repair only verified expansion fixtures; persist explicit tracking, never fake placement."""
import hashlib
import json
from datetime import date
from pathlib import Path
from openpyxl import load_workbook
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.graduate.models import Student, EmploymentRecord
from apps.graduate.portrait import destination_state, DESTINATIONS


def demo_gender(student_id):
    return '男' if hashlib.sha256(('portrait-demo-v1:' + str(student_id)).encode()).digest()[0] % 2 == 0 else '女'


class Command(BaseCommand):
    help = 'Audit/repair known generated samples; --apply writes, --report saves the audit'
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--report', type=Path)
        parser.add_argument('--file', type=Path, default=settings.BASE_DIR.parent / '研究生数据_2021-2026.xlsx')

    def handle(self, *args, **options):
        workbook = load_workbook(options['file'], read_only=True, data_only=True)
        sheet = iter(workbook['智能预测-学生数据'].values)
        headers = next(sheet)
        fixture = {str(row['学号']): row for values in sheet if (row := dict(zip(headers, values))).get('学号')}
        workbook.close()
        changes, tracking, unresolved = [], [], []
        students = list(Student.objects.all())
        tracked = set(EmploymentRecord.objects.values_list('student_id', flat=True))
        for student in students:
            before, after = {}, {}
            if student.gender not in ('男', '女'):
                source = fixture.get(student.student_id)
                # The historical expansion used a dedicated serial range and timestamp.
                verified = (source and str(source['姓名']) == student.name and str(source['专业']) == student.major
                    and str(source['年级']) == student.grade and student.student_id.isdigit()
                    and len(student.student_id) == 10 and 1000 < int(student.student_id[-4:]) <= 4600
                    and student.created_at.date() == date(2026, 10, 26))
                if not verified:
                    unresolved.append(student.student_id)
                    continue
                before = {'gender': student.gender, 'gender_source': student.gender_source,
                          'expected_graduation_date': str(student.expected_graduation_date or '')}
                student.gender = demo_gender(student.student_id)
                student.gender_source = 'demo_expansion_v1'
                if not student.expected_graduation_date:
                    student.expected_graduation_date = date(int(student.grade[:4]) + (4 if student.degree_type == 'doctoral' else 3), 6, 30)
                after = {'gender': student.gender, 'gender_source': student.gender_source,
                         'expected_graduation_date': str(student.expected_graduation_date)}
                changes.append({'student_id': student.student_id, 'before': before, 'after': after})
            if student.pk not in tracked:
                state = destination_state(student)
                tracking.append(EmploymentRecord(student=student, student_name=student.name,
                    graduation_year=student.expected_graduation_date.year if student.expected_graduation_date else date.today().year,
                    destination_type=DESTINATIONS[state], status='draft'))
        report = {'gender_repairs': len(changes), 'tracking_created': len(tracking), 'unresolved': unresolved,
                  'source': 'Confirmed synthetic expansion fixtures; gender is simulated, not personal verification.', 'changes': changes}
        if unresolved and options['apply']:
            raise CommandError(f'{len(unresolved)} students require an authoritative gender source; no writes performed')
        if options['apply']:
            with transaction.atomic():
                repaired = {r['student_id'] for r in changes}
                Student.objects.bulk_update([s for s in students if s.student_id in repaired], ['gender', 'gender_source', 'expected_graduation_date'])
                EmploymentRecord.objects.bulk_create(tracking)
        if options['report']:
            options['report'].parent.mkdir(parents=True, exist_ok=True)
            options['report'].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(json.dumps({key: value for key, value in report.items() if key != 'changes'}, ensure_ascii=False))
