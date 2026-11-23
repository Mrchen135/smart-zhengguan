import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createContext, runInContext } from 'node:vm'
import { computed, ref } from 'vue'

const utilsSource = await readFile(new URL('../src/utils/collaborationWorkspace.js', import.meta.url), 'utf8')
const helpers = await import('data:text/javascript;base64,' + Buffer.from(utilsSource).toString('base64'))
const { collaborationPresentation, combinedHistory, inputSignature } = helpers
const plan = { route: 'cloud_eligible', studentCount: 42, demoRecordCount: 42, payloadDigest: 'test-digest', snapshot: { groups: [{ grade: '2025级', major: '国际关系', studentCount: 42 }], capturedAt: '2026-11-24T00:00:00+08:00' }, cloudPayload: { groups: [{ studentCount: 42 }] } }
const completed = mode => ({ answer: { directAnswer: '结果', reasoning: ['依据'], actionPlan: ['核对'] }, audit: { executionMode: mode, cloudAttempted: mode !== 'local', cloudUsed: mode === 'cloud', requestId: 'test', createdAt: '2026-11-24T00:00:00+08:00', elapsedMs: 123 } })

test('an approved payload is a preview until an execution audit confirms transmission', () => {
  const view = collaborationPresentation({ plan, mode: 'cloud' })
  assert.equal(view.outboundLabel, '获准内容预览 · 尚未发送')
  assert.equal(view.steps[2].value, '云端辅助')
  assert.equal(view.steps[2].status, 'waiting')
  assert.equal(view.steps[3].status, 'waiting')
  const local = collaborationPresentation({ plan, mode: 'cloud', result: completed('local') })
  assert.equal(local.outboundLabel, '本次未向云端发送')
  assert.equal(local.steps[2].value, '本地已完成')
})

test('cloud success and fallback use recorded outcomes rather than the current mode selector', () => {
  const cloud = collaborationPresentation({ plan, mode: 'local', result: completed('cloud') })
  assert.equal(cloud.steps[2].value, '云端已返回')
  assert.equal(cloud.outboundLabel, '本次已用于云端分析')
  const fallback = collaborationPresentation({ plan, result: completed('fallback') })
  assert.equal(fallback.steps[2].value, '采用本地结果')
  assert.equal(fallback.steps[2].status, 'blocked')
  assert.equal(fallback.steps[3].status, 'done')
})

test('small-group samples keep their source distinct and close the outbound path', () => {
  const sample = { route: 'local', sourceData: { studentCount: 3 }, cloudPayload: null, inputFieldCount: 3, protectedFieldCount: 3 }
  const view = collaborationPresentation({ kind: 'sample', plan: sample, mode: 'cloud' })
  assert.match(view.sourceLabel, /固定虚构样本/)
  assert.equal(view.outboundLabel, '禁止外发')
  assert.equal(view.steps[1].value, '保留本地')
  assert.equal(view.steps[2].value, '本地处理')
})

test('input fingerprints change with database scope or sample identity settings', () => {
  const form = { title: '任务', question: '分析当前培养进展', grade: '2025级', major: '', topic: 'training' }
  assert.notEqual(inputSignature(form), inputSignature({ ...form, grade: '2023级' }))
  assert.notEqual(inputSignature(form), inputSignature({ ...form, question: '比较不同年级培养进展' }))
  assert.notEqual(inputSignature(form, 'policy', true), inputSignature(form, 'policy', false))
  assert.notEqual(inputSignature(form, 'policy'), inputSignature(form, 'small'))
})

test('one history retains source labels and excludes duplicate custom-task audits', () => {
  const history = combinedHistory([{ id: 1, title: '数据库任务', status: 'ready', createdAt: '2026-11-23' }], [
    { scenario: 'custom', requestId: 'a', executionMode: 'cloud', createdAt: '2026-11-24' },
    { scenario: 'small', requestId: 'b', executionMode: 'local', createdAt: '2026-11-24' },
  ], [{ id: 'small', title: '小群体保护' }])
  assert.equal(history.length, 2)
  assert.equal(history[0].title, '小群体保护')
  assert.equal(history[0].source, '固定虚构样本')
  assert.equal(history[1].kind, 'database')
})

async function harness(overrides = {}) {
  const source = await readFile(new URL('../src/components/collaboration/TaskWorkspace.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const calls = [], hooks = {}
  const context = {
    ...helpers, computed, ref, nextTick: async () => {}, onMounted: fn => { hooks.mount = fn }, onBeforeUnmount: fn => { hooks.unmount = fn },
    ArrowDown: {}, Connection: {}, InfoFilled: {}, Lock: {}, Monitor: {},
    ElMessage: { success() {}, info() {} },
    getCollaborationTasks: async () => ({ grades: ['2025级'], majors: ['国际关系'], topics: [{ id: 'training', label: '培养进展' }], tasks: [], cloudAvailable: true }),
    getPrivacyScenarios: async () => ({ scenarios: [{ id: 'small', title: '小群体保护' }, { id: 'policy', title: '公开政策问答' }], auditEntries: [], cloudAvailable: true }),
    createCollaborationTask: async data => { calls.push(['create', data]); return { id: 9, ...data, grade: '2025级', status: 'ready', plan, result: {} } },
    runCollaborationTask: async (id, data) => { calls.push(['run', id, data]); return { ...context.page.selected.value, status: 'completed', result: completed(data.executionMode) } },
    inspectPrivacyTask: async data => { calls.push(['inspectSample', data]); return { route: 'local', sourceData: { studentCount: 3 }, cloudPayload: null, inputFieldCount: 3, protectedFieldCount: 3 } },
    executePrivacyTask: async data => { calls.push(['runSample', data]); return { plan: context.page.demoPlan.value, ...completed('local') } },
    getCollaborationTask: async id => ({ ...context.page.selected.value, id, status: 'completed', result: completed('cloud') }),
    ...overrides,
  }
  runInContext(script + '\nglobalThis.page = { form, sampleId, includeIdentifiers, checkedSignature, selected, demoPlan, demoResult, plan, result, isCurrent, mode, error, refresh, chooseTemplate, inspect, execute, openTask, newTask };', createContext(context))
  await context.page.refresh()
  return { page: context.page, calls, hooks }
}

test('database publication uses the strict task API and editing invalidates the checked plan', async () => {
  const { page, calls } = await harness()
  page.chooseTemplate('training')
  await page.inspect()
  assert.equal(calls[0][0], 'create')
  assert.equal(page.isCurrent.value, true)
  assert.equal(page.selected.value.id, 9)
  page.form.value.question += '再比较不同阶段。'
  assert.equal(page.plan.value, null)
  await page.execute()
  assert.equal(calls.filter(call => call[0] === 'run').length, 0)
})

test('samples share the runner but use only their dedicated fixed-sample endpoints', async () => {
  const { page, calls } = await harness()
  page.chooseTemplate('sample:small')
  await page.inspect()
  assert.equal(page.mode.value, 'local')
  await page.execute()
  assert.deepEqual(calls.map(call => call[0]), ['inspectSample', 'runSample'])
  assert.deepEqual(Object.keys(calls[1][1]).sort(), ['executionMode', 'includeIdentifiers', 'scenario'])
  assert.equal(page.result.value.audit.cloudUsed, false)
  page.includeIdentifiers.value = false
  assert.equal(page.plan.value, null)
  assert.equal(page.result.value, null)
})

test('lost execution responses recover saved results without issuing another cloud request', async () => {
  let executions = 0
  const { page } = await harness({ runCollaborationTask: async () => { executions++; throw new Error('等待超时') } })
  page.chooseTemplate('training'); await page.inspect(); await page.execute()
  assert.equal(executions, 1)
  assert.equal(page.result.value.audit.cloudUsed, true)
  assert.equal(page.error.value, '')
  await page.execute()
  assert.equal(executions, 1)
})

test('unmounted workspaces do not accept late inspection responses', async () => {
  let finish
  const { page, hooks } = await harness({ inspectPrivacyTask: () => new Promise(resolve => { finish = resolve }) })
  page.chooseTemplate('sample:small')
  const pending = page.inspect()
  hooks.unmount()
  finish({ route: 'local', sourceData: {}, cloudPayload: null })
  await pending
  assert.equal(page.plan.value, null)
})
