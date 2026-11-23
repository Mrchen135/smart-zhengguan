<template>
  <section class="portrait-studio portrait-report" aria-label="群体发展画像">
    <header class="report-heading"><div><div class="report-kicker">STUDENT DEVELOPMENT / 学生发展画像</div><h1>{{ scope }}<span>群体画像</span></h1><p>{{ rows.length }} 个年级专业组合 · 更新 {{ updatedAt || '暂无' }}</p></div><span class="report-source-pill">{{ report.demo ? '演示数据' : '业务数据' }} · 本地分析</span></header>
    <div class="report-overview">
      <div class="report-overview-text"><span class="report-stage">{{ report.active===report.total ? '在读培养' : report.graduated===report.total ? '毕业发展' : '全阶段视角' }}</span><h2>{{ narrative.headline }}</h2><p>{{ narrative.description }}</p><div class="report-chips"><span>男 {{ report.male }} / 女 {{ report.female }}</span><span v-for="item in report.degreeTypes" :key="item.name">{{ item.name }} {{ item.value }}</span></div></div>
      <div class="report-numbers"><div><span>画像人数</span><strong>{{ report.total.toLocaleString() }}<small>人</small></strong></div><div><span>{{ report.graduated===report.total ? '就业占比' : '培养进度' }}</span><strong>{{ fmt(report.graduated===report.total?report.employmentRate:report.training) }}<small>%</small></strong></div><div><span>课程平均</span><strong>{{ fmt(report.course) }}<small>分</small></strong></div><div><span>科研成果</span><strong>{{ report.outputs }}<small>项</small></strong></div></div>
    </div>
    <ComparisonGallery :comparison="comparison" :selected="selected" :selected-narrative="selectedNarrative" :comparison-charts="comparisonCharts" :sankey-options="sankeyOptions" :sunburst-options="sunburstOptions" @select="selectFromChart" @clear="selectId=''" v-if="comparison.acrossGrades" />
    <nav class="report-tabs" aria-label="画像分析主题"><button v-for="tab in tabs" :key="tab.id" type="button" :class="{active:activeTab===tab.id}" :aria-pressed="activeTab===tab.id" @click="activeTab=tab.id">{{ tab.label }}<span>{{ tab.description }}</span></button></nav>
    <div class="report-body-grid">
      <article class="report-main-panel">
        <template v-if="activeTab==='destinations'"><div class="report-panel-title"><div><h2>去向结构</h2><p>按人去重 · 考公与就业分别呈现 · 在读不进入毕业去向分母</p></div><span class="report-unit">单位：人</span></div>
          <div class="report-destination-total"><div v-for="d in report.destinations" :key="d.key"><i :style="{background:d.color}"></i><span>{{ d.name }}</span><strong>{{ d.value }}</strong></div></div>
          <div class="report-stack total-stack" role="img" :aria-label="report.destinations.map(d=>d.name+d.value+'人').join('，')"><span v-for="d in report.destinations" :key="d.key" :style="{width:percentage(d.value,report.total)+'%',background:d.color}" :title="d.name+' '+d.value+'人'"></span></div>
          <div class="report-comparison-title">不同{{ comparison.dimension }}的去向构成 <span>点击{{ comparison.dimension }}查看单组解读</span></div>
          <div class="report-group-list"><button v-for="row in visibleRows" :key="row.id" class="report-group-row" :class="{selected:selectId===row.id}" @click="selectId=row.id"><span class="report-group-name">{{ comparison.label(row) }}<small>{{ comparison.acrossGrades ? row.major : row.grade }} · {{ row.totalStudents }}人</small></span><span class="report-stack"><span v-for="d in row.destinations.filter(d=>d.count)" :key="d.key" :style="{width:percentage(d.count,row.totalStudents)+'%',background:color(d.key)}" :title="d.label+' '+d.count+'人'"></span></span><span class="report-group-rate">{{ row.graduatedCount ? fmt(percentage(row.employedCount,row.graduatedCount))+'% 就业' : '在读' }}</span></button></div>
        </template>
        <template v-else-if="activeTab==='training'"><div class="report-panel-title"><div><h2>培养进展</h2><p>对照当前阶段理解进度，不把不同年级直接排名</p></div><span class="report-unit">有效快照 {{ report.snapshots }} 人</span></div>
          <div class="report-learning-grid"><div v-for="m in learning" :key="m.label"><div><span>{{ m.label }}</span><strong>{{ fmt(m.value) }}<small>{{ m.unit }}</small></strong></div><div class="report-meter"><span :style="{width:(m.value||0)+'%',background:m.color}"></span></div><p>{{ m.note }}</p></div></div>
          <div class="report-comparison-title">培养阶段分布</div><div class="report-stage-list"><div v-for="(item,index) in report.stages" :key="item.name"><b>{{ String(index+1).padStart(2,'0') }}</b><span>{{ item.name }}</span><strong>{{ item.value }}<small>人</small></strong><em>{{ fmt(percentage(item.value,report.total)) }}%</em></div></div>
          <div class="report-context-note">{{ report.graduated===report.total?'当前为毕业归档视角，培养与学分完成度为100%；课程均分、科研成果反映已保存的培养记录。':'进度是完成情况，不代表能力评分。课程、学分、实践应结合培养方案一起判断。' }}</div>
        </template>
        <template v-else><div class="report-panel-title"><div><h2>群体构成</h2><p>认识群体基础，不以性别和生源推断能力</p></div><span class="report-unit">{{ report.total }} 人</span></div>
          <div class="report-composition"><div><h3>性别分布</h3><div class="report-gender"><strong>{{ report.male }}<small>男</small></strong><strong>{{ report.female }}<small>女</small></strong></div><div class="report-stack"><span :style="{width:percentage(report.male,report.total)+'%',background:'#315fbd'}"></span><span :style="{width:percentage(report.female,report.total)+'%',background:'#69aaa6'}"></span></div></div><div><h3>培养层次</h3><div v-for="d in report.degreeTypes" :key="d.name" class="report-fact-line"><span>{{ d.name }}</span><strong>{{ d.value }} 人</strong></div></div></div>
          <h3 class="report-subtitle">主要生源地区</h3><div v-for="d in report.regions.slice(0,6)" :key="d.name" class="report-region"><span>{{ d.name }}</span><div class="report-meter"><span :style="{width:percentage(d.value,report.total)+'%',background:'#6694ca'}"></span></div><strong>{{ d.value }}</strong></div>
        </template>
        <el-pagination v-if="activeTab==='destinations'&&rows.length>8" v-model:current-page="page" :page-size="8" :total="rows.length" layout="prev, pager, next" />
      </article>
      <aside class="report-reading"><div class="report-kicker">INTERPRETATION / 画像解读</div><h2>{{ selected?.major || '当前群体' }}</h2><p class="report-selected-scope">{{ selected?.grade || '当前查询范围' }} · {{ selected?.totalStudents || report.total }} 人 <el-button v-if="rows.length>1" text size="small" @click="selectId=''">查看整体</el-button></p>
        <p v-for="finding in selectedNarrative.findings" :key="finding" class="report-finding">{{ finding }}</p><div class="report-advice"><span>建议方向</span><p>{{ selectedNarrative.recommendation }}</p></div>
        <div v-if="activeTab==='destinations'&&selectedReport.industries.length" class="report-industry"><h3>主要就业行业</h3><div v-for="d in selectedReport.industries.slice(0,4)" :key="d.name"><span>{{ d.name }}</span><strong>{{ d.value }} 人</strong></div></div>
        <div v-else class="report-small-facts"><div><span>人均实践</span><strong>{{ fmt(selectedReport.practice) }} 小时</strong></div><div><span>{{ selectedReport.graduated===selectedReport.total?'归档前60日导师沟通均值':'近60日导师沟通均值' }}</span><strong>{{ fmt(selectedReport.meetings) }} 次</strong></div><div><span>有奖助记录</span><strong>{{ selectedReport.awards }} 人</strong></div></div>
      </aside>
    </div>
    <ComparisonGallery :comparison="comparison" :selected="selected" :selected-narrative="selectedNarrative" :comparison-charts="comparisonCharts" :sankey-options="sankeyOptions" :sunburst-options="sunburstOptions" @select="selectFromChart" @clear="selectId=''" v-if="!comparison.acrossGrades" />
    <footer class="report-footnote">来源：学生档案、培养计划、学位、奖助、就业与画像快照。{{ report.demo ? '当前为有来源标记的演示数据；未知去向保留，未到阶段的日期按不适用处理。' : '' }} 图中人数、比例和文字随查询范围同步更新。</footer>
  </section>
</template>
<script setup>
import {computed,ref,watch} from 'vue'
import ComparisonGallery from './ComparisonGallery.vue'
import {buildCohortStructure,fmt,sankeyChart,sunburstChart} from '../../utils/portraitCharts'
import {summarizePortrait,portraitNarrative} from '../../utils/portraitInsights'
import {comparisonContext,buildComparisonCharts} from '../../utils/cohortComparisonCharts'
import './portrait.css'
import './report.css'
const props=defineProps({rows:{type:Array,default:()=>[]},scope:{type:String,default:''},updatedAt:{type:String,default:''}})
const activeTab=ref('destinations'),selectId=ref(''),page=ref(1)
const tabs=[{id:'destinations',label:'发展去向',description:'就业与职业方向'},{id:'training',label:'培养进展',description:'课程、学分与研究'},{id:'composition',label:'群体构成',description:'层次、性别与生源'}]
const report=computed(()=>summarizePortrait(props.rows)),narrative=computed(()=>portraitNarrative(report.value))
const selected=computed(()=>props.rows.find(r=>r.id===selectId.value))
const selectedReport=computed(()=>selected.value?summarizePortrait([selected.value]):report.value)
const selectedNarrative=computed(()=>portraitNarrative(selectedReport.value))
const comparison=computed(()=>comparisonContext(props.rows))
const comparisonCharts=computed(()=>buildComparisonCharts(props.rows,selectId.value))
const visibleRows=computed(()=>comparison.value.rows.slice((page.value-1)*8,page.value*8))
const learning=computed(()=>[{label:'课程均分',value:report.value.course,unit:'分',color:'#315fbd',note:'来自当前有效快照'},{label:'学分完成',value:report.value.credit,unit:'%',color:'#329c91',note:'已完成学分 / 要求学分'},{label:'培养进度',value:report.value.training,unit:'%',color:'#6888b3',note:'每名学生取当前培养记录'},{label:'科研任务完成',value:report.value.research,unit:'%',color:'#bba16d',note:'任务完成度，非科研能力评分'}])
const structure=computed(()=>buildCohortStructure(props.rows))
const sankeyOptions=computed(()=>{const s=structure.value;return w=>sankeyChart(s,w)})
const sunburstOptions=computed(()=>sunburstChart(structure.value,selectId.value))
const percentage=(n,d)=>d?Number((n*100/d).toFixed(1)):0
const color=key=>({employment:'#315fbd',civil_service:'#329c91',unknown:'#d9ad5a',in_study:'#a7bbd7'}[key]||'#8795a7')
watch(()=>props.rows,()=>{selectId.value='';page.value=1;activeTab.value=report.value.active===report.value.total?'training':'destinations'},{immediate:true})
function selectFromChart(event){const id=event?.data?.entityId;if(id&&props.rows.some(r=>r.id===id))selectId.value=id}
</script>
