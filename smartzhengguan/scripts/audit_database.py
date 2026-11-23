"""Read-only database audit. Run through manage.py shell with AUDIT_SNAPSHOT/OUTPUT globals."""
import json, re, math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from django.apps import apps
from django.db import connection, connections, models
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

if globals().get('AUDIT_SNAPSHOT'):
    connections.close_all()
    connection.settings_dict['NAME'] = str(AUDIT_SNAPSHOT)
TODAY = globals().get('AUDIT_AS_OF') or timezone.localdate()
APP_LABELS = {'graduate', 'employmenthub', 'common', 'accounts'}
issues, checks, inventory = [], [], []
data = {}

def check(code, title, table, rows, *, severity='error', note='', details=None):
    ids = sorted({r['id'] if isinstance(r, dict) else r for r in rows})
    item = {'code': code, 'title': title, 'table': table, 'count': len(ids), 'severity': severity, 'note': note}
    if details is not None: item['details'] = details
    checks.append({k:v for k,v in item.items() if k != 'details'})
    if ids or details:
        item['ids'] = ids
        issues.append(item)

def grouped_duplicate(rows, fields):
    groups = defaultdict(list)
    for r in rows: groups[tuple(r.get(k) for k in fields)].append(r['id'])
    return [g for g in groups.values() if len(g)>1]

def duplicate(code, title, model, fields, severity='review', note=''):
    groups = grouped_duplicate(data[model], fields)
    check(code,title,model,[i for g in groups for i in g],severity=severity,note=note,
          details={'groups':len(groups),'extraRows':sum(len(g)-1 for g in groups),'examples':groups[:12]} if groups else None)

with connection.cursor() as cursor:
    cursor.execute('PRAGMA query_only = ON')
    cursor.execute('PRAGMA integrity_check'); integrity = [r[0] for r in cursor.fetchall()]
    cursor.execute('PRAGMA foreign_key_check'); foreign_keys = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'");physical_tables=cursor.fetchone()[0]
executor=MigrationExecutor(connection)
pending=[m.name for m,_ in executor.migration_plan(executor.loader.graph.leaf_nodes())]
for model in apps.get_models():
    label=model._meta.label
    count=model.objects.count()
    inventory.append({'model':label,'table':model._meta.db_table,'rows':count})
    if model._meta.app_label not in APP_LABELS: continue
    # Never include passwords or account credentials in the report.
    selected=[f.attname for f in model._meta.concrete_fields if f.name not in ('password',)]
    rows=list(model.objects.values(*selected))
    data[model.__name__]=rows
    for f in model._meta.concrete_fields:
        key=f.attname
        if f.name=='password': continue
        if not f.null and not f.blank and isinstance(f,(models.CharField,models.TextField)):
            check(f'{model.__name__}.{key}.required','必填文本为空',label,[r for r in rows if not str(r.get(key) or '').strip()])
        if f.choices:
            allowed={x for x,_ in f.flatchoices}
            check(f'{model.__name__}.{key}.choice','字段值不在允许枚举中',label,[r for r in rows if r.get(key) not in allowed and r.get(key) not in (None,'')])
        if isinstance(f,models.CharField) and f.max_length:
            check(f'{model.__name__}.{key}.length','文本超出模型长度',label,[r for r in rows if r.get(key) and len(str(r[key]))>f.max_length])
        if isinstance(f,(models.PositiveIntegerField,models.PositiveSmallIntegerField,models.PositiveBigIntegerField)) or key=='amount':
            check(f'{model.__name__}.{key}.negative','非负字段出现负数',label,[r for r in rows if r.get(key) is not None and r[key]<0])
        if key != 'max_score' and (key.endswith(('_percent','_rate','_score')) or key in ('course_average','admission_rate')):
            if isinstance(f,(models.DecimalField,models.IntegerField)):
                check(f'{model.__name__}.{key}.range','百分比/百分制指标越界',label,[r for r in rows if r.get(key) is not None and not 0<=r[key]<=100])
    check(model.__name__+'.timestamp_order','更新时间早于创建时间',label,[r for r in rows if r.get('created_at') and r.get('updated_at') and r['updated_at']<r['created_at']])

students={r['id']:r for r in data['Student']}
S=list(students.values())
for field in ['student_id','name','gender','college','major','grade','degree_type','source_region','advisor_name','enrolled_on','expected_graduation_date','profile_source']:
    check('student.required.'+field,'学生核心字段缺漏：'+field,'Student',[s for s in S if s.get(field) in ('',None)])
check('student.credits','要求学分为零','Student',[s for s in S if not s['required_credits']])
check('student.placeholder_names','学生姓名为扩增占位符','Student',[s for s in S if re.match(r'^(学生|同学|student|测试|演示学生)[- _\d]*$',s['name'],re.I)],severity='review',note='演示库可保留占位符；不能当成实际学生姓名。')
check('student.degree_enrollment','学位类型与招生类型矛盾','Student',[s for s in S if s['enrollment_type']!='international' and ((s['degree_type']=='doctoral')!=(s['enrollment_type']=='doctoral'))])
check('student.international','国际生标记与招生类型不一致','Student',[s for s in S if s['is_international']!=(s['enrollment_type']=='international')],severity='review')
check('student.grade_enrollment','年级与入学年份不一致','Student',[s for s in S if s['enrolled_on'] and s['grade'][:4].isdigit() and int(s['grade'][:4])!=s['enrolled_on'].year])
check('student.date_order','毕业/预计毕业不晚于入学','Student',[s for s in S if s['enrolled_on'] and any(d and d<=s['enrolled_on'] for d in [s['graduated_on'],s['expected_graduation_date']])])
check('student.graduated_date','已毕业缺实际毕业日期或毕业日在未来','Student',[s for s in S if s['current_status']=='graduated' and (not s['graduated_on'] or s['graduated_on']>TODAY)])
check('student.active_graduated','在读状态却有已发生的实际毕业日期','Student',[s for s in S if s['current_status']=='active' and s['graduated_on'] and s['graduated_on']<=TODAY])
check('student.2023','2023级硕士未按约定设置为毕业','Student',[s for s in S if s['grade']=='2023级' and s['degree_type']!='doctoral' and s['current_status']!='graduated'])
check('student.2025','2025级未全部设置为在读','Student',[s for s in S if s['grade']=='2025级' and s['current_status']!='active'])
check('student.masters_duration','硕士预计毕业年份不符合三年制','Student',[s for s in S if s['degree_type']!='doctoral' and s['enrolled_on'] and s['expected_graduation_date'] and s['expected_graduation_date'].year!=s['enrolled_on'].year+3])
check('student.doctoral_duration','演示博士预计毕业年份不符合原有四年制','Student',[s for s in S if s['profile_source'].startswith('demo_') and s['degree_type']=='doctoral' and s['enrolled_on'] and s['expected_graduation_date'] and s['expected_graduation_date'].year!=s['enrolled_on'].year+4])

related=['AcademicStatusEvent','AcademicChangeRequest','TrainingPlan','DegreeApplication','ScholarshipAward','EmploymentRecord','PredictionSnapshot']
for name in related:
    rows=data[name]
    check(name+'.unlinked','业务记录没有关联学生档案',name,[r for r in rows if not r.get('student_id')],severity='review',note='可空外键不一定违法，但这类记录不能可靠参与个人画像。')
    for field,target in [('student_name','name'),('grade','grade'),('major','major'),('degree_type','degree_type'),('advisor_name','advisor_name')]:
        if rows and field in rows[0]:
            check(name+'.mirror.'+field,'业务冗余字段与学生主档不一致：'+field,name,[r for r in rows if r.get('student_id') in students and r.get(field)!=students[r['student_id']][target]],note='历史专业/导师变更应保留依据；字段不应无解释地与主档冲突。')
    if name in ['TrainingPlan','DegreeApplication','EmploymentRecord','PredictionSnapshot']:
        linked={r.get('student_id') for r in rows}
        check(name+'.coverage','学生缺少核心业务记录：'+name,'Student',[s for s in S if s['id'] not in linked])

for name,fields in [('TrainingPlan',['student_id','grade','major','degree_type','stage','status','completion_percent','business_updated_at']),('DegreeApplication',['student_id','application_year','application_type','discipline','paper_submitted_at','paper_review_result','defense_result','award_status','awarded_at']),('EmploymentRecord',['student_id','graduation_year']),('ScholarshipAward',['student_id','award_year','award_category','award_type','award_name','amount','awarded_on'])]:
    duplicate(name+'.duplicate','重复业务记录',name,fields,note='列出相同业务键/值的组；未直接删除，以免误删多笔合法发放或历史版本。')

def student_of(r):return students.get(r.get('student_id'))
def before_enrollment(r,dt):
    s=student_of(r)
    return bool(s and s['enrolled_on'] and dt and dt<s['enrolled_on'])
def after_graduation(r,dt):
    s=student_of(r)
    return bool(s and s['graduated_on'] and dt and dt>s['graduated_on'])
for name,key in [('AcademicStatusEvent','occurred_on'),('AcademicChangeRequest','submitted_at'),('TrainingPlan','business_updated_at'),('ScholarshipAward','awarded_on'),('DegreeApplication','paper_submitted_at')]:
    convert=lambda v:v.date() if isinstance(v,datetime) else v
    check(name+'.before_enrollment','业务日期早于入学',name,[r for r in data[name] if before_enrollment(r,convert(r.get(key)))])
    check(name+'.after_graduation','在校业务日期晚于实际毕业',name,[r for r in data[name] if after_graduation(r,convert(r.get(key)))],severity='review')

check('academic.review_order','学籍审核日期早于提交日期','AcademicChangeRequest',[r for r in data['AcademicChangeRequest'] if r['reviewed_at'] and r['reviewed_at']<r['submitted_at']])
check('academic.closed_no_review','已审批异动缺审核时间','AcademicChangeRequest',[r for r in data['AcademicChangeRequest'] if r['status'] in ('approved','rejected','completed') and not r['reviewed_at']],severity='review')
latest_events={}
for r in sorted(data['AcademicStatusEvent'],key=lambda r:(r['occurred_on'],r['id'])):
    if r['status'] in ('approved','completed') and r.get('student_id'):latest_events[r['student_id']]=r
conflicts=[]
for sid,r in latest_events.items():
    s=students.get(sid)
    if not s:continue
    expected={'退学':'withdrawn','休学':'suspended','复学':'active','延期毕业':'extended'}.get(r['change_type'])
    if expected and s['current_status']!=expected and not (s['current_status']=='graduated' and r['change_type'] in ('复学','延期毕业') and r['occurred_on']<=s['graduated_on']):conflicts.append(r)
check('academic.current_status','最后一条已生效异动与当前学籍状态不一致','AcademicStatusEvent',conflicts,severity='review',note='可能缺后续复学/毕业事件，必须核对审批链，不能只依据一条事件覆盖主档。')
for r in data['TrainingPlan']:
    s=student_of(r)
    if not s:continue
    if s['current_status']=='graduated' and (r['completion_percent']!=100 or r['status']!='completed'):
        check('training.graduated.'+str(r['id']),'已毕业但培养未完成','TrainingPlan',[r])
check('training.complete_progress','培养状态完成但进度不足100','TrainingPlan',[r for r in data['TrainingPlan'] if r['status']=='completed' and r['completion_percent']!=100])
check('degree.award_before_paper','授位日期早于论文提交','DegreeApplication',[r for r in data['DegreeApplication'] if r['awarded_at'] and r['paper_submitted_at'] and r['awarded_at']<r['paper_submitted_at']])
check('degree.completed_missing','已授位缺日期/论文/通过结果','DegreeApplication',[r for r in data['DegreeApplication'] if r['award_status']=='completed' and (not r['awarded_at'] or not r['paper_submitted_at'] or r['defense_result']!='通过' or r['paper_review_result']!='通过')])
check('degree.active_awarded','在读学生已有授位日期','DegreeApplication',[r for r in data['DegreeApplication'] if student_of(r) and student_of(r)['current_status']=='active' and r['awarded_at']])
check('degree.type_mismatch','学位申请层次与学生层次不一致','DegreeApplication',[r for r in data['DegreeApplication'] if student_of(r) and (('博士' in r['application_type'])!=(student_of(r)['degree_type']=='doctoral'))])
check('degree.subject_mismatch','学位申请专业与学生专业不一致','DegreeApplication',[r for r in data['DegreeApplication'] if student_of(r) and r['discipline']!=student_of(r)['major']],severity='review')
check('scholarship.year_date','奖助年份与发放日期年份不一致','ScholarshipAward',[r for r in data['ScholarshipAward'] if r['awarded_on'] and r['award_year']!=r['awarded_on'].year])
check('scholarship.date_missing','奖助记录缺发放日期','ScholarshipAward',[r for r in data['ScholarshipAward'] if not r['awarded_on']],severity='review')

from apps.graduate.models import EmploymentRecord
from apps.graduate.portrait import latest_destinations, destination_state
latest=latest_destinations(EmploymentRecord.objects.select_related('student').all())
check('employment.2023','2023级硕士最新去向不在就业/考公/未知三类','EmploymentRecord',[r.pk for r in latest.values() if r.student and r.student.grade=='2023级' and r.student.degree_type!='doctoral' and destination_state(r.student,r,today=TODAY) not in ('employment','civil_service','unknown')])
check('employment.2025','2025级最新去向不是在读','EmploymentRecord',[r.pk for r in latest.values() if r.student and r.student.grade=='2025级' and destination_state(r.student,r,today=TODAY)!='in_study'])
check('employment.latest_details','已就业缺单位/地区/行业','EmploymentRecord',[r.pk for r in latest.values() if r.student and destination_state(r.student,r,today=TODAY)=='employment' and not all([r.employer_name,r.province,r.industry,r.unit_nature])])
check('employment.latest_flags','最新去向与签约/升学标记矛盾','EmploymentRecord',[r.pk for r in latest.values() if r.student and ((destination_state(r.student,r,today=TODAY) in ('in_study','unknown','civil_service') and r.is_signed) or (r.is_further_study and destination_state(r.student,r,today=TODAY) not in ('study','abroad')))])
latest_ids={r.pk for r in latest.values()}
check('employment.historical_before_enrollment','旧就业记录毕业年份不晚于入学年份','EmploymentRecord',[r for r in data['EmploymentRecord'] if student_of(r) and student_of(r)['enrolled_on'] and r['graduation_year']<=student_of(r)['enrolled_on'].year],note='已按个人最新记录展示不代表这些旧行在数据库中不存在。')
check('employment.historical_flags','旧就业记录的去向与标记冲突','EmploymentRecord',[r for r in data['EmploymentRecord'] if r['id'] not in latest_ids and ((r['is_signed'] and any(x in r['destination_type'] for x in ('未就业','未知','在读','考公'))) or (r['is_further_study'] and not any(x in r['destination_type'] for x in ('升学','出国'))))])

snapshots={r['id']:r for r in data['PredictionSnapshot']}
check('snapshot.before_enrollment','画像快照早于入学','PredictionSnapshot',[r for r in snapshots.values() if before_enrollment(r,timezone.localtime(r['captured_at']).date())])
check('snapshot.after_graduation','当前画像快照晚于毕业','PredictionSnapshot',[r for r in snapshots.values() if after_graduation(r,timezone.localtime(r['captured_at']).date())])
check('snapshot.graduated_progress','毕业画像培养/学分/毕业进度未完成','PredictionSnapshot',[r for r in snapshots.values() if student_of(r) and student_of(r)['current_status']=='graduated' and any(r[k]!=100 for k in ['credit_completion_rate','training_plan_completion_rate','graduation_progress_rate'])])
check('snapshot.graduated_risk','已毕业画像仍有在校风险/逾期','PredictionSnapshot',[r for r in snapshots.values() if student_of(r) and student_of(r)['current_status']=='graduated' and (r['risk_level']!='low' or r['overdue_tasks_count'] or r['missed_checkins'])])
latest_plans={}
for r in sorted(data['TrainingPlan'],key=lambda r:(r['updated_at'],r['id'])):latest_plans[r['student_id']]=r
check('snapshot.training_disagrees','画像培养进度与最新培养计划不一致','PredictionSnapshot',[r for r in snapshots.values() if r['student_id'] in latest_plans and abs(float(r['training_plan_completion_rate'])-latest_plans[r['student_id']]['completion_percent'])>0.1])
months=data['PredictionMonthlyMetric']
check('month.invalid','月度记录月份格式错误','PredictionMonthlyMetric',[r for r in months if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',r['month'])])
check('month.after_snapshot','月度记录晚于所属快照','PredictionMonthlyMetric',[r for r in months if r['snapshot_id'] in snapshots and r['month']>timezone.localtime(snapshots[r['snapshot_id']]['captured_at']).strftime('%Y-%m')],note='目前接口对演示数据会过滤这些月份，但库内仍保留。')
check('month.before_enrollment','月度记录早于学生入学','PredictionMonthlyMetric',[r for r in months if r['snapshot_id'] in snapshots and student_of(snapshots[r['snapshot_id']]) and student_of(snapshots[r['snapshot_id']])['enrolled_on'] and r['month']<student_of(snapshots[r['snapshot_id']])['enrolled_on'].strftime('%Y-%m')])
check('month.after_graduation','毕业后仍有在校月度记录','PredictionMonthlyMetric',[r for r in months if r['snapshot_id'] in snapshots and student_of(snapshots[r['snapshot_id']]) and student_of(snapshots[r['snapshot_id']])['graduated_on'] and r['month']>student_of(snapshots[r['snapshot_id']])['graduated_on'].strftime('%Y-%m')])
by_snapshot=defaultdict(list)
for r in months:by_snapshot[r['snapshot_id']].append(r)
check('month.coverage','画像快照缺月度记录','PredictionSnapshot',[r for r in snapshots.values() if not by_snapshot[r['id']]],severity='review')

pairs=defaultdict(list)
for s in S:pairs[(s['grade'],s['major'])].append(s)
group_mismatch=[]
for r in data['HomeGradeMajorSummary']:
    members=pairs[(r['grade'],r['major'])]
    actual=(len(members),sum(s['gender']=='男' for s in members),sum(s['gender']=='女' for s in members))
    stored=(r['total_count'],r['male_count'],r['female_count'])
    if actual!=stored:group_mismatch.append({'id':r['id'],'grade':r['grade'],'major':r['major'],'stored':stored,'actual':actual})
check('home.group_counts','首页年级专业汇总与学生明细不一致','HomeGradeMajorSummary',group_mismatch,details=group_mismatch if group_mismatch else None)
check('home.gender_sum','汇总男女人数之和不等于总人数','HomeGradeMajorSummary',[r for r in data['HomeGradeMajorSummary'] if r['male_count']+r['female_count']!=r['total_count']])
latest_annual=max(data['HomeAnnualSummary'],key=lambda r:r['year']) if data['HomeAnnualSummary'] else None
active=[s for s in S if s['current_status']=='active']
if latest_annual:
    annual_actual={'year':TODAY.year,'total_students':len(active),'master_count':sum(s['degree_type']!='doctoral' for s in active),'doctor_count':sum(s['degree_type']=='doctoral' for s in active),'international_count':sum(s['is_international'] for s in active),'annual_graduates':sum(bool(s['graduated_on']) and s['graduated_on'].year==TODAY.year for s in S)}
    check('home.annual_stale','首页最新年度汇总并非当前年度口径','HomeAnnualSummary',[latest_annual] if latest_annual['year']!=TODAY.year else [],severity='review',note='历史统计不能直接用当前学生状态覆盖；页面应明确历史年份或改用当前明细。',details={'stored':{k:latest_annual[k] for k in annual_actual},'currentDetail':annual_actual} if latest_annual['year']!=TODAY.year else None)
    check('home.annual_counts','当年汇总与当前学生明细不一致','HomeAnnualSummary',[latest_annual] if latest_annual['year']==TODAY.year and any(latest_annual[k]!=v for k,v in annual_actual.items()) else [])
check('home.degree_sum','年度硕博人数之和与总数不一致','HomeAnnualSummary',[r for r in data['HomeAnnualSummary'] if r['master_count']+r['doctor_count']!=r['total_students']])
source_counter=Counter(s['source_region'] for s in S)
source_diff=[{'id':r['id'],'region':r['region'],'stored':r['student_count'],'actual':source_counter[r['region']]} for r in data['HomeSourceRegionSummary'] if r['student_count']!=source_counter[r['region']]]
check('home.source_counts','首页生源汇总与全部学生明细不同','HomeSourceRegionSummary',source_diff,severity='review',note='需确认历史/在读/全部学生口径；不能默认全部是算错。',details=source_diff if source_diff else None)

check('admission.funnel','招生漏斗人数顺序矛盾','AdmissionCycle',[r for r in data['AdmissionCycle'] if not r['applicant_count']>=r['initial_review_pass_count']>=r['retest_count']>=r['proposed_admission_count']>=r['actual_admission_count']],severity='review',note='实际录取高于拟录取可能有补录，需要依据。')
check('admission.rate','招生录取率与实际录取/报名人数不一致','AdmissionCycle',[r for r in data['AdmissionCycle'] if r['applicant_count'] and abs(float(r['admission_rate'])-r['actual_admission_count']*100/r['applicant_count'])>0.11],severity='review',note='若系统使用其他分母，需明确标注。')
check('admission.stage_dates','招生阶段结束早于开始','AdmissionStageProgress',[r for r in data['AdmissionStageProgress'] if r['end_date']<r['start_date']])
check('admission.closed_incomplete','已完成招生阶段进度不足100','AdmissionStageProgress',[r for r in data['AdmissionStageProgress'] if r['status']=='completed' and r['completion_percent']!=100])
check('admission.stale_progress','过期招生阶段仍为待处理/进行中','AdmissionStageProgress',[r for r in data['AdmissionStageProgress'] if r['end_date']<TODAY and r['status'] in ('pending','in_progress','draft')],severity='review')
check('defense.stale','过去的答辩安排仍为待处理/进行中','DefenseSession',[r for r in data['DefenseSession'] if timezone.localtime(r['scheduled_at']).date()<TODAY and r['status'] in ('pending','in_progress','draft')],severity='review')
check('course.stale','2025年及以前课程仍为进行中','CourseOffering',[r for r in data['CourseOffering'] if re.match(r'^20\d{2}',r['term']) and int(r['term'][:4])<TODAY.year and r['status']=='in_progress'],severity='review')

check('import.completed_no_rows','已完成导入缺逐行审计记录','ImportBatch',[r for r in data['ImportBatch'] if r['status']=='completed' and r['total_rows']>0 and not any(x['batch_id']==r['id'] for x in data['ImportBatchRecord'])],severity='review')
check('import.date_order','导入完成早于开始','ImportBatch',[r for r in data['ImportBatch'] if r['started_at'] and r['completed_at'] and r['completed_at']<r['started_at']])
check('import.row_totals','导入行数分项与总行数不符','ImportBatch',[r for r in data['ImportBatch'] if r['status']=='completed' and r['total_rows']!=sum(r[k] for k in ['new_count','update_count','unchanged_count','error_count','skipped_count'])],severity='review')
check('warning.active_no_version','启用的预警规则缺版本记录','WarningRule',[r for r in data['WarningRule'] if r['is_active'] and not any(v['rule_id']==r['id'] and v['version']==r['version'] for v in data['WarningRuleVersion'])])
check('opportunity.date_order','招聘报名截止早于开始','Opportunity',[r for r in data['Opportunity'] if r['registration_start'] and r['registration_end'] and r['registration_end']<r['registration_start']])
check('opportunity.unverified_dates','招聘公告未记录精确报名截止时刻','Opportunity',[r for r in data['Opportunity'] if not r['registration_end']],severity='review',note='部分公告仅有日期或滚动招聘说明；保留原文说明，不能补造精确时刻。')
check('opportunity.url','招聘公告链接协议无效','Opportunity',[r for r in data['Opportunity'] if not re.match(r'^https?://',r['canonical_url'])])
check('source.never_synced','启用的信息源没有成功同步记录','EmploymentSource',[r for r in data['EmploymentSource'] if r['enabled'] and not r['last_success']],severity='review')
check('sync.date_order','同步完成时间早于开始','SyncRun',[r for r in data['SyncRun'] if r['finished_at'] and r['started_at'] and r['finished_at']<r['started_at']])
check('task.completed_no_result','完成的协同任务缺结果或审计','CollaborationTask',[r for r in data['CollaborationTask'] if r['status'] in ('completed','fallback') and (not r['result'].get('answer') or not r['result'].get('audit'))])

# Additional cross-table checks and schema-specific exceptions.
check('indicator.invalid_max','指标刻度上限非正数','PredictionIndicatorDefinition',[r for r in data['PredictionIndicatorDefinition'] if r['max_score']<=0])
check('student.future_enrollment','学生入学日期在未来','Student',[s for s in S if s['enrolled_on'] and s['enrolled_on']>TODAY])
check('employment.latest_year','最新去向毕业年份与主档毕业年份不一致','EmploymentRecord',[r.pk for r in latest.values() if r.student and (r.student.graduated_on or r.student.expected_graduation_date) and r.graduation_year!=(r.student.graduated_on or r.student.expected_graduation_date).year])
check('employment.old_source_missing','旧就业记录缺数据来源标记','EmploymentRecord',[r for r in data['EmploymentRecord'] if r['id'] not in latest_ids and not r['data_source']],severity='review')
check('degree.application_year','申请年份与已授位年份不一致','DegreeApplication',[r for r in data['DegreeApplication'] if r['awarded_at'] and r['application_year']!=r['awarded_at'].year],severity='review')
check('degree.future_award','存在未来已授位日期','DegreeApplication',[r for r in data['DegreeApplication'] if r['awarded_at'] and r['awarded_at']>TODAY])
check('scholarship.future_date','已记录的奖助发放日在未来','ScholarshipAward',[r for r in data['ScholarshipAward'] if r['awarded_on'] and r['awarded_on']>TODAY],severity='review')
check('export.file_missing','未过期的已完成导出文件不存在','ExportRecord',[r for r in data['ExportRecord'] if r['status']=='completed' and (not r['expires_at'] or timezone.localtime(r['expires_at']).date()>=TODAY) and (not r['file_path'] or not Path(r['file_path']).is_file())])
check('source.url','信息源链接协议无效','EmploymentSource',[r for r in data['EmploymentSource'] if not re.match(r'^https?://',r['url'])])
event_keys={(r['student_id'],r['change_type'],r['status']) for r in data['AcademicStatusEvent']}
check('academic.request_event_mismatch','学籍申请与异动事件缺相同学生/类型/状态的对应记录','AcademicChangeRequest',[r for r in data['AcademicChangeRequest'] if (r['student_id'],r['change_type'],r['status']) not in event_keys],severity='review',note='申请时间和生效时间允许不同；这里不以同一天作为匹配条件。')
for model_name in ['TrainingPlan','DegreeApplication']:
    fields=[f for f in data[model_name][0] if f not in ('id','created_at','updated_at')] if data[model_name] else []
    duplicate(model_name+'.exact_duplicate','除主键与技术时间戳外全部业务字段完全相同',model_name,fields,severity='error',note='与前面的重复业务键统计重叠；实际展示和统计中会重复计数。')

summary={'auditDate':str(TODAY),'snapshot':str(globals().get('AUDIT_SNAPSHOT','live')),'physicalTables':physical_tables,
         'modelCount':len(inventory),'businessRows':sum(v['rows'] for v in inventory if v['model'].split('.')[0] in APP_LABELS and v['model']!='graduate.DataRepairArchive'),'repairArchiveEntries':len(data.get('DataRepairArchive',[])),
         'integrity':integrity,'foreignKeyViolations':len(foreign_keys),'pendingMigrations':pending,
         'studentCount':len(S),'activeCount':len(active),'graduatedCount':sum(s['current_status']=='graduated' for s in S),
         'profileSources':dict(Counter(s['profile_source'] for s in S)),
         'checksRun':len(checks),'issueGroups':len(issues),'issueGroupsBySeverity':dict(Counter(i['severity'] for i in issues)),
         'note':'各问题可能涉及同一记录，不能把问题计数直接相加当作人数；review是待核实项。',
         'coverageByGrade':{g:{'students':sum(s['grade']==g for s in S),'status':dict(Counter(s['current_status'] for s in S if s['grade']==g)),'destinations':dict(Counter(destination_state(r.student,r,today=TODAY) for r in latest.values() if r.student and r.student.grade==g))} for g in sorted({s['grade'] for s in S})}}
report={'summary':summary,'inventory':inventory,'issues':issues,'checks':checks}
output=Path(globals().get('AUDIT_OUTPUT','database-audit.json'))
output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf8')
print(json.dumps({'summary':summary,'issues':[{k:v for k,v in i.items() if k not in ('ids','details')} for i in issues]},ensure_ascii=False,default=str))
