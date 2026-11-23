import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createContext, runInContext } from 'node:vm'

const source = await readFile(new URL('../src/utils/employmentHub.js', import.meta.url), 'utf8')
const { employmentQuery, shanghaiDate, formatEmploymentTime, monthDays, calendarEvents, safeEmploymentUrl, sourceStatusLabel, manualOpportunityPayload, recruitmentEntryLabel } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))

test('search encodes filters and excludes undefined and unsupported parameters', () => {
  const query = new URLSearchParams(employmentQuery({ q: '政治学 & 招聘', channel: 'exam', province: '山东', saved: true, featured: false, category: '', page: 2, pageSize: 12, ignored: 'secret' }).slice(1))
  assert.equal(query.get('q'), '政治学 & 招聘')
  assert.equal(query.get('saved'), '1')
  assert.equal(query.get('channel'), 'exam')
  assert.equal(query.get('province'), '山东')
  assert.equal(query.get('page'), '2')
  assert.equal(query.has('featured'), false)
  assert.equal(query.has('ignored'), false)
  assert.equal(employmentQuery({}), '')
})

test('all event dates use Beijing time across midnight regardless of browser timezone', () => {
  assert.equal(shanghaiDate('2026-11-30T18:00:00Z'), '2026-12-01')
  assert.equal(shanghaiDate('2026-11-23T00:30:00+08:00'), '2026-11-23')
  assert.equal(shanghaiDate(null), '')
  assert.equal(shanghaiDate('not a date'), '')
  assert.equal(formatEmploymentTime(null), '待核实')
})

test('calendar handles leap years and Monday-first alignment without invented days', () => {
  const days = monthDays('2024-02')
  assert.equal(days.length % 7, 0)
  assert.equal(days.filter(day => day.date).length, 29)
  assert.equal(days.findIndex(day => day.date), 3)
  assert.equal(days.find(day => day.day === 29).date, '2024-02-29')
  assert.deepEqual(monthDays('2026-13'), [])
  assert.deepEqual(monthDays('invalid'), [])
})

test('calendar displays only explicit nodes in the selected month, not the whole registration interval', () => {
  const items = [
    { id: 1, title: '已明确时间', registrationStart: '2026-10-01T08:00:00+08:00', registrationEnd: '2026-12-01T18:00:00+08:00', examAt: '2026-11-10T09:00:00+08:00' },
    { id: 2, title: '截止跨时区', registrationEnd: '2026-10-31T20:00:00Z' },
    { id: 3, title: '未明确时间', registrationStart: null, registrationEnd: null },
    { id: 4, title: '无效时间', examAt: 'invalid' },
  ]
  const events = calendarEvents(items, '2026-11')
  assert.deepEqual(events.map(event => [event.item.id, event.date, event.kind]), [[2, '2026-11-01', 'end'], [1, '2026-11-10', 'exam']])
})

test('several nodes on one day retain distinct event identifiers', () => {
  const events = calendarEvents([{ id: 9, registrationStart: '2026-11-12T08:00:00+08:00', registrationEnd: '2026-11-12T18:00:00+08:00' }], '2026-11')
  assert.equal(events.length, 2)
  assert.equal(new Set(events.map(event => event.key)).size, 2)
})

test('announcement and attachment links refuse executable protocols and embedded credentials', () => {
  assert.equal(safeEmploymentUrl('javascript:alert(1)'), '')
  assert.equal(safeEmploymentUrl('data:text/html,hello'), '')
  assert.equal(safeEmploymentUrl('https://user:password@example.com/job'), '')
  assert.equal(safeEmploymentUrl('/relative-link'), '')
  assert.equal(safeEmploymentUrl('https://example.com/job?id=1'), 'https://example.com/job?id=1')
})

test('manual forms preserve Beijing timestamps and leave unknown dates empty', () => {
  const form = { title: '  公告标题 ', url: ' https://example.com/job ', category: '人才引进', province: '山东', employer: ' 招聘单位 ', employerType: '未说明', publishedAt: '', registrationStart: '2026-11-23T08:30', registrationEnd: '2026-11-30T18:00:30', examAt: '', relatedMajors: ['行政管理'], matchKind: '方向相关', reviewState: '待核对', summary: ' 摘要 ', requirements: ' 要求 ', matchReasonsText: '管理相关\n\n  需核对具体专业  ' }
  const payload = manualOpportunityPayload(form)
  assert.equal(payload.registrationStart, '2026-11-23T08:30:00+08:00')
  assert.equal(payload.registrationEnd, '2026-11-30T18:00:30+08:00')
  assert.equal(payload.examAt, null)
  assert.equal(payload.publishedAt, null)
  assert.equal(payload.employerType, '不适用')
  assert.deepEqual(payload.matchReasons, ['管理相关', '需核对具体专业'])
  assert.equal(payload.title, '公告标题')
  assert.notEqual(payload.relatedMajors, form.relatedMajors)
})

test('source labels distinguish successful connection, errors, partial updates and official entrances', () => {
  assert.equal(sourceStatusLabel({ adapter: 'manual', enabled: false, status: 'manual' }), '官方入口')
  assert.equal(sourceStatusLabel({ enabled: true, status: 'success' }), '已接入')
  assert.equal(sourceStatusLabel({ enabled: false, status: 'success' }), '已暂停')
  assert.equal(sourceStatusLabel({ enabled: true, status: 'error' }), '同步失败')
  assert.equal(sourceStatusLabel({ enabled: true, status: 'partial' }), '部分同步')
  assert.equal(sourceStatusLabel({ enabled: false, status: 'pending' }), '待接入')
})

// Run the page's actual refresh logic with API and lifecycle boundaries stubbed.
// This catches stale deadline states without waiting a real minute or mounting UI.
async function pageRefreshHarness(opportunities) {
  const page = await readFile(new URL('../src/views/EmploymentHub.vue', import.meta.url), 'utf8')
  const script = page.match(/<script setup>([\s\S]*?)<\/script>/)[1]
  const timers = new Set(), listeners = new Map(), hooks = {}, calls = []
  const clock = { now: Date.parse('2026-11-23T09:00:00+08:00') }
  class PageDate extends Date {
    constructor(...args) { super(...(args.length ? args : [clock.now])) }
    static now() { return clock.now }
  }
  const context = {
    Date: PageDate, ref: value => ({ value }), reactive: value => value, computed: get => ({ get value() { return get() } }),
    onMounted: fn => { hooks.mount = fn }, onBeforeUnmount: fn => { hooks.unmount = fn },
    setInterval: (callback, delay) => { const timer = { callback, delay }; timers.add(timer); return timer }, clearInterval: timer => timers.delete(timer),
    document: { visibilityState: 'visible', addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) },
    ElMessage: { success() {}, error() {}, warning() {}, info() {} }, REAL_MAJORS: [],
    calendarEvents, formatEmploymentTime, manualOpportunityPayload, monthDays, recruitmentEntryLabel, safeEmploymentUrl, shanghaiDate, sourceStatusLabel,
    getEmploymentMeta: async () => ({ stats: { total: 1 }, canManage: true }),
    getOpportunities: async filters => { calls.push({ ...filters }); return opportunities ? opportunities(filters) : { items: [], count: 0 } },
    getEmploymentSources: async () => ({ items: [] }), getEmploymentSync: async () => ({ running: false, items: [], scheduler: { running: true } }),
    getEmploymentCalendar: async () => ({ items: [], count: 0 }),
  }
  for (const name of script.match(/import \{([^}]+)\} from '@element-plus\/icons-vue'/)[1].split(',')) context[name.trim()] = {}
  runInContext(script.replace(/^import .*$/gm, '') + '\nglobalThis.pageApi = { loadWorkspace, loadItems, loadDeadlines, refreshBusiness, applyFilters, filters, appliedFilters, formVisible, digestVisible, digestBusy, items, closingItems, meta };', createContext(context))
  return { api: context.pageApi, timers, listeners, hooks, calls, clock, document: context.document }
}

test('an open page updates expired opportunities every minute and removes all timers on unmount', async () => {
  let ended = false
  const harness = await pageRefreshHarness(filters => ({ items: filters.status ? (ended ? [] : [{ id: 1, status: '即将截止' }]) : [{ id: 1, status: ended ? '已截止' : '报名中' }], count: 1 }))
  harness.hooks.mount()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(harness.api.items.value[0].status, '报名中')
  assert.equal(harness.api.closingItems.value.length, 1)
  const timer = [...harness.timers].find(timer => timer.delay === 60000)
  assert.ok(timer, 'business refresh runs independently of collection task completion')
  ended = true
  await timer.callback()
  assert.equal(harness.api.items.value[0].status, '已截止')
  assert.equal(harness.api.closingItems.value.length, 0)
  harness.hooks.unmount()
  assert.equal(harness.timers.size, 0)
  assert.equal(harness.listeners.has('visibilitychange'), false)
  const callCount = harness.calls.length
  await timer.callback()
  assert.equal(harness.calls.length, callCount)
})

test('background refresh preserves form, digest and unsubmitted search state, then resumes when visible', async () => {
  const harness = await pageRefreshHarness()
  harness.hooks.mount()
  await new Promise(resolve => setImmediate(resolve))
  const { api, calls } = harness
  const baseline = calls.length
  for (const state of [api.formVisible, api.digestVisible, api.digestBusy]) {
    state.value = true
    await api.refreshBusiness()
    state.value = false
    assert.equal(calls.length, baseline)
  }
  api.filters.q = '尚未提交的关键字'
  await api.refreshBusiness()
  assert.equal(calls.length, baseline)
  await api.loadItems()
  assert.equal(calls.at(-1).q, '', 'pagination and retries keep the applied query')
  api.applyFilters()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls.at(-1).q, '尚未提交的关键字')
  harness.document.visibilityState = 'hidden'
  const beforeHidden = calls.length
  await api.refreshBusiness()
  assert.equal(calls.length, beforeHidden)
  harness.clock.now += 61000
  harness.document.visibilityState = 'visible'
  harness.listeners.get('visibilitychange')()
  await new Promise(resolve => setImmediate(resolve))
  assert.ok(calls.length > beforeHidden)
  assert.equal(api.filters.q, '尚未提交的关键字')
  harness.hooks.unmount()
})

test('late API responses cannot overwrite a newer list or deadline refresh', async () => {
  const pending = []
  const { api } = await pageRefreshHarness(() => new Promise(resolve => pending.push(resolve)))
  const older = api.loadItems(), newer = api.loadItems()
  pending[1]({ items: [{ id: 2 }], count: 1 })
  await newer
  pending[0]({ items: [{ id: 1 }], count: 1 })
  await older
  assert.equal(api.items.value[0].id, 2)
  const oldDeadline = api.loadDeadlines(), newDeadline = api.loadDeadlines()
  pending[3]({ items: [{ id: 4 }], count: 1 })
  await newDeadline
  pending[2]({ items: [{ id: 3 }], count: 1 })
  await oldDeadline
  assert.equal(api.closingItems.value[0].id, 4)
})

test('company and source filters reach backend and record kinds remain distinct', () => {
  const params = new URLSearchParams(employmentQuery({ companyTrack: 'state', sourceId: 7 }).slice(1))
  assert.equal(params.get('companyTrack'), 'state')
  assert.equal(params.get('sourceId'), '7')
  assert.equal(recruitmentEntryLabel({ metadata: { entryType: 'position' } }), '官网职位')
  assert.equal(recruitmentEntryLabel({ metadata: { entryType: 'announcement_index' } }), '公告索引')
  assert.equal(recruitmentEntryLabel({}), '招聘公告')
})
