"""Explicit, mutually exclusive destination tracking; never infer unemployment from absence."""
from collections import Counter
from django.utils import timezone

DESTINATIONS = {
    'employment': '就业', 'study': '升学', 'abroad': '出国出境',
    'civil_service': '考公', 'unknown': '未知',
    'flexible': '灵活就业', 'other': '其他已落实', 'unresolved': '暂未落实',
    'in_study': '在读', 'verify': '去向待核实', 'inactive': '学籍异动待跟进',
}
RESOLVED = {'employment', 'study', 'abroad', 'flexible', 'other'}


def destination_state(student, record=None, today=None):
    today = today or timezone.localdate()
    if record:
        label = (record.destination_type or '').strip()
        if label == '考公': return 'civil_service'
        if label == '未知': return 'unknown'
        if label in ('去向待核实', '待核实', ''):
            pass
        elif label in ('未就业', '待就业', '暂未落实', '求职中'):
            return 'unresolved'
        elif label == DESTINATIONS['inactive']:
            return 'inactive'
        elif label not in ('在读', '在读（暂不纳入）') and record.status in ('completed', 'approved'):
            if record.is_further_study or '升学' in label: return 'study'
            if '出国' in label or '出境' in label: return 'abroad'
            if '灵活' in label: return 'flexible'
            if label in ('就业', '单位就业', '签约就业', '协议就业', '合同就业'): return 'employment'
            if label in ('自主创业', '自由职业', '其他已落实'): return 'other'
            return 'verify'
    if student.current_status in ('withdrawn', 'suspended', 'other'):
        return 'inactive'
    if student.expected_graduation_date and student.expected_graduation_date > today:
        return 'in_study'
    return 'verify'


def latest_destinations(records):
    result = {}
    for item in sorted(records, key=lambda r: (r.graduation_year, r.updated_at, r.pk), reverse=True):
        if item.student_id: result.setdefault(item.student_id, item)
    return result


def summarize_destinations(students, records):
    latest = latest_destinations(records)
    counts = Counter(destination_state(s, latest.get(s.pk)) for s in students)
    return [{'key': key, 'label': label, 'count': counts[key]} for key, label in DESTINATIONS.items()]
