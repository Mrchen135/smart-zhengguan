"""Read-only portrait facts: counts, denominators and latest per-student records."""
from collections import Counter
from .portrait import latest_destinations,destination_state

def latest_rows(rows):
    result={}
    for row in sorted(rows,key=lambda r:(r.updated_at,r.pk),reverse=True):
        if row.student_id:result.setdefault(row.student_id,row)
    return result

def items(counter):return [{'name':name,'value':value} for name,value in counter.most_common() if name]

def cohort_facts(members,plans,degrees,snapshots,employment):
    plan_map=latest_rows(plans);snapshot_map={}
    for snapshot in sorted(snapshots,key=lambda r:(r.captured_at,r.updated_at,r.pk),reverse=True):
        snapshot_map.setdefault(snapshot.student_id,snapshot)
    snaps=list(snapshot_map.values());records=latest_destinations(employment)
    employed=[r for r in records.values() if r.student and destination_state(r.student,r)=='employment']
    def avg(field):return round(sum(float(getattr(r,field)) for r in snaps)/len(snaps),1) if snaps else None
    return {
        'graduatedCount':sum(s.current_status=='graduated' for s in members),
        'activeCount':sum(s.current_status=='active' for s in members),
        'snapshotCount':len(snaps), 'courseAverage':avg('course_average'),'creditCompletionRate':avg('credit_completion_rate'),
        'researchTaskCompletionRate':avg('research_task_completion_rate'),'attendanceRate':avg('attendance_rate'),
        'practiceHoursAverage':avg('practice_hours'),'advisorMeetingsAverage':avg('advisor_meeting_count_60d'),
        'researchOutputCount':sum(s.research_output_count for s in snaps),
        'overdueStudentCount':sum(s.overdue_tasks_count>0 and s.student.current_status!='graduated' for s in snaps),
        'trainingStages':items(Counter(p.stage for p in plan_map.values())),
        'sourceRegions':items(Counter(s.source_region for s in members)),
        'degreeTypes':items(Counter({'academic_master':'学术型硕士','professional_master':'专业型硕士','doctoral':'博士'}.get(s.degree_type,s.degree_type) for s in members)),
        'employmentIndustries':items(Counter(r.industry for r in employed)),
        'employmentRegions':items(Counter(r.province for r in employed)),
        'graduationDates':sorted({str(s.graduated_on) for s in members if s.graduated_on}),
        'expectedGraduationDates':sorted({str(s.expected_graduation_date) for s in members if s.expected_graduation_date and s.current_status!='graduated'}),
        'trainingObservedAverage':round(sum(p.completion_percent for p in plan_map.values())/len(plan_map),1) if plan_map else None,
        'degreeObservedAverage':avg('graduation_progress_rate'),
        'demoProfileCount':sum(s.profile_source.startswith('demo_') for s in members),
    }
