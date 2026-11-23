const queryKeys = ['q', 'channel', 'category', 'province', 'major', 'employerType', 'companyTrack', 'sourceId', 'status', 'saved', 'featured', 'page', 'pageSize', 'month']

export function employmentQuery(filters = {}) {
  const query = new URLSearchParams()
  for (const key of queryKeys) {
    const value = filters[key]
    if (value !== undefined && value !== null && value !== '' && value !== false) query.set(key, value === true ? '1' : String(value))
  }
  const text = query.toString()
  return text ? `?${text}` : ''
}

export function shanghaiDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date)
  const part = (type) => parts.find((item) => item.type === type)?.value
  return `${part('year')}-${part('month')}-${part('day')}`
}

export function formatEmploymentTime(value, withTime = false) {
  if (!value) return '待核实'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return '待核实'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    ...(withTime ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}),
  }).format(date)
}

export function monthDays(month) {
  if (!/^\d{4}-\d{2}$/.test(month || '')) return []
  const [year, number] = month.split('-').map(Number)
  if (number < 1 || number > 12) return []
  const first = new Date(Date.UTC(year, number - 1, 1))
  const offset = (first.getUTCDay() + 6) % 7
  const count = new Date(Date.UTC(year, number, 0)).getUTCDate()
  const cells = Array.from({ length: offset }, (_, index) => ({ key: `blank-${index}`, date: '', day: '' }))
  for (let day = 1; day <= count; day++) cells.push({ key: `${month}-${String(day).padStart(2, '0')}`, date: `${month}-${String(day).padStart(2, '0')}`, day })
  while (cells.length % 7) cells.push({ key: `end-${cells.length}`, date: '', day: '' })
  return cells
}

export function calendarEvents(items = [], month) {
  const fields = [['registrationStart', '报名开始', 'start'], ['registrationEnd', '报名截止', 'end'], ['examAt', '考试', 'exam']]
  return items.flatMap((item) => fields.flatMap(([field, label, kind]) => {
    const date = shanghaiDate(item[field])
    return date && date.startsWith(`${month}-`) ? [{ key: `${item.id}-${field}`, date, time: item[field], label, kind, item }] : []
  })).sort((a, b) => new Date(a.time) - new Date(b.time))
}

export function safeEmploymentUrl(value) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}

export function sourceStatusLabel(source) {
  const status = source.status
  if (status === 'error' || status === 'failed') return '同步失败'
  if (status === 'partial') return '部分同步'
  if (status === 'running') return '同步中'
  if (status === 'success') return source.enabled ? '已接入' : '已暂停'
  if (status === 'manual' || source.adapter === 'manual') return '官方入口'
  return source.enabled ? '待首次同步' : '待接入'
}

export function manualOpportunityPayload(form) {
  const timestamp = (value) => value ? `${value.length === 16 ? value + ':00' : value}+08:00` : null
  return {
    title: form.title.trim(), url: form.url.trim(), category: form.category, province: form.province,
    employer: form.employer.trim(), employerType: form.category === '企业招聘' ? form.employerType : '不适用',
    publishedAt: form.publishedAt || null, registrationStart: timestamp(form.registrationStart),
    registrationEnd: timestamp(form.registrationEnd), examAt: timestamp(form.examAt),
    summary: form.summary.trim(), requirements: form.requirements.trim(), relatedMajors: [...form.relatedMajors],
    matchKind: form.matchKind, reviewState: form.reviewState,
    matchReasons: (form.matchReasonsText || '').split('\n').map(value => value.trim()).filter(Boolean),
  }
}

export function recruitmentEntryLabel(item) {
  return ({ position: '官网职位', announcement: '招聘公告', announcement_index: '公告索引' })[item?.metadata?.entryType] || '招聘公告'
}
