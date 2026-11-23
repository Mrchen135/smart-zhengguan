// Rules are descriptive workflow guidance, never predictions or personal diagnoses.
const count = value => Math.max(0, Number(value) || 0)
const rate = (n, d) => d ? Math.round(n * 1000 / d) / 10 : 0
export function cohortInsights(rows = []) {
  const sum = key => rows.reduce((n, row) => n + count(row[key]), 0)
  const total = sum('totalStudents'), pending = sum('destinationPendingCount'), unresolved = sum('unresolvedCount')
  const trainingMissing = rows.reduce((n,r) => n + Math.max(0,count(r.totalStudents)-count(r.trainingCoverageCount)),0)
  const ranked = [...rows].sort((a,b)=> count(b.destinationPendingCount)-count(a.destinationPendingCount))
  const priority = ranked[0]
  const conclusions = []
  if (!total) return {total:0, conclusions:[], pending:0, unresolved:0, trainingMissing:0, completeness:0, demo:0, ranked:[]}
  if (pending) conclusions.push({tone:'amber', title:'先补齐去向核实，再判断就业表现', value:pending, unit:'人待核实',
    evidence:'占当前范围 '+rate(pending,total)+'%；'+(priority ? priority.grade+' · '+priority.major+' 待核实 '+priority.destinationPendingCount+' 人，建议先跟进。' : ''),
    action:'就业辅导员本周核对毕业资格与去向证明，逐人区分求职、升学、延期和已落实；未核实前不作就业率结论。',
    acceptance:'验收：待核实人数下降，新增状态均有来源记录。', key:'destinationPendingCount'})
  else conclusions.push({tone:'teal', title:'当前范围没有待核实去向', value:sum('employedCount'), unit:'人已落实',
    evidence:'另有 '+sum('inStudyCount')+' 人处于在读阶段；已落实人数按每人最新年度去重。',
    action:'就业辅导员按月复核去向变化与证明材料，保持学生状态与业务台账一致。', acceptance:'验收：新增变更有对应记录。',key:'employedCount'})
  if (unresolved) conclusions.push({tone:'violet',title:'已确认未落实者需要定向支持',value:unresolved,unit:'人暂未落实',
    evidence:'仅包含明确登记为未就业、待就业或求职中的学生，不含缺失记录。',
    action:'就业辅导员一周内确认个人意愿，安排岗位匹配或升学咨询；两周后复核申请和面试进展。',acceptance:'验收：每人形成意向、下一步行动与复核日期。',key:'unresolvedCount'})
  else conclusions.push({tone:'violet',title:'已落实去向可以沉淀为指导资源',value:sum('employedCount'),unit:'人已落实',
    evidence:'当前没有明确登记为暂未落实的学生；这不代表待核实者已经就业。',
    action:'就业辅导员按去向类型整理求职与升学经验，面向同专业开展专题交流；避免把覆盖不足解读为就业表现差。',acceptance:'验收：形成按去向分类的指导材料。',key:'employedCount'})
  conclusions.push(trainingMissing ? {tone:'blue',title:'培养记录覆盖不足，先核查再评价',value:trainingMissing,unit:'人缺培养记录',
    evidence:'当前 '+total+' 人中有 '+(total-trainingMissing)+' 人关联培养计划；缺记录会拉低旧版进度汇总。',
    action:'研究生教务本周按学号核对培养计划与导入映射，补齐后再与同年级、同学位类型的培养要求比较。',acceptance:'验收：覆盖人数增加，进度与培养台账一致。',key:'trainingMissing'} :
    {tone:'blue',title:'培养计划已覆盖当前学生',value:total,unit:'人有培养记录',evidence:'覆盖完整只代表有台账，不代表所有培养环节已经完成。',
    action:'研究生教务与导师按计划节点核对逾期任务，优先确认本阶段需完成的环节。',acceptance:'验收：逾期任务有负责人和复核日期。',key:'trainingMissing'})
  return {total,pending,unresolved,trainingMissing,conclusions,ranked,completeness:rate(sum('maleCount')+sum('femaleCount'),total),demo:sum('demoGenderCount'),inStudy:sum('inStudyCount'),resolved:sum('employedCount'),tracking:sum('destinationTrackingCount')}
}
export function studentActions(target, distributions = []) {
  const snapshot=target.currentSnapshot || {}, actions=[]
  if (Number(snapshot.overdueTasksCount)>0) actions.push({title:'优先清理逾期任务', evidence:'当前快照记录 '+snapshot.overdueTasksCount+' 项逾期任务。',action:'学生与导师本周逐项核对截止时间、阻碍和责任人，拆分为可交付步骤；一周后复核剩余数量。'})
  const low=distributions.filter(d=>d.current!==null&&d.median!==null&&d.current<d.low).sort((a,b)=>(a.current-a.median)-(b.current-b.median))[0]
  if(low)actions.push({title:low.label+'需要进一步核查',evidence:'当前 '+low.current+low.unit+'，低于同组下四分位 '+Number(low.low.toFixed(1))+low.unit+'（有效样本 '+low.n+' 人）。',action:low.key==='courseAverage'?'学生与导师核对具体课程和考核要求，选出需要补强的知识点，安排两周学习计划并复核。':'学生与导师核对当前培养阶段和已完成事项，确认差异是否来自任务安排或数据更新，再制定两周推进计划。'})
  if(!actions.length)actions.push({title:'按培养节点持续跟进',evidence:'当前可比较指标未触发下四分位提醒；同组样本不足时不作相对评价。',action:'学生与导师确认下一项培养里程碑、交付物和日期；两周后更新记录并复核进展。'})
  return actions.slice(0,2)
}

export function summarizePortrait(rows=[]) {
  const sum=key=>rows.reduce((n,r)=>n+count(r[key]),0)
  const mean=key=>{const valid=rows.filter(r=>r[key]!==null&&r[key]!==undefined&&Number.isFinite(Number(r[key]))&&count(r.snapshotCount)>0);const n=valid.reduce((s,r)=>s+count(r.snapshotCount),0);return n?Math.round(valid.reduce((s,r)=>s+Number(r[key])*count(r.snapshotCount),0)/n*10)/10:null}
  const distribution=key=>{const data=new Map();rows.forEach(r=>(r[key]||[]).forEach(d=>data.set(d.name,(data.get(d.name)||0)+count(d.value))));return [...data].map(([name,value])=>({name,value})).sort((a,b)=>b.value-a.value)}
  const destinationCount=key=>rows.reduce((n,r)=>n+(Array.isArray(r.destinations)?r.destinations.filter(d=>d.key===key).reduce((v,d)=>v+count(d.count),0):count(r[{employment:'employedCount',civil_service:'civilServiceCount',unknown:'unknownDestinationCount',in_study:'inStudyCount'}[key]])),0)
  const total=sum('totalStudents'),graduated=sum('graduatedCount'),active=sum('activeCount'),employed=destinationCount('employment'),civil=destinationCount('civil_service'),unknown=destinationCount('unknown')
  const destinations=[{key:'employment',name:'就业',value:employed,color:'#315fbd'},{key:'civil_service',name:'考公',value:civil,color:'#329c91'},{key:'unknown',name:'未知',value:unknown,color:'#d9ad5a'},{key:'in_study',name:'在读',value:destinationCount('in_study'),color:'#a7bbd7'},...Object.entries({study:'升学',abroad:'出国出境',flexible:'灵活就业',other:'其他已落实',unresolved:'暂未落实',verify:'去向待核实',inactive:'学籍异动'}).map(([key,name])=>({key,name,value:destinationCount(key),color:'#8795a7'}))].filter(d=>d.value>0)
  return {total,graduated,active,employed,civil,unknown,destinations,male:sum('maleCount'),female:sum('femaleCount'),course:mean('courseAverage'),credit:mean('creditCompletionRate'),training:mean('trainingObservedAverage'),research:mean('researchTaskCompletionRate'),attendance:mean('attendanceRate'),practice:mean('practiceHoursAverage'),meetings:mean('advisorMeetingsAverage'),outputs:sum('researchOutputCount'),overdue:sum('overdueStudentCount'),snapshots:sum('snapshotCount'),awards:sum('awardCount'),demo:sum('demoProfileCount'),stages:distribution('trainingStages'),industries:distribution('employmentIndustries'),regions:distribution('sourceRegions'),degreeTypes:distribution('degreeTypes'),employmentRegions:distribution('employmentRegions'),employmentRate:graduated?rate(employed,graduated):null,civilRate:graduated?rate(civil,graduated):null,unknownRate:graduated?rate(unknown,graduated):null}
}
export function portraitNarrative(report) {
  if(!report.total)return {headline:'当前范围暂无画像数据',description:'调整年级或专业后查看。',findings:[],recommendation:''}
  const graduated=report.graduated===report.total,studying=report.active===report.total,industry=report.industries[0],stage=report.stages[0]
  return {
    headline:graduated?'培养已完成，关注职业发展的下一步':studying?'围绕培养节点，积累研究与实践能力':'连接在读培养与毕业发展',
    description:graduated?'当前 '+report.total+' 人均已毕业，就业 '+report.employmentRate+'%，考公 '+report.civilRate+'%，未知 '+report.unknownRate+'%。':studying?'当前 '+report.total+' 人均在读，主要处于'+(stage?.name||'培养')+'阶段。画像以学业积累和培养进展为重点。':'当前 '+report.active+' 人在读、'+report.graduated+' 人毕业；不同阶段分别观察，毕业去向比例只以毕业人数为分母。',
    findings:graduated?[industry?industry.name+'是当前就业人数最多的行业方向（'+industry.value+' 人）。':'当前没有可比较的就业行业记录。','考公 '+report.civil+' 人是明确的发展意向，不能合并为已就业或已录用。']:[report.credit===null?'学分数据尚不足以形成结论。':'当前学分平均完成 '+report.credit+'%，培养进度平均 '+report.training+'%。',report.practice===null?'当前缺少实践记录。':'平均实践 '+report.practice+' 小时，科研成果累计 '+report.outputs+' 项；结合具体培养要求判断。'],
    recommendation:graduated?'按就业行业组织岗位经验与校友交流；对考公群体安排招考信息、笔试和面试辅导，按考试阶段复核进展。':report.overdue?'有 '+report.overdue+' 人记录了逾期任务。建议导师先确认任务截止时间与阻碍，再安排两周推进目标，并同步补强课程和实践安排。':'建议导师围绕下一培养节点明确交付物与日期，结合已有实践和科研成果安排研究任务；每两周复核一次进展。',
  }
}
