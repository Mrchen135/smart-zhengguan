import { apiFetch } from './apiClient'

async function requestPrivacy(path, payload) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), path.startsWith('tasks/') ? 120000 : 40000)
  try {
    const response = await apiFetch(`/privacy-collaboration/${path}/`, {
      method: payload ? 'POST' : 'GET',
      headers: { Accept: 'application/json', ...(payload ? { 'Content-Type': 'application/json' } : {}) },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
      signal: controller.signal,
      cache: 'no-store',
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : Object.values(data || {}).flat().filter(v => typeof v === 'string').join('；')
      throw new Error(detail || (response.status === 429 ? '操作较频繁，请稍后再试' : '隐私协同服务暂不可用，请稍后重试'))
    }
    if (!data || typeof data !== 'object') throw new Error('服务返回的数据格式不正确，请重试')
    return data
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('等待结果超时，请打开任务记录确认状态')
    throw error
  } finally {
    clearTimeout(timeout)
  }
}

export const getPrivacyScenarios = () => requestPrivacy('scenarios')
export const inspectPrivacyTask = (payload) => requestPrivacy('inspect', payload)
export const executePrivacyTask = (payload) => requestPrivacy('execute', payload)

export const getCollaborationTasks = () => requestPrivacy('tasks')
export const createCollaborationTask = payload => requestPrivacy('tasks', payload)
export const getCollaborationTask = id => requestPrivacy('tasks/' + id)
export const runCollaborationTask = (id, payload) => requestPrivacy('tasks/' + id + '/execute', payload)
