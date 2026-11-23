"""Deterministic reconciliation of verified demo fixtures. Never invent personal facts."""
import json
from collections import Counter, defaultdict
from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import (Student, AcademicStatusEvent, AcademicChangeRequest, TrainingPlan, DegreeApplication,
    EmploymentRecord, PredictionSnapshot, PredictionMonthlyMetric, HomeAnnualSummary, HomeGradeMajorSummary,
    HomeSourceRegionSummary, DataRepairArchive)
from .portrait import latest_destinations

SOURCE = 'demo_reconciled_v1'

def snapshot(row):
    return json.loads(serializers.serialize('json', [row]))[0]


def reconcile(apply=False, batch_id=''):
    students = list(Student.objects.all())
    if not students or any(not s.profile_source.startswith('demo_') for s in students):
        raise ValidationError('仅处理已标明来源的演示库；发现非演示档案时停止，避免改写真正业务事实。')
    by_id = {s.pk:s for s in students}
    today = timezone.localdate()
    archives, updates, creates = {}, {}, []

    def archive(row, reason, canonical=None):
        key = (row._meta.label, row.pk)
        if key not in archives:
            archives[key] = (row, reason, canonical)
            updates.pop(key, None)

    def update(row, changes, reason):
        key = (row._meta.label, row.pk)
        if key in archives: return
        changed = {k:v for k,v in changes.items() if getattr(row,k) != v}
        if changed:
            previous = updates.get(key)
            updates[key] = (row, {**(previous[1] if previous else {}), **changed}, reason)

    def exact_duplicates(model):
        fields = [f.attname for f in model._meta.concrete_fields if f.name not in ('id','created_at','updated_at')]
        groups = defaultdict(list)
        for row in model.objects.all(): groups[tuple(getattr(row,f) for f in fields)].append(row)
        for members in groups.values():
            if len(members)<2: continue
            keep = max(members,key=lambda r:(r.updated_at,r.pk))
            for row in members:
                if row.pk != keep.pk: archive(row,'完全相同业务字段归并，保留最新记录',keep.pk)

    exact_duplicates(TrainingPlan)
    exact_duplicates(DegreeApplication)

    latest = latest_destinations(EmploymentRecord.objects.select_related('student').all())
    keep_jobs = {r.pk for r in latest.values()}
    for row in EmploymentRecord.objects.all():
        if row.pk not in keep_jobs and row.student_id in by_id and not row.data_source:
            archive(row,'无来源标记的旧演示去向已被个人最新记录取代',latest[row.student_id].pk)

    snaps = {r.pk:r for r in PredictionSnapshot.objects.all()}
    for row in PredictionMonthlyMetric.objects.all():
        snap = snaps[row.snapshot_id]
        s = by_id[snap.student_id]
        end = timezone.localtime(snap.captured_at).strftime('%Y-%m')
        if s.graduated_on: end = min(end,s.graduated_on.strftime('%Y-%m'))
        if row.month > end or (s.enrolled_on and row.month < s.enrolled_on.strftime('%Y-%m')):
            archive(row,'月度观测超出本人入学至归档/毕业时间范围')

    events = list(AcademicStatusEvent.objects.select_related('student').order_by('pk'))
    requests = list(AcademicChangeRequest.objects.select_related('student').order_by('pk'))
    # Legacy importer emitted the event and request arrays in identical order.
    pairs = []
    legacy_events = [r for r in events if r.reason == f'{r.change_type}业务导入记录' and not r.data_source]
    legacy_requests = [r for r in requests if r.remark == f'Excel 导入生成的{r.change_type}申请' and not r.data_source]
    if legacy_events or legacy_requests:
        if len(legacy_events)!=len(legacy_requests) or any((a.student_id,a.change_type)!=(b.student_id,b.change_type) for a,b in zip(legacy_events,legacy_requests)):
            raise ValidationError('旧学籍事件与申请无法逐条对齐，停止修复；需先核对关联。')
        pairs = list(zip(legacy_events,legacy_requests))

    def outside(row, day):
        s = by_id.get(row.student_id)
        return not s or (s.enrolled_on and day<s.enrolled_on) or (s.graduated_on and day>s.graduated_on)

    for event,request in pairs:
        if outside(event,event.occurred_on) or outside(request,timezone.localtime(request.submitted_at).date()):
            for row in (event,request): archive(row,'旧汇总展开的个人异动不在本人在校时间范围内，原始记录留档')
        elif by_id[event.student_id].current_status=='graduated' and (event.status in ('pending','draft','in_progress') or request.status in ('pending','draft','in_progress')):
            for row in (event,request): archive(row,'已毕业对象仍挂未结的旧演示异动，缺少结案依据，转入历史归档')

    # Keep the principal lifecycle intact: an unsupported chain must not change a student's status.
    final_events = {}
    for row in sorted(legacy_events,key=lambda r:(r.occurred_on,r.pk)):
        if (row._meta.label,row.pk) not in archives and row.status in ('approved','completed'):
            final_events[row.student_id] = row
    bad_students = set()
    for sid,row in final_events.items():
        s=by_id[sid]
        expected={'退学':'withdrawn','休学':'suspended','复学':'active','延期毕业':'extended'}.get(row.change_type)
        graduated_after = s.current_status=='graduated' and row.change_type in ('复学','延期毕业') and row.occurred_on<=s.graduated_on
        if expected and s.current_status!=expected and not graduated_after: bad_students.add(sid)
    for event,request in pairs:
        if event.student_id in bad_students:
            for row in (event,request): archive(row,'旧演示异动链与现有主档状态冲突且缺后续审批依据，整组留档')
        for row in (event,request):
            if (row._meta.label,row.pk) not in archives:
                update(row,{'data_source':SOURCE},'为保留的演示学籍记录补充来源标记')
        if (event._meta.label,event.pk) not in archives and event.status!=request.status:
            update(event,{'status':request.status,'status_tag':request.status_type},'申请未审批完成时，事件同步保持申请的处理状态')

    for s in students:
        if s.is_international and s.enrollment_type!='international':
            update(s,{'enrollment_type':'international'},'按已存在的国际生标记统一招生类型，学位层次保留')
        elif s.enrollment_type=='international' and not s.is_international:
            update(s,{'is_international':True},'按已存在的国际招生类型统一国际生标记')

    members = defaultdict(list)
    for s in students: members[(s.grade,s.major)].append(s)
    existing_groups = {(r.grade,r.major):r for r in HomeGradeMajorSummary.objects.all()}
    for key,group in members.items():
        values={'total_count':len(group),'male_count':sum(s.gender=='男' for s in group),'female_count':sum(s.gender=='女' for s in group)}
        if key in existing_groups: update(existing_groups[key],values,'按全部学生主档重算年级专业汇总')
        else: creates.append((HomeGradeMajorSummary,{'grade':key[0],'major':key[1],**values},'根据学生档案建立年级专业汇总'))
    for key,row in existing_groups.items():
        if key not in members: archive(row,'汇总组合在当前学生档案中不存在')
    sources = Counter(s.source_region or '未知' for s in students)
    existing_sources = {r.region:r for r in HomeSourceRegionSummary.objects.all()}
    for name,count in sources.items():
        values={'student_count':count,'percent_text':f'{count*100/len(students):.1f}%'}
        if name in existing_sources: update(existing_sources[name],values,'按全部学生主档重算生源人数及占比')
        else: creates.append((HomeSourceRegionSummary,{'region':name,**values},'补齐学生档案中存在的生源地区'))
    for key,row in existing_sources.items():
        if key not in sources: archive(row,'生源汇总地区在当前学生档案中不存在')
    active=[s for s in students if s.current_status=='active']
    current={'total_students':len(active),'master_count':sum(s.degree_type!='doctoral' for s in active),
             'doctor_count':sum(s.degree_type=='doctoral' for s in active),
             'international_count':sum(s.is_international or s.enrollment_type=='international' for s in active),
             'annual_graduates':sum(bool(s.graduated_on) and s.graduated_on.year==today.year for s in students)}
    annual=HomeAnnualSummary.objects.filter(year=today.year).first()
    if annual:update(annual,current,'当年汇总按当前库内在读及本年毕业档案重算')
    else:creates.append((HomeAnnualSummary,{'year':today.year,**current},'新建当年库内学生汇总，保留过去年度历史值'))

    report={'batchId':batch_id,'apply':apply,'asOf':str(today),
            'archiveByModel':dict(Counter(row._meta.label for row,_,_ in archives.values())),
            'archiveReasons':dict(Counter(reason for _,reason,_ in archives.values())),
            'updateByModel':dict(Counter(row._meta.label for row,_,_ in updates.values())),
            'createByModel':dict(Counter(m._meta.label for m,_,_ in creates)),
            'archiveCount':len(archives),'updateCount':len(updates),'createCount':len(creates),
            'studentCount':len(students),'activeCount':len(active),'graduatedCount':sum(s.current_status=='graduated' for s in students),
            'unresolved':'姓名占位、未提供精确截止时刻的招聘公告保留原文和来源，不猜测。'}
    if not apply:return report
    if not batch_id:raise ValidationError('写入修复必须提供批次号。')
    if DataRepairArchive.objects.filter(batch_id=batch_id).exists():raise ValidationError('修复批次已存在。')
    with transaction.atomic():
        # Serialize and retain every removed row before changing active tables.
        DataRepairArchive.objects.bulk_create([DataRepairArchive(batch_id=batch_id,model_label=row._meta.label,
            original_pk=row.pk,action='archive',reason=reason,canonical_pk=canonical,original=snapshot(row))
            for row,reason,canonical in archives.values()],batch_size=250)
        delete_ids=defaultdict(list)
        for row,_,_ in archives.values():delete_ids[type(row)].append(row.pk)
        for model,ids in delete_ids.items():
            for start in range(0,len(ids),400):model.objects.filter(pk__in=ids[start:start+400]).delete()
        for row,values,reason in updates.values():
            original=snapshot(row)
            for key,value in values.items():setattr(row,key,value)
            row.save(update_fields=[*values,'updated_at'])
            DataRepairArchive.objects.create(batch_id=batch_id,model_label=row._meta.label,original_pk=row.pk,
                action='update',reason=reason,original=original,after=snapshot(row))
        for model,values,reason in creates:
            row=model.objects.create(**values)
            DataRepairArchive.objects.create(batch_id=batch_id,model_label=row._meta.label,original_pk=row.pk,
                action='create',reason=reason,after=snapshot(row))
    return report


def reconcile_doctoral_cohort(apply=False, batch_id=''):
    """Undo the obsolete whole-2023 three-year fixture rule after user clarification."""
    from datetime import datetime
    from .management.commands.complete_demo_destinations import graduation_date, destination_values
    from .management.commands.complete_portrait_demo import seed
    today = timezone.localdate()
    students = [s for s in Student.objects.filter(grade='2023级', degree_type='doctoral')
                if graduation_date(s) > today and (s.current_status == 'graduated' or s.expected_graduation_date != graduation_date(s))]
    if any(not s.profile_source.startswith('demo_') for s in students):
        raise ValidationError('发现非演示博士档案，停止自动调整学制。')
    report = {'batchId': batch_id, 'apply': apply, 'students': len(students),
              'policy': '仅硕士按三年制；博士沿用原有四年制，2023级博士预计2027年毕业。'}
    if not apply or not students:
        return report
    if not batch_id or DataRepairArchive.objects.filter(batch_id=batch_id).exists():
        raise ValidationError('请使用未执行过的修复批次。')
    counts = Counter()

    def amend(row, values, reason):
        changed = {key: value for key, value in values.items() if getattr(row, key) != value}
        if not changed:
            return
        original = snapshot(row)
        for key, value in changed.items():
            setattr(row, key, value)
        row.save(update_fields=[*changed, 'updated_at'])
        DataRepairArchive.objects.create(batch_id=batch_id, model_label=row._meta.label,
            original_pk=row.pk, action='update', reason=reason, original=original, after=snapshot(row))
        counts[row._meta.label] += 1

    with transaction.atomic():
        for student in students:
            grad = graduation_date(student)
            d = seed(student)
            training = 80 + d[0] % 15
            amend(student, {'current_status': 'active', 'graduated_on': None, 'expected_graduation_date': grad},
                  '用户确认仅硕士为三年制；撤销博士错误毕业标记，沿用四年制预计毕业日期')
            for plan in student.training_plans.all():
                amend(plan, {'stage': '论文研究', 'status': 'in_progress', 'status_tag': 'primary',
                    'completion_percent': training, 'business_updated_at': today},
                    '修正博士为在读后，恢复对应的演示培养阶段')
            for degree in student.degree_applications.all():
                amend(degree, {'application_year': grad.year, 'paper_submitted_at': None,
                    'paper_review_result': '未到评阅阶段', 'defense_result': '未到答辩阶段',
                    'award_status': 'draft', 'awarded_at': None}, '撤销三年制误用产生的博士授位演示记录')
            latest = latest_destinations(student.employment_records.select_related('student').all()).get(student.pk)
            if latest:
                amend(latest, destination_values(student, '在读'), '博士未毕业，当前去向应为在读，清除错误就业单位与签约标记')
            for snap in student.prediction_snapshots.all():
                amend(snap, {'captured_at': timezone.make_aware(datetime.combine(today, datetime.min.time())),
                    'credit_completion_rate': 100, 'training_plan_completion_rate': training,
                    'graduation_progress_rate': 85, 'risk_level': 'low' if snap.overdue_tasks_count == 0 else 'medium',
                    'risk_type': '培养进度', 'risk_field': '培养节点',
                    'suggestion': '按博士论文研究阶段确认送审准备与下一项任务的交付日期。'},
                    '恢复在读博士演示快照；阶段指标为演示值，不能视作真实测评')
                old_months = list(snap.monthly_metrics.all())
                DataRepairArchive.objects.bulk_create([DataRepairArchive(batch_id=batch_id,
                    model_label=row._meta.label, original_pk=row.pk, action='archive',
                    reason='撤销错误毕业状态生成的演示月度序列，原值留档', original=snapshot(row)) for row in old_months])
                snap.monthly_metrics.all().delete()
                fresh = []
                for i in range(6):
                    ordinal = today.year * 12 + today.month - 1 - (5 - i)
                    year, month = divmod(ordinal, 12)
                    progress = (5 - i) * 3
                    fresh.append(PredictionMonthlyMetric(snapshot=snap, month=f'{year:04d}-{month+1:02d}',
                        course_average=max(0, float(snap.course_average)-progress*.25),
                        credit_completion_rate=100-progress, attendance_rate=snap.attendance_rate,
                        research_task_completion_rate=max(0, float(snap.research_task_completion_rate)-progress),
                        activity_hours=snap.activity_hours//6, practice_hours=snap.practice_hours//6,
                        advisor_meeting_count=max(1, snap.advisor_meeting_count_60d//2),
                        advisor_evaluation_score=snap.advisor_evaluation_score, wellbeing_score=snap.wellbeing_score))
                PredictionMonthlyMetric.objects.bulk_create(fresh)
                DataRepairArchive.objects.bulk_create([DataRepairArchive(batch_id=batch_id,
                    model_label=row._meta.label, original_pk=row.pk, action='create',
                    reason='为修正后的在读博士演示快照建立最近六个月序列', after=snapshot(row)) for row in fresh])
                counts['monthlyArchived'] += len(old_months)
                counts['monthlyCreated'] += len(fresh)
        report['summaryReconciliation'] = reconcile(apply=True, batch_id=batch_id+'-summary')
    report['changed'] = dict(counts)
    return report
