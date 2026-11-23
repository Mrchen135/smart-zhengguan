import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
const source=await readFile(new URL('../src/utils/employmentMap.js',import.meta.url),'utf8')
const {buildProvinceLookup,normalizeEmploymentRegions,employmentRegionTooltip}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))
const geo=JSON.parse(await readFile(new URL('../public/maps-china-100000.json',import.meta.url),'utf8'))
test('full API province names join every region in the bundled map without losing people',()=>{
 const lookup=buildProvinceLookup(geo)
 const rows=geo.features.filter(f=>f.properties.fullname).map(f=>({name:f.properties.fullname,value:7}))
 const output=normalizeEmploymentRegions(rows,lookup)
 assert.equal(output.length,rows.length)
 assert.equal(output.reduce((n,r)=>n+r.value,0),rows.length*7)
 assert.ok(output.every(r=>geo.features.some(f=>f.properties.name===r.name)))
 assert.deepEqual(normalizeEmploymentRegions([{name:'山东省',value:427},{name:'北京市',value:415}],lookup),[{name:'山东',value:427},{name:'北京',value:415}])
})
test('fallback maps with full region names also accept short API aliases',()=>{
 const fallback={features:geo.features.map(f=>({properties:{name:f.properties.fullname||f.properties.name}}))}
 const names=normalizeEmploymentRegions([{name:'山东',value:3},{name:'广西',value:4},{name:'香港',value:5}],buildProvinceLookup(fallback))
 assert.deepEqual(names.map(r=>r.name),['山东省','广西壮族自治区','香港特别行政区'])
})
test('mixed short and full names merge once; unmatched or invalid rows cannot fabricate counts',()=>{
 assert.deepEqual(normalizeEmploymentRegions([{name:'山东省',value:4},{name:' 山东 ',value:'6'},{name:'其他',value:100},{name:'未知',value:2},{name:'北京',value:null},{name:'江苏省',value:'invalid'},{name:'上海市',value:-1}],buildProvinceLookup(geo)),[{name:'山东',value:10}])
})
test('tooltips distinguish unavailable data from measured zero without exposing HTML',()=>{
 assert.match(employmentRegionTooltip({name:'北京',data:{value:0}}),/0人/)
 assert.match(employmentRegionTooltip({name:'河北',value:NaN}),/暂无就业地区记录/)
 assert.ok(!employmentRegionTooltip({name:'<img>',data:{value:1}}).includes('<img>'))
})
