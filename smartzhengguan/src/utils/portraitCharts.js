// Portrait views use the existing API payloads. No requests or external inference here.
export const PORTRAIT_COLORS = ['#3768DF', '#149F97', '#8770D5', '#E6A23C', '#EC7F86', '#5B9ECD']
export const COHORT_METRICS = [
  { key: 'awardRate', label: '奖助覆盖', weight: 0.28 },
  { key: 'employmentRate', label: '已落实占比', weight: 0.34 },
  { key: 'trainingCompletionRate', label: '培养完成', weight: 0.20 },
  { key: 'degreeProgressRate', label: '学位进度', weight: 0.18 },
]
export const STUDENT_METRICS = [
  { key: 'courseAverage', label: '课程均分', unit: '分' },
  { key: 'creditCompletionRate', label: '学分完成', unit: '%' },
  { key: 'researchTaskCompletionRate', label: '科研任务', unit: '%' },
  { key: 'attendanceRate', label: '出勤率', unit: '%' },
  { key: 'trainingPlanCompletionRate', label: '培养进度', unit: '%' },
]
export const ACADEMIC_METRICS = [
  { key: 'courseAverage', label: '课程均分', weight: 0.40, unit: '分' },
  { key: 'creditCompletionRate', label: '学分完成', weight: 0.30, unit: '%' },
  { key: 'trainingPlanCompletionRate', label: '培养进度', weight: 0.15, unit: '%' },
  { key: 'graduationProgressRate', label: '毕业进度', weight: 0.15, unit: '%' },
]

export function numeric(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}
export function score(value) {
  const n = numeric(value)
  return n !== null && n >= 0 && n <= 100 ? n : null
}
const count = value => Math.max(0, Math.floor(numeric(value) ?? 0))
export const fmt = value => numeric(value) === null ? '暂无' : Number(value).toFixed(1).replace(/\.0$/, '')
const wrap = (value, n = 8) => String(value || '').match(new RegExp('.{1,' + n + '}', 'g'))?.join('\n') || ''
const base = () => ({ animation: false, color: PORTRAIT_COLORS, textStyle: { fontFamily: 'Microsoft YaHei, sans-serif', color: '#526078', fontSize: 12 }, aria: { enabled: true }, tooltip: { renderMode: 'richText', confine: true } })
export function emptyChart(text = '当前范围暂无可展示的数据') {
  return { ...base(), graphic: [{ type: 'text', left: 'center', top: 'middle', style: { text, fill: '#7D8BA3', fontSize: 13, lineHeight: 22, textAlign: 'center' } }], series: [] }
}

export function buildCohortStructure(rows = []) {
  const nodes = [], links = [], grades = new Map(), outcomes = new Map(), hierarchy = []
  let total = 0, unknownGender = 0, inconsistentGender = 0
  const sorted = [...rows].filter(row => count(row.totalStudents) > 0).sort((a, b) => String(a.id).localeCompare(String(b.id), 'zh-CN'))
  const multipleGrades = new Set(sorted.map(row => row.grade)).size > 1
  const multipleMajors = new Set(sorted.map(row => row.major)).size > 1
  sorted.forEach((row, i) => {
    const n = count(row.totalStudents), gradeId = 'grade:' + row.grade, id = 'cohort:' + row.id
    const color = PORTRAIT_COLORS[i % PORTRAIT_COLORS.length]
    total += n
    if (!grades.has(gradeId)) { const node = { name: gradeId, labelText: row.grade, depth: 0, itemStyle: { color: '#3768DF' } }; grades.set(gradeId, node); nodes.push(node) }
    nodes.push({ name: id, labelText: multipleGrades ? `${row.major}\n${row.grade}` : row.major, entityId: row.id, depth: 1, itemStyle: { color } })
    links.push({ source: gradeId, target: id, value: n })
    const states = Array.isArray(row.destinations) && row.destinations.reduce((sum,d)=>sum+count(d.count),0) === n
      ? row.destinations : [{label:'去向待核实',count:n,key:'verify'}]
    states.forEach(({label, count: value, key}) => {
      if (!value) return
      const target = 'destination:' + label
      if (!outcomes.has(target)) { outcomes.set(target,true); nodes.push({name:target,labelText:label,depth:2,itemStyle:{color:['verify','unresolved','inactive'].includes(key)?'#DCA44B':key==='in_study'?'#7E94B6':'#149F97'}}) }
      links.push({source:id,target,value})
    })
    const male = count(row.maleCount), female = count(row.femaleCount), invalid = male + female > n
    const missing = invalid ? n : n - male - female
    unknownGender += missing
    if (invalid) inconsistentGender++
    const structureLabel = multipleGrades ? (multipleMajors ? `${row.grade} · ${row.major}` : row.grade) : row.major
    hierarchy.push({ name: structureLabel, value: n, entityId: row.id, itemStyle: { color }, children: (invalid ? [['口径待核查', n]] : [['男', male], ['女', female], ['数据待核验', missing]]).filter(([,value]) => value > 0).map(([name,value]) => ({ name, value, entityId: row.id })) })
  })
  return { nodes, links, hierarchy, total, unknownGender, inconsistentGender }
}
export function sankeyChart(structure, width = 600) {
  if (!structure.total) return emptyChart()
  return { ...base(), tooltip: { renderMode: 'richText', confine: true, formatter: p => p.dataType === 'edge' ? `${p.data.source.replace(/^[^:]+:/,'')} → ${p.data.target.replace(/^[^:]+:/,'')}\n${p.value} 人` : `${p.data.labelText}\n点击专业可联动评分与维度对比` }, series: [{ type: 'sankey', left: 4, right: 8, top: 16, bottom: 16, nodeWidth: 10, nodeGap: 15, draggable: false, layoutIterations: 32, emphasis: { focus: 'adjacency' }, data: structure.nodes, links: structure.links, lineStyle: { color: 'gradient', opacity: 0.22, curveness: 0.5 }, label: { color: '#3C4C68', fontSize: 11, formatter: p => wrap(p.data.labelText, width < 420 ? 5 : 9) }, levels: [{ depth: 0, label: { position: 'right' } }, { depth: 1, label: { position: 'right' } }, { depth: 2, label: { position: 'left' } }] }] }
}
export function sunburstChart(structure, selectedId) {
  if (!structure.total) return emptyChart()
  return { ...base(), tooltip: { renderMode: 'richText', confine: true, formatter: p => `${p.treePathInfo.slice(1).map(d => d.name).join(' / ')}\n${p.value} 人` }, series: [{ type: 'sunburst', data: structure.hierarchy.map(node => ({ ...node, itemStyle: { ...node.itemStyle, borderColor: node.entityId === selectedId ? '#344566' : '#FFFFFF', borderWidth: node.entityId === selectedId ? 2.5 : 2 } })), radius: ['20%', '88%'], center: ['50%', '50%'], sort: null, nodeClick: false, emphasis: { focus: 'ancestor' }, label: { color: '#344054', fontSize: 11, minAngle: 12, rotate: 'tangential', formatter: p => p.data.children ? (p.name.length > 6 ? p.name.slice(0,5) + '…' : p.name) : `${p.name} ${p.value}` }, itemStyle: { borderColor: '#FFFFFF', borderWidth: 2, opacity: 0.88 }, levels: [{}, { r0: '20%', r: '61%', itemStyle: { opacity: 0.8 } }, { r0: '62%', r: '88%', itemStyle: { opacity: 0.48 } }], selectedMode: false }], graphic: [{ type: 'text', left: 'center', top: '46%', silent: true, style: { text: `${structure.total}\n人`, fill: '#283B5D', fontSize: 14, lineHeight: 20, textAlign: 'center' } }] }
}
export function parallelChart(rows, metrics, selectedId, width = 600) {
  const complete = rows.filter(row => metrics.every(m => score(row[m.key]) !== null))
  if (!complete.length) return emptyChart('缺少完整的多维记录\n缺失值不按零分绘制')
  const selected = complete.find(row => row.id === selectedId)
  const others = complete.filter(row => row.id !== selectedId)
  const sample = others.length <= 120 ? others : Array.from({length:120},(_,i) => others[Math.floor(i * others.length / 120)])
  const make = (data, highlight) => ({ type: 'parallel', name: highlight ? '当前对象' : '同组参考', lineStyle: { width: highlight ? 3 : 1, color: highlight ? '#149F97' : '#8DA9ED', opacity: highlight ? 1 : 0.22 }, inactiveOpacity: 0.06, activeOpacity: 0.65, data: data.map(row => ({ name: row.label, entityId: row.id, value: metrics.map(m => Number(row[m.key])) })) })
  return { ...base(), tooltip: { renderMode: 'richText', confine: true, formatter: p => `${p.name || '同组参考'}\n${metrics.map((m,i) => `${m.label}：${fmt(p.value[i])}${m.unit || '%'}`).join('\n')}` }, parallel: { left: 45, right: 34, top: 48, bottom: 28, parallelAxisDefault: { min: 0, max: 100, type: 'value', nameLocation: 'end', nameGap: 16, nameTextStyle: { color: '#526078', fontSize: 11 }, axisLine: { lineStyle: { color: '#DCE5F0' } }, axisLabel: { color: '#7E8BA1', fontSize: 10 }, splitNumber: 2, areaSelectStyle: { color: 'rgba(20,159,151,0.12)', borderColor: '#149F97', borderWidth: 1 } } }, parallelAxis: metrics.map((m,dim) => ({ dim, name: width < 480 ? wrap(m.label, 2) : m.label, axisLabel: { show: dim === 0 } })), series: [...(sample.length ? [make(sample,false)] : []), ...(selected ? [make([selected],true)] : [])] }
}

export function weightedContributions(record, metrics, normalize = false) {
  const available = metrics.map(m => ({ ...m, raw: score(record?.[m.key]) })).filter(m => m.raw !== null)
  const weight = available.reduce((sum,m) => sum + m.weight, 0)
  if (!available.length || (!normalize && available.length !== metrics.length)) return { items: [], total: null, missing: metrics.length - available.length }
  let cumulative = 0
  const items = available.map(m => { const effectiveWeight = normalize ? m.weight / weight : m.weight; const value = m.raw * effectiveWeight; const start = cumulative; cumulative += value; return { ...m, weight: effectiveWeight, value, start, end: cumulative } })
  return { items, total: Number(cumulative.toFixed(1)), missing: metrics.length - available.length }
}
export function waterfallChart(contributions, totalLabel = '规则总分') {
  const items = contributions.items || []
  if (!items.length) return emptyChart('暂无完整的评分依据')
  const all = [...items, { label: totalLabel, value: contributions.total, start: 0, total: true }]
  return { ...base(), grid: { left: 105, right: 48, top: 14, bottom: 38 }, tooltip: { renderMode: 'richText', confine: true, trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: p => { const row=all[p[0].dataIndex]; return row.total ? `${totalLabel}：${fmt(row.value)} 分\n规则加权结果，不是风险概率` : `${row.label}：${fmt(row.raw)}${row.unit || '%'}\n有效权重：${fmt(row.weight*100)}%\n加权贡献：${fmt(row.value)} 分` } }, xAxis: { type: 'value', min: 0, max: 100, name: '贡献 / 分', nameLocation: 'middle', nameGap: 26, splitLine: { lineStyle: { color: '#EEF2F8' } }, axisLabel: { fontSize: 11 } }, yAxis: { type: 'category', inverse: true, data: all.map(m => m.total ? m.label : `${m.label}\n${fmt(m.weight*100)}%`), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { fontSize: 11, lineHeight: 17, color: '#526078' } }, series: [{ type: 'bar', stack: 'contribution', silent: true, itemStyle: { color: 'transparent' }, emphasis: { disabled: true }, data: all.map(m => m.start) }, { type: 'bar', stack: 'contribution', barWidth: 23, label: { show: true, position: 'right', color: '#526078', fontSize: 11, formatter: p => (all[p.dataIndex].total ? '' : '+') + fmt(p.value) }, data: all.map(m => ({ value: m.value, itemStyle: { color: m.total ? '#8770D5' : '#149F97', borderRadius: [0,3,3,0] } })) }] }
}

export function quantile(values, p) {
  const sorted = values.filter(v => numeric(v) !== null).map(Number).sort((a,b) => a-b)
  if (!sorted.length) return null
  const pos=(sorted.length-1)*p, lo=Math.floor(pos), hi=Math.ceil(pos)
  return sorted[lo] + (sorted[hi]-sorted[lo])*(pos-lo)
}
export function comparableStudents(students, target) {
  if (!target?.studentId) return []
  return students.filter(s => s.dataSource === 'measured' && s.hasMeasuredSnapshot !== false && s.grade === target.grade && s.major === target.major && s.degreeType === target.degreeType && s.college === target.college)
}
export function distributionData(students, target, metrics = STUDENT_METRICS.slice(0,3), minCount = 5) {
  return metrics.map(m => {
    const values=students.map(s => score(s.currentSnapshot?.[m.key])).filter(v => v !== null)
    const n=values.length, current=score(target.currentSnapshot?.[m.key]), median=quantile(values,0.5), low=quantile(values,0.25), high=quantile(values,0.75)
    const mean=n ? values.reduce((sum,v)=>sum+v,0)/n : 0
    const sigma=n>1 ? Math.sqrt(values.reduce((sum,v) => sum+(v-mean)**2,0)/(n-1)) : 0
    const bandwidth=Math.max(2,Math.min(12,1.06*sigma*Math.pow(Math.max(1,n),-0.2)))
    const density=n>=minCount ? Array.from({length:51},(_,i)=> { const x=i*2; return [x,values.reduce((sum,v)=>sum+Math.exp(-0.5*((x-v)/bandwidth)**2),0)/(n*bandwidth*Math.sqrt(2*Math.PI))] }) : []
    return { ...m, n, current, median: n>=minCount?median:null, low:n>=minCount?low:null, high:n>=minCount?high:null, density }
  })
}
export function violinChart(distributions) {
  if (!distributions.some(d => d.current !== null || d.density.length)) return emptyChart('暂无当前值与同组记录')
  return { ...base(), grid: { left: 77, right: 28, top: 24, bottom: 40 }, tooltip: { renderMode: 'richText', confine: true, formatter: p => {const d=distributions[p.dataIndex]; return `${d.label} · 有效样本 ${d.n} 人\n当前：${fmt(d.current)}${d.unit}\n${d.density.length?`中位数：${fmt(d.median)}${d.unit}\n四分位：${fmt(d.low)}—${fmt(d.high)}${d.unit}`:'同组样本不足5人，不展示分布'}` } }, xAxis: { type: 'value', min: 0, max: 100, name: '课程 / 分；其余 / %', nameLocation: 'middle', nameGap: 27, splitLine: { lineStyle: { color: '#EEF2F8' } }, axisLabel: { fontSize: 11 } }, yAxis: { type: 'category', inverse: true, data: distributions.map(d=>d.label), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { fontSize: 11 } }, series: [{ type: 'custom', name: '同组分布与个人位置', data: distributions.map((d,i)=>[i]), renderItem: (params,api) => {
    const d=distributions[params.dataIndex], i=params.dataIndex, center=api.coord([0,i])[1], half=Math.min(30,Math.abs(api.size([0,1])[1])*0.33), children=[]
    const max=Math.max(...d.density.map(v=>v[1]),1e-8)
    if(d.density.length) {
      const upper=d.density.map(([v,density])=>[api.coord([v,i])[0],center-density/max*half])
      const lower=[...d.density].reverse().map(([v,density])=>[api.coord([v,i])[0],center+density/max*half])
      children.push({type:'polygon',shape:{points:[...upper,...lower]},style:{fill:'rgba(55,104,223,0.14)'}})
      const q1=api.coord([d.low,i])[0],q3=api.coord([d.high,i])[0],med=api.coord([d.median,i])[0]
      children.push({type:'line',shape:{x1:q1,y1:center,x2:q3,y2:center},style:{stroke:'#3768DF',lineWidth:6}})
      children.push({type:'line',shape:{x1:med,y1:center-7,x2:med,y2:center+7},style:{stroke:'#FFFFFF',lineWidth:2}})
    }
    if(d.current!==null){const x=api.coord([d.current,i])[0];children.push({type:'polygon',shape:{points:[[x,center-7],[x+5,center],[x,center+7],[x-5,center]]},style:{fill:'#149F97',stroke:'#FFFFFF',lineWidth:1}})}
    return {type:'group',children,clipPath:{type:'rect',shape:{x:params.coordSys.x-6,y:params.coordSys.y,width:params.coordSys.width+12,height:params.coordSys.height}}}
  } }] }
}
export function evidenceChart(target, contributions, width=600) {
  if (!contributions.items.length) return emptyChart('暂无可追溯的评分记录')
  const size=width<450?76:108
  const nodes=[{ id:'result', name:`学业维度\n${fmt(contributions.total)} 分`, x:0,y:150, category:0 }, {id:'source', name:`导入快照\n${(target.capturedAt || '').slice(0,10) || '当前记录'}`,x:520,y:150,category:2}]
  const links=[]
  contributions.items.forEach((m,i)=>{const id='metric:'+m.key;nodes.push({id,name:`${m.label} ${fmt(m.raw)}\n权重 ${fmt(m.weight*100)}%`,x:260,y:35+i*78,category:1,sourceKey:m.key});links.push({source:'result',target:id},{source:id,target:'source'})})
  return { ...base(), tooltip:{renderMode:'richText',confine:true,formatter:p=>p.dataType==='edge'?'连线表示评分依据，不表示因果关系':p.data.sourceKey?`${p.name}\n点击查看来源字段与快照日期`:p.name}, series:[{type:'graph',layout:'none',roam:false,left:size/2+4,right:size/2+4,top:35,bottom:35,data:nodes,links,categories:[{name:'规则结果',itemStyle:{color:'#E8EFFD'}},{name:'测量指标',itemStyle:{color:'#E3F4F1'}},{name:'来源记录',itemStyle:{color:'#F0EBFA'}}],symbol:'roundRect',symbolSize:[size,54],label:{show:true,color:'#344566',fontSize:11,lineHeight:18},lineStyle:{color:'#C4CFDF',width:1.5,curveness:0.08},emphasis:{focus:'adjacency'},edgeSymbol:['none','arrow'],edgeSymbolSize:[0,5]}] }
}
