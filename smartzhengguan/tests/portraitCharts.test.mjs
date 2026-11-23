import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
const source=await readFile(new URL('../src/utils/portraitCharts.js',import.meta.url),'utf8')
const {buildCohortStructure,weightedContributions,COHORT_METRICS,ACADEMIC_METRICS,comparableStudents,distributionData,parallelChart,numeric}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))

test('桑基图每个专业的人数流入流出守恒，性别缺失独立计数',()=>{
  const data=buildCohortStructure([{id:'a',grade:'2024级',major:'甲',totalStudents:10,maleCount:3,femaleCount:5,employedCount:6},{id:'b',grade:'2024级',major:'乙',totalStudents:5,maleCount:5,femaleCount:3,employedCount:9}])
  assert.equal(data.total,15)
  assert.equal(data.unknownGender,7)
  assert.equal(data.inconsistentGender,1)
  for(const id of ['cohort:a','cohort:b'])assert.equal(data.links.filter(l=>l.target===id).reduce((s,l)=>s+l.value,0),data.links.filter(l=>l.source===id).reduce((s,l)=>s+l.value,0))
  for(const branch of data.hierarchy)assert.equal(branch.children.reduce((s,c)=>s+c.value,0),branch.value)
})
test('群体规则贡献还原原有四项权重及综合评分',()=>{
  const data=weightedContributions({awardRate:50,employmentRate:80,trainingCompletionRate:80,degreeProgressRate:75},COHORT_METRICS)
  assert.equal(data.total,70.7)
  assert.ok(Math.abs(data.items.reduce((s,m)=>s+m.value,0)-70.7)<1e-9)
  assert.equal(data.items[2].start,data.items[1].end)
})
test('单专业跨年级比较能区分不同年级的结构与联动对象',()=>{
  const data=buildCohortStructure([{id:'a',grade:'2023级',major:'国际关系',totalStudents:10},{id:'b',grade:'2024级',major:'国际关系',totalStudents:12}])
  assert.deepEqual(data.hierarchy.map(row=>row.name),['2023级','2024级'])
  assert.deepEqual(data.hierarchy.map(row=>row.entityId),['a','b'])
  assert.equal(data.total,22)
  assert.match(data.nodes.find(node=>node.entityId==='b').labelText,/2024级/)
})
test('个人缺项重分配有效权重；缺失、空串与非数值不能当零',()=>{
  const data=weightedContributions({courseAverage:80,creditCompletionRate:null,trainingPlanCompletionRate:'',graduationProgressRate:100},ACADEMIC_METRICS,true)
  assert.equal(data.missing,2)
  assert.equal(data.total,85.5)
  assert.ok(Math.abs(data.items.reduce((s,m)=>s+m.weight,0)-1)<1e-9)
  assert.equal(numeric(null),null)
  assert.equal(numeric(''),null)
  assert.equal(numeric('bad'),null)
  assert.equal(numeric(false),null)
  assert.equal(numeric(0),0)
  assert.equal(weightedContributions({},COHORT_METRICS).total,null)
})
const target={id:'s1',studentId:'1',college:'学院',grade:'2024级',major:'甲',degreeType:'学术型硕士',dataSource:'measured',currentSnapshot:{courseAverage:70}}
test('同组仅包含同院同年级专业学位的导入快照，排除虚拟与缺失指标',()=>{
  const students=[target,{...target,id:'s2',dataSource:'virtual'},{...target,id:'s3',grade:'2023级'},{...target,id:'s4',degreeType:'博士'},{...target,id:'s5',hasMeasuredSnapshot:false},{...target,id:'s6',currentSnapshot:{courseAverage:null}}]
  const peers=comparableStudents(students,target)
  assert.deepEqual(peers.map(p=>p.id),['s1','s6'])
  const d=distributionData(peers,target)[0]
  assert.equal(d.n,1)
  assert.equal(d.current,70)
  assert.equal(d.median,null)
  assert.equal(d.density.length,0)
})
test('足量同组观测产生真实分位数，平行坐标不连接缺失项',()=>{
  const peers=[50,60,70,80,90].map((v,i)=>({...target,id:'s'+i,currentSnapshot:{courseAverage:v}}))
  const d=distributionData(peers,target)[0]
  assert.equal(d.median,70)
  assert.equal(d.low,60)
  assert.equal(d.high,80)
  assert.equal(d.density.length,51)
  const chart=parallelChart([{id:'a',x:0,y:10},{id:'b',x:null,y:20},{id:'c',x:80,y:90}],[{key:'x',label:'甲'},{key:'y',label:'乙'}],'c')
  assert.equal(chart.series.reduce((s,item)=>s+item.data.length,0),2)
  assert.deepEqual(chart.series.at(-1).data[0].value,[80,90])
})
