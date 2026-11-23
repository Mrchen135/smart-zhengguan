<template>
  <section class="task-workspace">
    <div class="workspace-tools"><div><span class="status-dot" :class="{ online: cloudAvailable }" />{{ loading ? '正在连接协同服务' : cloudAvailable ? '云端辅助已启用' : '本地处理可用' }}<span class="tool-divider">·</span><span class="task-muted">先检查数据，再执行任务</span></div><div class="tool-buttons"><el-dropdown trigger="click" :disabled="busy" @command="chooseTemplate"><el-button :disabled="busy">选择任务或机制示例 <el-icon><ArrowDown /></el-icon></el-button><template #dropdown><el-dropdown-menu><el-dropdown-item v-for="item in examples" :key="item.id" :command="item.id">任务模板 · {{ item.label }}</el-dropdown-item><el-dropdown-item v-for="(item,index) in demoCatalog.scenarios" :key="item.id" :command="'sample:'+item.id" :divided="index===0">机制示例 · {{ item.title }}</el-dropdown-item></el-dropdown-menu></template></el-dropdown><el-button :disabled="busy" @click="newTask">新建任务</el-button></div></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="task-error" />
    <el-alert v-if="catalogError || demoError" :title="[catalogError,demoError].filter(Boolean).join('；')" type="warning" :closable="false" class="task-error"><template #default><el-button text :disabled="busy" @click="refresh">重新连接</el-button></template></el-alert>

    <div class="task-layout">
      <article class="task-card task-composer">
        <div class="section-heading"><div><div class="task-eyebrow">01 / 定义需求</div><h2>{{ sampleId ? '使用机制示例' : '发布具体任务' }}</h2></div><el-tag size="small" :type="sampleId?'warning':'info'">{{ sampleId?'固定虚构样本':'数据库任务' }}</el-tag></div>
        <p class="task-muted">{{ sampleId ? '示例使用固定虚构数据，沿用右侧相同的检查、执行和结果流程。' : '写清分析对象、关心的问题和期望结果。统计由本地服务从当前数据库生成。' }}</p>
        <el-form label-position="top" :disabled="busy">
          <el-form-item label="任务名称"><el-input v-model="form.title" aria-label="任务名称" :readonly="Boolean(sampleId)" maxlength="100" placeholder="例如：2025级培养进展分析" /></el-form-item>
          <template v-if="!sampleId">
            <div class="task-fields"><el-form-item label="年级范围"><el-select v-model="form.grade" aria-label="任务年级" placeholder="全部年级"><el-option label="全部年级" value=""/><el-option v-for="g in catalog.grades" :key="g" :label="g" :value="g"/></el-select></el-form-item><el-form-item label="专业范围"><el-select v-model="form.major" aria-label="任务专业" placeholder="全部专业"><el-option label="全部专业" value=""/><el-option v-for="m in catalog.majors" :key="m" :label="m" :value="m"/></el-select></el-form-item></div>
            <el-form-item label="分析主题"><el-select v-model="form.topic" aria-label="任务主题"><el-option v-for="t in catalog.topics" :key="t.id" :label="t.label" :value="t.id"/></el-select></el-form-item>
          </template>
          <el-form-item :label="sampleId?'示例任务说明':'具体任务要求'"><el-input v-model="form.question" aria-label="具体任务要求" type="textarea" :readonly="Boolean(sampleId)" :rows="5" maxlength="1200" :show-word-limit="!sampleId" placeholder="例如：分析2025级各专业的培养进展，按数据依据、建议行动和下一步安排给出建议。请勿填写姓名、学号、联系方式等个人信息。" /></el-form-item>
          <el-checkbox v-if="sampleId" v-model="includeIdentifiers" class="identifier-option">在虚构样本中加入身份字段</el-checkbox>
          <div v-else class="task-examples"><button v-for="item in examples" :key="item.id" type="button" :disabled="busy" @click="chooseTemplate(item.id)">{{ item.label }}</button></div>
          <el-button type="primary" class="publish-button" :loading="checking" :disabled="busy || !validDraft || isCurrent || (!sampleId && Boolean(catalogError))" @click="inspect">{{ isCurrent ? '已完成数据检查' : sampleId ? '检查示例数据' : '发布任务并检查数据' }}</el-button>
          <p class="task-muted task-hint">{{ sampleId?'示例内容固定；需要提出自己的问题时，点击“新建任务”。':'发布只生成统计快照。查看右侧检查结果后，再点击“执行任务”。' }}</p>
        </el-form>
      </article>

      <article class="task-card task-runner" ref="processPanel" :aria-busy="checking || executing">
        <div class="section-heading"><div><div class="task-eyebrow">02 / 数据如何参与分析</div><h2>{{ plan ? currentTitle : '端云协同处理过程' }}</h2></div><el-tag v-if="selected && isCurrent" :type="selected.status==='fallback'?'warning':'info'">#{{ selected.id }} · {{ executing?'执行中':taskStatusLabel(selected.status) }}</el-tag></div>
        <p class="source-caption"><el-icon><Monitor /></el-icon>{{ view.sourceLabel }}<span v-if="plan && !sampleId"> · {{ plan.demoRecordCount }} 人为演示记录</span></p>
        <el-alert v-if="dirty" title="任务内容已修改，请重新发布并检查数据后执行。" type="warning" :closable="false" class="task-error" />
        <CollaborationFlow :steps="view.steps" />
        <template v-if="plan">
          <div class="boundary-summary"><el-icon><Lock /></el-icon><span>{{ plan.reason }}</span></div>
          <div class="task-run-actions"><div><span class="control-label">执行方式</span><el-radio-group v-model="mode" :disabled="busy || Boolean(result) || (!sampleId && selected?.status!=='ready')" aria-label="任务执行方式"><el-radio-button label="local">本地处理</el-radio-button><el-radio-button label="cloud" :disabled="!cloudAvailable || plan.route==='local'">云端辅助</el-radio-button></el-radio-group></div><el-button v-if="!result && (sampleId || selected?.status==='ready')" type="primary" :loading="executing" :disabled="busy" @click="execute">执行任务</el-button><el-tag v-else-if="result" :type="result.audit.cloudUsed?'success':'info'">{{ executionLabel(result.audit.executionMode) }}</el-tag></div>
          <p v-if="!cloudAvailable" class="task-muted">云端暂不可用，可以执行本地统计。</p>
          <p v-if="selected && ['running','failed'].includes(selected.status)" class="task-muted">{{ selected.status==='running'?'任务正在处理，可刷新记录查看进展。':'任务执行中断，可复制为新任务重试。' }}<el-button text :disabled="busy" @click="openTask(selected.id)">刷新任务记录</el-button></p>


        </template>
        <div v-else class="process-placeholder"><el-icon :size="30"><Connection /></el-icon><h3>{{ checking?'正在统计并检查数据':'发布任务后，在这里查看全过程' }}</h3><p>检查完成后，下方将展示本地输入、获准外发内容和分析结果。</p><p>也可以从上方选择政策问答、群体分析或小群体保护示例。</p></div>


        <el-button v-if="selected && isCurrent" text :disabled="busy" class="copy-task" @click="copyTask">复制为新任务</el-button>
      </article>
    </div>

    <section v-if="plan" class="task-card task-details" aria-label="任务数据与分析结果">
      <div class="section-heading"><div><div class="task-eyebrow">DETAILS / 数据与结果</div><h2>本次任务的数据与分析</h2></div><el-tag size="small" :type="sampleId?'warning':'info'">{{ sampleId?'固定虚构样本':'数据库任务' }}</el-tag></div>
          <div class="payload-grid">
            <section class="payload-panel"><div class="panel-heading"><h3>{{ sampleId?'本地样本输入':'本地统计快照' }}</h3><span>{{ sampleId?'虚构样本':date(plan.snapshot.capturedAt) }}</span></div>
              <pre v-if="sampleId" class="payload-code">{{ json(view.sourceData) }}</pre>
              <template v-else><el-table :data="plan.snapshot.groups" size="small" max-height="220" class="snapshot-table"><el-table-column prop="grade" label="年级" min-width="70"/><el-table-column prop="major" label="专业" min-width="110"/><el-table-column prop="studentCount" label="人数" width="58"/><el-table-column prop="activeCount" label="在读" width="58"/><el-table-column prop="graduatedCount" label="毕业" width="58"/></el-table><details class="payload-details"><summary>查看完整主题统计</summary><pre class="payload-code">{{ json(view.sourceData) }}</pre></details></template>
              <p class="panel-note">{{ sampleId?'可在右侧核对哪些字段被移除或泛化。':'此处展示统计结果，学生姓名、学号和个人明细保留在本地。' }}</p>
            </section>
            <section class="payload-panel outbound-panel"><div class="panel-heading"><h3>获准外发内容</h3><el-button text size="small" :disabled="!plan.cloudPayload" @click="copyPayload">复制内容</el-button></div><div class="outbound-state" :class="{blocked:plan.route==='local'}">{{ view.outboundLabel }}</div><pre class="payload-code">{{ plan.cloudPayload ? json(plan.cloudPayload) : '无外发内容。此任务只能在本地处理。' }}</pre><p class="panel-note">{{ plan.cloudPayload?'包含任务需要的公开问题或统计摘要；选择本地处理时不会发送。':'隐私检查已关闭本任务的云端通道。' }}</p></section>
          </div>
          <details v-if="sampleId && plan.decisions" class="field-details" open><summary>逐字段处理明细 · {{ plan.approvedFieldCount }} 个字段获准外发</summary><el-table :data="plan.decisions" size="small"><el-table-column prop="label" label="数据项目" min-width="100"/><el-table-column label="处理方式" width="105"><template #default="{row}"><el-tag size="small" :type="actionType(row.action)">{{ actionLabel(row.action) }}</el-tag></template></el-table-column><el-table-column prop="reason" label="处理依据" min-width="190"/></el-table></details>
        <section v-if="result" class="task-result" aria-live="polite"><div class="section-heading"><div><div class="task-eyebrow">03 / 结果与执行记录</div><h2>{{ executionLabel(result.audit.executionMode) }}</h2></div><el-button plain size="small" @click="exportResult">下载结果</el-button></div><el-alert v-if="result.fallbackReason" :title="result.fallbackReason" type="warning" :closable="false"/><p class="task-answer">{{ result.answer.directAnswer }}</p><div class="answer-grid"><div><h3>分析依据</h3><ul><li v-for="(item,i) in result.answer.reasoning" :key="i">{{ item }}</li></ul></div><div><h3>建议行动</h3><ol><li v-for="(item,i) in result.answer.actionPlan" :key="i">{{ item }}</li></ol></div></div><div class="execution-footer"><span>{{ result.audit.cloudUsed?'云端结果已采用':result.audit.cloudAttempted?'已尝试云端调用，采用本地结果':'本地执行，未调用云端' }}</span><span>耗时 {{ seconds(result.audit.elapsedMs) }} 秒</span><span>{{ date(result.audit.createdAt) }}</span><el-button link type="primary" @click="selectedAudit=result.audit">查看执行记录</el-button></div></section>
    </section>

    <section class="task-card task-history"><div class="section-heading"><div><div class="task-eyebrow">HISTORY / 任务与执行记录</div><h2>从历史记录继续</h2></div><div class="tool-buttons"><el-button plain :disabled="!history.length" @click="exportHistory">导出记录</el-button><el-button :disabled="busy" :loading="loading" @click="refresh">刷新</el-button></div></div><p class="task-muted">当前账号最近 50 个数据库任务与 20 次机制示例执行。数据库任务可重新打开，示例保存执行元数据。</p><el-table :data="history" row-key="key" empty-text="发布任务或执行示例后，这里会留下记录" @row-click="openHistory" class="history-table"><el-table-column prop="title" label="任务 / 示例" min-width="220"/><el-table-column prop="source" label="数据来源" width="130"/><el-table-column prop="scope" label="范围" min-width="200"/><el-table-column prop="status" label="状态" width="150"/><el-table-column label="时间" width="170"><template #default="{row}">{{ date(row.at) }}</template></el-table-column><el-table-column label="操作" width="100"><template #default="{row}"><el-button text type="primary" :disabled="busy" @click.stop="openHistory(row)">{{ row.kind==='database'?'打开任务':'执行记录' }}</el-button></template></el-table-column></el-table></section>
    <footer class="scope-note"><el-icon><InfoFilled /></el-icon>本页任务按所选来源处理数据。人数阈值为 {{ minimumGroupSize }} 人，是保护措施之一；分析建议仍需结合实际培养方案与本地记录复核。</footer>
    <el-dialog :model-value="Boolean(selectedAudit)" title="执行记录详情" width="min(700px,94vw)" @close="selectedAudit=null"><pre class="audit-detail">{{ json(selectedAudit) }}</pre><template #footer><el-button @click="selectedAudit=null">关闭</el-button></template></el-dialog>
  </section>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, Connection, InfoFilled, Lock, Monitor } from '@element-plus/icons-vue'
import CollaborationFlow from './CollaborationFlow.vue'
import { getCollaborationTasks, createCollaborationTask, getCollaborationTask, runCollaborationTask, getPrivacyScenarios, inspectPrivacyTask, executePrivacyTask } from '../../services/privacyService'
import { collaborationPresentation, combinedHistory, emptyTask, executionLabel, inputSignature, taskDraft, taskStatusLabel } from '../../utils/collaborationWorkspace'

const catalog = ref({ grades: [], majors: [], topics: [], tasks: [], cloudAvailable: false })
const demoCatalog = ref({ scenarios: [], auditEntries: [], cloudAvailable: false })
const loading = ref(false), checking = ref(false), executing = ref(false), error = ref(''), catalogError = ref(''), demoError = ref('')
const form = ref(emptyTask()), sampleId = ref(''), includeIdentifiers = ref(true), mode = ref('local')
const processPanel = ref(null)
const selected = ref(null), demoPlan = ref(null), demoResult = ref(null), selectedAudit = ref(null), checkedSignature = ref('')
let requestVersion = 0, refreshVersion = 0, disposed = false
const busy = computed(() => loading.value || checking.value || executing.value)
const signature = computed(() => inputSignature(form.value, sampleId.value, includeIdentifiers.value))
const isCurrent = computed(() => Boolean(checkedSignature.value && signature.value === checkedSignature.value))
const dirty = computed(() => Boolean(checkedSignature.value && !isCurrent.value))
const plan = computed(() => isCurrent.value ? sampleId.value ? demoPlan.value : selected.value?.plan : null)
const result = computed(() => { const value = sampleId.value ? demoResult.value : selected.value?.result; return plan.value && value?.answer ? value : null })
const cloudAvailable = computed(() => Boolean((sampleId.value ? demoCatalog.value : catalog.value).cloudAvailable))
const minimumGroupSize = computed(() => (sampleId.value ? demoCatalog.value : catalog.value).minimumGroupSize || 5)
const validDraft = computed(() => sampleId.value ? Boolean(demoCatalog.value.scenarios.find(item => item.id === sampleId.value)) : Boolean(form.value.title.trim() && form.value.question.trim().length >= 8))
const currentTitle = computed(() => sampleId.value ? form.value.title : selected.value?.title || form.value.title)
const view = computed(() => collaborationPresentation({ kind: sampleId.value ? 'sample' : 'database', plan: plan.value, result: result.value, mode: mode.value, checking: checking.value, executing: executing.value || (isCurrent.value && selected.value?.status === 'running') }))
const history = computed(() => combinedHistory(catalog.value.tasks, demoCatalog.value.auditEntries, demoCatalog.value.scenarios))
const examples = [
  { id: 'training', label: '培养进展', title: '2025级培养进展分析', grade: '2025级', major: '', topic: 'training', question: '分析2025级各专业的课程、学分和培养进展，按“数据依据、建议行动、下一步安排”给出三条建议。缺少阶段标准时请说明，不推断整体滞后。' },
  { id: 'employment', label: '毕业去向', title: '2023级毕业去向分析', grade: '2023级', major: '', topic: 'employment', question: '分析2023级毕业生的就业、考公及未知去向分布，将仍在读的博士单列，给出面向学院就业指导工作的三条具体建议。' },
  { id: 'research', label: '跨年级科研', title: '同专业跨年级科研与实践比较', grade: '', major: '国际关系', topic: 'research', question: '比较国际关系专业不同年级的科研与实践记录，考虑在读年限与毕业阶段，说明差异及下一步培养建议。' },
]
const sampleQuestions = { individual: '分析固定虚构样本中的课程和逾期事项，演示个体画像为何留在本地处理。', policy: '硕士开题前通常需要核对哪些培养事项？使用固定公开问题与演示参考材料，观察身份信息如何被移除。', cohort: '分析固定42人样本的培养事项统计，观察群体数字通过检查后如何参与云端辅助。', small: '检查固定3人样本的统计请求，演示小群体人数不足时如何关闭外发通道。' }
const json = value => JSON.stringify(value, null, 2)
const date = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'
const seconds = value => (Number(value || 0) / 1000).toFixed(1)
const actionLabel = action => ({ local: '保留本地', remove: '移除', generalize: '泛化问题', keep: '允许外发' }[action] || action)
const actionType = action => ({ local: 'info', remove: 'danger', generalize: 'warning', keep: 'success' }[action] || 'info')

function clearSelection() { requestVersion += 1; selected.value = null; demoPlan.value = null; demoResult.value = null; checkedSignature.value = ''; error.value = ''; mode.value = 'local' }
function newTask() { if (busy.value) return; clearSelection(); sampleId.value = ''; form.value = emptyTask() }
function chooseTemplate(id) {
  if (busy.value) return
  if (id.startsWith('sample:')) {
    const sample = demoCatalog.value.scenarios.find(item => item.id === id.slice(7))
    if (!sample) return
    clearSelection(); sampleId.value = sample.id; includeIdentifiers.value = true
    form.value = { ...emptyTask(), title: sample.title, question: sampleQuestions[sample.id] || sample.description }
  } else {
    const example = examples.find(item => item.id === id)
    if (!example) return
    clearSelection(); sampleId.value = ''; form.value = taskDraft(example)
    if (!catalog.value.grades.includes(form.value.grade)) form.value.grade = ''
    if (!catalog.value.majors.includes(form.value.major)) form.value.major = ''
  }
}
async function refresh() {
  const version = ++refreshVersion; loading.value = true
  try {
    const responses = await Promise.allSettled([getCollaborationTasks(), getPrivacyScenarios()])
    if (disposed || version !== refreshVersion) return
    if (responses[0].status === 'fulfilled') { catalog.value = responses[0].value; catalogError.value = '' }
    else catalogError.value = '数据库任务：' + responses[0].reason.message
    if (responses[1].status === 'fulfilled') { demoCatalog.value = responses[1].value; demoError.value = '' }
    else demoError.value = '机制示例：' + responses[1].reason.message
  } finally { if (!disposed && version === refreshVersion) loading.value = false }
}
function selectTask(task) {
  sampleId.value = ''; selected.value = task; demoPlan.value = null; demoResult.value = null
  form.value = taskDraft(task); checkedSignature.value = inputSignature(form.value)
  mode.value = task.result?.audit?.cloudUsed ? 'cloud' : task.result?.answer ? 'local' : catalog.value.cloudAvailable && task.plan.route === 'cloud_eligible' ? 'cloud' : 'local'
}
async function inspect() {
  if (busy.value || !validDraft.value || isCurrent.value) return
  const version = ++requestVersion, submitted = signature.value, scenario = sampleId.value
  checking.value = true; error.value = ''
  try {
    if (scenario) {
      const checked = await inspectPrivacyTask({ scenario, includeIdentifiers: includeIdentifiers.value })
      if (disposed || version !== requestVersion || signature.value !== submitted) return
      selected.value = null; demoPlan.value = checked; demoResult.value = null; checkedSignature.value = submitted; mode.value = 'local'; await showProcess()
    } else {
      const task = await createCollaborationTask(taskDraft(form.value))
      if (disposed || version !== requestVersion || signature.value !== submitted) return
      selectTask(task); await refresh(); await showProcess()
    }
  } catch (cause) { if (!disposed && version === requestVersion) error.value = cause.message || '检查失败，请重试' }
  finally { if (!disposed && version === requestVersion) checking.value = false }
}
async function showProcess() { await nextTick(); if (!disposed) processPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
async function openTask(id) {
  if (busy.value) return
  const version = ++requestVersion; loading.value = true; error.value = ''
  try { const task = await getCollaborationTask(id); if (!disposed && version === requestVersion) { selectTask(task); await showProcess() } }
  catch (cause) { if (!disposed && version === requestVersion) error.value = cause.message }
  finally { if (!disposed && version === requestVersion) loading.value = false }
}
async function execute() {
  if (busy.value || !plan.value || result.value) return
  const version = ++requestVersion, scenario = sampleId.value, task = selected.value
  executing.value = true; error.value = ''
  try {
    const completed = scenario ? await executePrivacyTask({ scenario, includeIdentifiers: includeIdentifiers.value, executionMode: mode.value }) : await runCollaborationTask(task.id, { executionMode: mode.value, payloadDigest: task.plan.payloadDigest })
    if (disposed || version !== requestVersion) return
    if (scenario) { demoPlan.value = completed.plan; demoResult.value = completed; demoCatalog.value.auditEntries = [completed.audit, ...demoCatalog.value.auditEntries.filter(item => item.requestId !== completed.audit.requestId)].slice(0, 20) }
    else { selected.value = completed; await refresh() }
  } catch (cause) {
    if (disposed || version !== requestVersion) return
    // A timed-out request may still have saved its result. Read it; never repeat execution automatically.
    if (!scenario) { try { const recovered = await getCollaborationTask(task.id); if (!disposed && version === requestVersion) { selected.value = recovered; await refresh() } } catch {} }
    if (!disposed && version === requestVersion && !result.value) error.value = cause.message + (scenario ? '' : '；可刷新任务记录查看进展。')
  } finally { if (!disposed && version === requestVersion) executing.value = false }
}
function copyTask() { if (busy.value || !selected.value) return; const draft = taskDraft(selected.value); newTask(); form.value = { ...draft, title: (draft.title + '（新任务）').slice(0, 100) } }
function openHistory(row) { if (busy.value) return; if (row.kind === 'database') openTask(row.id); else selectedAudit.value = row.audit }
async function copyPayload() { try { await navigator.clipboard.writeText(json(plan.value.cloudPayload)); ElMessage.success('已复制获准外发内容') } catch { ElMessage.info('请在内容框中选中文字复制') } }
function download(content, name, type = 'text/plain;charset=utf-8') { const url = URL.createObjectURL(new Blob([content], { type })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; document.body.appendChild(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
function exportResult() { const value = result.value; if (!value) return; download([currentTitle.value, '来源：' + view.value.sourceLabel, form.value.question, value.answer.directAnswer, '分析依据', ...value.answer.reasoning, '建议行动', ...value.answer.actionPlan, '执行方式：' + executionLabel(value.audit.executionMode), value.fallbackReason || '', '执行记录', json(value.audit)].join('\n\n'), '协同任务结果-' + (selected.value?.id || sampleId.value) + '.txt') }
function exportHistory() { download(json({ exportedAt: new Date().toISOString(), tasks: catalog.value.tasks, sampleAudits: demoCatalog.value.auditEntries }), '端云协同执行记录.json', 'application/json;charset=utf-8') }
onMounted(refresh)
onBeforeUnmount(() => { disposed = true; requestVersion += 1; refreshVersion += 1 })
</script>
<style scoped>
.task-workspace{color:#29455c}.workspace-tools,.workspace-tools>div,.tool-buttons{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.workspace-tools{justify-content:space-between;margin-bottom:20px;font-size:12px;color:#547388;gap:15px}.workspace-tools .task-muted{margin:0}.tool-buttons :deep(.el-button+.el-button){margin-left:0}.tool-buttons .el-icon{margin-left:6px}.status-dot{height:7px;width:7px;border-radius:50%;background:#9fabb7}.status-dot.online{background:#298e7e;box-shadow:0 0 0 3px #298e7e10}.tool-divider{color:#bdcbd5}.task-layout{display:grid;grid-template-columns:minmax(340px,0.9fr) minmax(0,1.4fr);gap:20px;align-items:stretch}.task-card{border:1px solid #dfe8ee;background:#fff;border-radius:14px;padding:24px;min-width:0}.task-runner{display:flex;flex-direction:column;scroll-margin-top:90px}.task-runner :deep(.collaboration-flow){grid-template-columns:repeat(2,minmax(0,1fr))}.task-details{margin-top:24px}.task-composer{background:linear-gradient(150deg,#f8fbfd,#fff 45%)}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}.task-eyebrow{font-size:10px;letter-spacing:1.7px;color:#79909f;margin-bottom:9px}.task-card h2{font-size:19px;line-height:1.6;color:#1a4058;margin:0;font-weight:600}.task-muted{font-size:12px;color:#718698;line-height:1.85;margin:12px 0 17px}.task-composer .el-form{margin-top:24px}.task-composer :deep(.el-form-item__label){font-size:12px;color:#49677c;padding-bottom:6px}.task-composer :deep(.el-form-item){margin-bottom:18px}.task-fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}.task-composer .el-select{width:100%}.task-examples{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 18px}.task-examples button{border:1px solid #dbe6ed;background:#f6f9fc;border-radius:5px;color:#56748b;padding:6px 9px;font:inherit;font-size:11px;cursor:pointer}.task-examples button:disabled{cursor:wait;opacity:.55}.publish-button{width:100%;background:#286e86;border-color:#286e86}.task-hint{margin-bottom:0;font-size:11px}.identifier-option{margin-bottom:20px;white-space:normal}.task-error{margin-bottom:17px}.source-caption{display:flex;gap:6px;align-items:center;flex-wrap:wrap;color:#748b9b;font-size:11px;line-height:1.9;margin:12px 0 20px}.source-caption .el-icon{color:#5f829a}.boundary-summary{display:flex;align-items:flex-start;gap:9px;padding:14px 0;color:#577285;font-size:12px;line-height:1.9;border-bottom:1px solid #e8eef2}.boundary-summary .el-icon{margin-top:4px;flex-shrink:0;color:#3c8278}.task-run-actions{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;margin:20px 0}.task-run-actions>div{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.control-label{font-size:12px;color:#688094}.payload-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:24px}.payload-panel{min-width:0;border:1px solid #e2eaf0;border-radius:10px;background:#fafcfd;padding:15px}.outbound-panel{background:#f5faf8;border-color:#dcebe4}.panel-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:24px;margin-bottom:12px;flex-wrap:wrap}.panel-heading h3,.answer-grid h3{font-size:13px;color:#355b70;font-weight:600;margin:0}.panel-heading>span{font-size:10px;color:#8a9dab}.panel-heading .el-button{font-size:11px;padding:0}.outbound-state{font-size:10px;color:#38836c;margin-bottom:8px}.outbound-state.blocked{color:#a17432}.payload-code{font:11px/1.9 Consolas,'Microsoft Yahei',monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto;margin:0;color:#4e697e;background:#f0f4f7;border-radius:6px;padding:12px}.outbound-panel .payload-code{background:#eaf4ef;color:#426e60}.panel-note{font-size:10px;line-height:1.9;color:#8193a3;margin:12px 0 0}.payload-details{margin-top:13px}.payload-details summary,.field-details summary{cursor:pointer;color:#3f6c8a;font-size:11px;line-height:1.8}.payload-details pre{margin-top:10px}.snapshot-table{--el-table-header-bg-color:#f0f5f8;--el-table-bg-color:transparent;--el-table-tr-bg-color:transparent;--el-table-header-text-color:#6d8495;font-size:11px}.field-details{margin-top:20px}.field-details summary{margin-bottom:12px}.field-details :deep(.el-table){font-size:11px}.process-placeholder{flex:1;min-height:180px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#8aa1b3;padding:24px 8px}.process-placeholder>.el-icon{color:#76a0b4;background:#f1f7fa;padding:14px;width:58px;height:58px;border-radius:15px;margin-bottom:18px}.process-placeholder h3{font-size:15px;font-weight:500;color:#55758b;margin:0 0 10px}.process-placeholder p{font-size:12px;line-height:1.9;margin:4px 0;max-width:420px}.task-result{border-top:1px solid #e3ebf0;padding-top:24px;margin-top:26px}.task-result .el-alert{margin-top:14px}.task-answer{font-size:14px;line-height:1.95;color:#345a73;white-space:pre-wrap;margin:17px 0}.answer-grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}.answer-grid ul,.answer-grid ol{font-size:12px;line-height:1.95;padding-left:17px;color:#5e788c;margin-top:9px}.answer-grid li{margin-bottom:7px}.execution-footer{display:flex;align-items:center;gap:8px 14px;flex-wrap:wrap;border-top:1px solid #e9eef3;padding-top:15px;margin-top:20px;font-size:10px;color:#8498a7}.execution-footer .el-button{font-size:11px}.copy-task{font-size:11px;margin-top:auto;align-self:flex-start}.task-history{margin-top:24px}.history-table{cursor:pointer;font-size:12px}.scope-note{display:flex;gap:7px;align-items:flex-start;font-size:11px;color:#8295a5;line-height:1.9;padding:20px 2px}.scope-note .el-icon{flex-shrink:0;margin-top:4px}.audit-detail{font:12px/1.9 Consolas,'Microsoft Yahei',monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:60vh;overflow:auto}@media(max-width:1300px){.task-layout{gap:16px}.task-card{padding:20px}}@media(max-width:1000px){.task-layout{grid-template-columns:1fr}.task-fields{grid-template-columns:1fr 1fr;gap:12px}.payload-grid{grid-template-columns:1fr 1fr}.task-composer .el-form{display:grid;grid-template-columns:1fr 1fr;gap:0 20px}.task-composer .task-fields,.task-examples,.publish-button,.task-hint,.identifier-option{grid-column:1/-1}.task-composer :deep(.el-form-item:has(textarea)){grid-column:1/-1}.process-placeholder{min-height:210px}.task-runner :deep(.collaboration-flow){grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:600px){.task-runner :deep(.collaboration-flow){grid-template-columns:repeat(2,minmax(0,1fr))}.answer-grid{grid-template-columns:1fr;gap:5px}.task-card{padding:17px}.task-fields,.payload-grid,.task-composer .el-form{grid-template-columns:1fr}.task-fields{gap:0}.workspace-tools{align-items:flex-start}.task-card h2{font-size:17px}.task-run-actions{align-items:flex-start}.task-run-actions>div{align-items:flex-start;flex-direction:column}}
</style>
