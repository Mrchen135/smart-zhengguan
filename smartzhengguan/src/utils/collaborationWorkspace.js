export const taskFields = ['title', 'question', 'grade', 'major', 'topic']
export const emptyTask = () => ({ title: '', question: '', grade: '', major: '', topic: 'training' })
export const taskDraft = task => Object.fromEntries(taskFields.map(key => [key, task[key] || (key === 'topic' ? 'training' : '')]))
export const inputSignature = (form, scenario = '', identifiers = true) => JSON.stringify(scenario ? { scenario, identifiers } : taskDraft(form))
export const executionLabel = mode => ({ local: '本地处理完成', cloud: '云端辅助完成', fallback: '已采用本地结果' }[mode] || '等待执行')
export const taskStatusLabel = status => ({ ready: '待执行', running: '执行中', completed: '已完成', fallback: '已回退本地', failed: '执行中断' }[status] || status)

export function collaborationPresentation({ kind = 'database', plan = null, result = null, mode = 'local', checking = false, executing = false } = {}) {
  const sample = kind === 'sample', audit = result?.audit
  const blocked = plan?.route === 'local', used = audit?.cloudUsed === true, attempted = audit?.cloudAttempted === true
  const groups = plan?.snapshot?.groups || []
  const ready = Boolean(plan), completed = Boolean(result?.answer)
  return {
    sourceLabel: sample ? '固定虚构样本 · 不读取数据库' : '当前数据库 · 本地统计快照',
    sourceData: sample ? plan?.sourceData : plan?.snapshot,
    outboundLabel: attempted ? (used ? '本次已用于云端分析' : '已尝试云端调用') : completed ? '本次未向云端发送' : blocked ? '禁止外发' : '获准内容预览 · 尚未发送',
    steps: [
      { title: '本地数据', value: checking ? '正在读取' : !ready ? '等待检查' : sample ? plan.inputFieldCount + ' 个输入字段' : plan.studentCount + ' 人',
        caption: sample ? '使用固定虚构样本' : ready ? groups.length + ' 个年级专业组合' : '根据任务范围统计', status: ready ? 'done' : checking ? 'active' : 'waiting' },
      { title: '隐私检查', value: !ready ? '等待检查' : blocked ? '保留本地' : '允许受控外发',
        caption: !ready ? '核对个人信息与分组人数' : sample ? plan.protectedFieldCount + ' 个字段留在本地或泛化' : '仅使用所选主题的群体统计', status: ready ? blocked ? 'blocked' : 'done' : 'waiting' },
      { title: '协同执行', value: executing ? '正在执行' : completed ? used ? '云端已返回' : attempted ? '采用本地结果' : '本地已完成' : !ready ? '等待执行' : blocked || mode === 'local' ? '本地处理' : '云端辅助',
        caption: executing ? '等待服务端返回实际结果' : completed ? attempted ? '已实际发起云端请求' : '未调用云端' : blocked ? '本任务不向云端发送数据' : '点击执行后开始处理', status: executing ? 'active' : completed ? attempted && !used ? 'blocked' : 'done' : 'waiting' },
      { title: '结果与记录', value: completed ? '结果已生成' : '等待结果', caption: completed ? '可查看依据、建议和执行记录' : '完成后展示真实执行方式', status: completed ? 'done' : 'waiting' },
    ],
  }
}

export function combinedHistory(tasks = [], audits = [], scenarios = []) {
  const names = Object.fromEntries(scenarios.map(item => [item.id, item.title]))
  return [
    ...tasks.map(task => ({ key: 'task-' + task.id, kind: 'database', id: task.id, title: task.title, source: '数据库任务',
      scope: (task.grade || '全部年级') + ' · ' + (task.major || '全部专业'), status: taskStatusLabel(task.status), at: task.createdAt })),
    ...audits.filter(audit => audit.scenario !== 'custom').map(audit => ({ key: 'audit-' + audit.requestId, kind: 'sample', audit,
      title: names[audit.scenario] || '隐私示例', source: '固定虚构样本', scope: '机制示例 · 不读取学生数据库', status: executionLabel(audit.executionMode), at: audit.createdAt })),
  ].sort((a, b) => new Date(b.at) - new Date(a.at))
}
