<template>
  <section class="portrait-studio portrait-report student-studio" aria-label="个人成长画像">
    <header class="report-heading"><div><div class="report-kicker">STUDENT JOURNEY / 个人成长档案</div><h1>{{ target.name || '选择学生' }}<span>的成长画像</span></h1><p>{{ target.grade }} · {{ target.major }} · {{ target.degreeType }}</p></div><span class="report-source-pill">{{ target.recordKind==='demonstration' ? '演示档案' : '学生档案' }} · {{ target.currentStatus || '当前状态' }}</span></header>
    <div class="portrait-link-bar student-selector"><div><strong>切换分析对象</strong><span>与下方 AI 解读同步</span></div><el-select :model-value="target.id || undefined" filterable :filter-method="filterNames" placeholder="搜索姓名或学号" aria-label="切换个人画像学生" @change="$emit('select',$event)" @visible-change="search=''">
      <el-option v-for="s in choices" :key="s.id" :value="s.id" :label="s.name+' · '+s.studentId+' · '+s.major" /></el-select></div>
    <el-empty v-if="!target.studentId" description="当前范围暂无学生档案，请调整筛选条件" />
    <template v-else>
      <div class="report-overview"><div class="report-overview-text"><span class="report-stage">{{ target.trainingStage || '培养中' }}</span><h2>{{ graduated ? '培养已完成，继续职业发展' : '把阶段目标转化为具体行动' }}</h2><p>{{ summary }}</p><div class="report-chips"><span>{{ target.gender || '待完善' }}</span><span>导师 {{ target.advisorName || '待分配' }}</span><span>{{ graduated ? '当前去向：'+target.destination : '预计毕业：'+target.expectedGraduationDate }}</span></div></div>
        <div class="report-numbers"><div><span>课程均分</span><strong>{{ fmt(snapshot.courseAverage) }}<small>分</small></strong></div><div><span>学分完成</span><strong>{{ fmt(snapshot.creditCompletionRate) }}<small>%</small></strong></div><div><span>科研成果</span><strong>{{ snapshot.researchOutputCount ?? '—' }}<small>项</small></strong></div><div><span>累计实践</span><strong>{{ snapshot.practiceHours ?? '—' }}<small>小时</small></strong></div></div>
      </div>
      <div class="report-body-grid"><article class="report-main-panel"><div class="report-panel-title"><div><h2>{{ graduated ? '培养与发展记录' : '当前培养路径' }}</h2><p>基本档案、阶段进展和当前快照集中查看</p></div><span class="report-unit">{{ (target.capturedAt || '').slice(0,10) }} {{ graduated?'归档':'记录' }}</span></div>
        <div class="report-timeline"><div>入学<small>{{ target.enrolledOn || '待完善' }}</small></div><div>{{ target.trainingStage || '培养中' }}<small>{{ graduated?'培养要求已完成':'当前培养阶段' }}</small></div><div>{{ graduated?'已毕业':'预计毕业' }}<small>{{ target.graduatedOn || target.expectedGraduationDate || '待完善' }}</small></div></div>
        <dl class="report-identity"><div v-for="item in identity" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value || '—' }}</dd></div></dl>
        <div class="report-learning-grid"><div v-for="m in learning" :key="m.label"><div><span>{{ m.label }}</span><strong>{{ fmt(m.value) }}<small>%</small></strong></div><div class="report-meter"><span :style="{width:(m.value||0)+'%',background:m.color}"></span></div><p>{{ m.note }}</p></div></div>
        <p class="report-personal-summary">{{ graduated ? '毕业后不再以在读培养进度生成催办建议。下方对照展示毕业前归档的课程与培养记录。' : insight }}</p>
      </article><aside class="report-reading"><div class="report-kicker">NEXT STEP / 发展建议</div><h2>{{ graduated?'职业与校友支持':'下一步成长行动' }}</h2><div v-for="item in actions" :key="item.title" class="report-action-item"><h3>{{ item.title }}</h3><p>{{ item.evidence }}</p><p>{{ item.action }}</p></div><div class="report-small-facts"><div><span>{{ graduated?'归档前60日导师沟通':'近60日导师沟通' }}</span><strong>{{ snapshot.advisorMeetingCount60d ?? '—' }} 次</strong></div><div><span>项目参与</span><strong>{{ snapshot.projectParticipationCount ?? '—' }} 项</strong></div><div v-if="!graduated"><span>逾期任务</span><strong>{{ snapshot.overdueTasksCount ?? '—' }} 项</strong></div><div><span>同组参考样本</span><strong>{{ peers.length }} 人</strong></div></div></aside></div>
      <el-collapse class="report-more"><el-collapse-item title="查看同组分布与本人位置" name="comparison"><article class="portrait-chart-panel"><div class="report-panel-title"><div><h2>同阶段、同专业的指标对照</h2><p>绿色菱形为本人；有效样本不足5人时不作群体位置比较</p></div></div><PortraitChart :options="violinOptions" description="课程、学分、科研等指标的同组分布及个人位置" /><p class="portrait-chart-note">位置差异用于理解当前记录，不代表能力排名。只比较同年级、专业、学位类别和学籍阶段的同类来源档案。</p></article></el-collapse-item></el-collapse>
      <footer class="report-footnote">来源：学生基本档案、当前培养与就业记录、画像快照。{{ target.recordKind==='demonstration'?'本档案及历史数据为带来源标记的演示数据。':'' }} 建议由当前记录生成，结合具体培养或职业目标确认后执行。</footer>
    </template>
  </section>
</template>
<script setup>
import {computed,ref} from 'vue'
import PortraitChart from './PortraitChart.vue'
import {comparableStudents,distributionData,fmt,STUDENT_METRICS,score,violinChart} from '../../utils/portraitCharts'
import {studentActions} from '../../utils/portraitInsights'
import './portrait.css'
import './report.css'
const props=defineProps({target:{type:Object,default:()=>({})},students:{type:Array,default:()=>[]},candidates:{type:Array,default:()=>[]}})
defineEmits(['select'])
const search=ref('')
const choices=computed(()=>{const text=search.value.trim().toLowerCase();const list=props.candidates.filter(s=>!text||(s.name+' '+s.studentId+' '+s.major+' '+s.grade).toLowerCase().includes(text)).slice(0,40);if(props.target.id&&!list.some(s=>s.id===props.target.id))list.unshift(props.target);return list})
const snapshot=computed(()=>props.target.currentSnapshot||{}),graduated=computed(()=>props.target.currentStatus==='已毕业')
const peers=computed(()=>comparableStudents(props.students,props.target).filter(s=>s.currentStatus===props.target.currentStatus&&s.recordKind===props.target.recordKind))
const distributions=computed(()=>distributionData(peers.value,props.target)),violinOptions=computed(()=>violinChart(distributions.value))
const summary=computed(()=>graduated.value?'已于 '+props.target.graduatedOn+' 完成培养。当前去向为'+(props.target.destination||'未知')+'，后续关注职业发展与校友联系。':'当前处于'+(props.target.trainingStage||'培养')+'阶段，学分完成 '+fmt(snapshot.value.creditCompletionRate)+'%，培养进度 '+fmt(snapshot.value.trainingPlanCompletionRate)+'%。')
const identity=computed(()=>[{label:'学号',value:props.target.studentId},{label:'生源地区',value:props.target.sourceRegion},{label:'培养层次',value:props.target.degreeType},{label:'要求学分',value:props.target.requiredCredits?props.target.requiredCredits+' 学分':'—'},...(graduated.value?[{label:'去向分类',value:props.target.destination},{label:'就业行业 / 地区',value:[props.target.employmentIndustry,props.target.employmentProvince].filter(Boolean).join(' / ')||'不适用'}]:[])])
const learning=computed(()=>[{label:'培养计划',value:snapshot.value.trainingPlanCompletionRate,color:'#315fbd',note:graduated.value?'已完成培养要求':'按当前培养阶段推进'},{label:'科研任务',value:snapshot.value.researchTaskCompletionRate,color:'#329c91',note:'已完成任务占比，非能力评分'}])
const actions=computed(()=>{if(!graduated.value)return studentActions(props.target,distributions.value);const d=props.target.destinationKey;if(d==='civil_service')return [{title:'围绕招考阶段准备',evidence:'当前明确登记为考公，尚不等同已录用。',action:'确认报考岗位与考试时间，安排笔试、面试训练；录用后更新就业单位和地区。'}];if(d==='unknown')return [{title:'保持毕业后的联系',evidence:'当前去向为未知，不能据此判断是否就业。',action:'就业老师通过校友联系方式确认本人近况与意愿，再提供岗位信息或考试支持。'}];return [{title:'积累岗位经验与职业能力',evidence:'当前就业方向：'+(props.target.employmentIndustry||'已记录就业')+'。',action:'围绕岗位需要制定三个月能力提升目标；结合个人意愿参与同专业校友经验交流。'}]})
const insight=computed(()=>{const comparable=distributions.value.filter(d=>d.current!==null&&d.median!==null),lowest=[...comparable].sort((a,b)=>(a.current-a.median)-(b.current-b.median))[0];if(!lowest)return '当前同组有效样本不足，先依据本人培养计划和阶段目标判断。';const gap=lowest.current-lowest.median;return lowest.label+'为 '+fmt(lowest.current)+lowest.unit+'，'+(Math.abs(gap)<.05?'与同组中位数一致':(gap<0?'低于':'高于')+'同组中位数 '+fmt(Math.abs(gap))+(lowest.unit==='%'?'个百分点':'分'))+'。差异需要结合课程要求和培养阶段理解。'})
function filterNames(query){search.value=query}
</script>
