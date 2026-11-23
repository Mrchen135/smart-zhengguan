import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
const load=async path=>import('data:text/javascript;base64,'+Buffer.from(await readFile(new URL(path,import.meta.url),'utf8')).toString('base64'))
const {cohortInsights,studentActions,summarizePortrait,portraitNarrative}=await load('../src/utils/portraitInsights.js')
const {buildCohortStructure}=await load('../src/utils/portraitCharts.js')
test('conclusions use selected scope and separate missing records from unemployment',()=>{
 const a={id:'a',grade:'2023级',major:'甲',totalStudents:10,maleCount:4,femaleCount:6,destinationPendingCount:6,employedCount:3,unresolvedCount:1,trainingCoverageCount:2}
 const result=cohortInsights([a]);assert.equal(result.pending,6);assert.equal(result.unresolved,1);assert.equal(result.trainingMissing,8);assert.equal(result.completeness,100)
 assert.match(result.conclusions[0].evidence,/6 人/);assert.equal(cohortInsights([]).conclusions.length,0)
})
test('sankey uses exhaustive destination states and never invents unknown ones',()=>{
 const row={id:'a',grade:'2023级',major:'甲',totalStudents:10,maleCount:4,femaleCount:6,destinations:[{key:'study',label:'升学',count:3},{key:'in_study',label:'在读（暂不纳入）',count:7}]}
 const s=buildCohortStructure([row]);assert.equal(s.links.filter(l=>l.source==='cohort:a').reduce((n,l)=>n+l.value,0),10);assert.equal(s.unknownGender,0);assert.ok(!JSON.stringify(s).includes('未标注'))
 assert.equal(buildCohortStructure([{...row,destinations:[]}]).links.at(-1).target,'destination:去向待核实')
})
test('personal actions respond to overdue work and avoid unsupported peer comparisons',()=>{
 assert.match(studentActions({currentSnapshot:{overdueTasksCount:3}},[])[0].evidence,/3 项/)
 assert.equal(studentActions({currentSnapshot:{}},[])[0].title,'按培养节点持续跟进')
 assert.match(studentActions({currentSnapshot:{}},[{key:'courseAverage',label:'课程均分',current:60,median:80,low:75,n:10,unit:'分'}])[0].action,/具体课程/)
})

test('portrait rates use graduates only and keep all destination categories exhaustive',()=>{
 const rows=[{totalStudents:100,graduatedCount:100,activeCount:0,snapshotCount:100,courseAverage:80,creditCompletionRate:100,trainingObservedAverage:100,destinations:[{key:'employment',label:'就业',count:65},{key:'civil_service',label:'考公',count:25},{key:'study',label:'升学',count:7},{key:'unknown',label:'未知',count:3}],employmentIndustries:[{name:'公共服务',value:40}]},{totalStudents:100,graduatedCount:0,activeCount:100,snapshotCount:100,courseAverage:90,creditCompletionRate:60,trainingObservedAverage:40,destinations:[{key:'in_study',label:'在读',count:100}]}]
 const result=summarizePortrait(rows)
 assert.equal(result.employmentRate,65);assert.equal(result.civilRate,25);assert.equal(result.unknownRate,3)
 assert.equal(result.course,85);assert.equal(result.credit,80);assert.equal(result.destinations.reduce((n,d)=>n+d.value,0),200)
 assert.match(portraitNarrative(result).description,/100 人在读、100 人毕业/)
 assert.match(portraitNarrative(summarizePortrait([rows[0]])).findings[0],/公共服务/)
})
test('portrait handles empty and missing measurements without showing zero scores',()=>{
 assert.equal(summarizePortrait([]).course,null);assert.deepEqual(portraitNarrative(summarizePortrait([])).findings,[])
 const row={totalStudents:8,activeCount:8,snapshotCount:0,overdueStudentCount:2}
 const narrative=portraitNarrative(summarizePortrait([row]));assert.match(narrative.description,/均在读/);assert.match(narrative.recommendation,/2 人/)
 assert.match(narrative.findings[0],/不足/)
})
