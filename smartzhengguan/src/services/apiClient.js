export const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
let refreshPending = null

export const getAccessToken = () => {
  const token = localStorage.getItem('token') || ''
  return token.startsWith('mock-') ? '' : token
}

export function clearSession() {
  for (const key of ['token', 'refresh-token', 'account-user', 'mock-user', 'mock-password', 'mock-user-profile', 'mock-navbar-messages']) localStorage.removeItem(key)
}

export function saveSession(tokens) {
  clearSession()
  localStorage.setItem('token', tokens.access)
  localStorage.setItem('refresh-token', tokens.refresh)
}

function describeError(value) {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(describeError).join('；')
  if (value && typeof value === 'object') return Object.values(value).map(describeError).join('；')
  return ''
}

export async function refreshAccessToken() {
  if (!refreshPending) {
    refreshPending = (async () => {
      const refresh = localStorage.getItem('refresh-token')
      if (!refresh) throw new Error('登录已过期，请重新登录')
      const response = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh }),
      })
      if (!response.ok) throw new Error('登录已过期，请重新登录')
      const data = await response.json()
      localStorage.setItem('token', data.access)
      return data.access
    })().finally(() => { refreshPending = null })
  }
  return refreshPending
}

export function expireSession() {
  clearSession()
  if (typeof window !== 'undefined' && !window.location.hash.startsWith('#/login')) {
    const redirect = window.location.hash.slice(1) || '/home'
    window.location.hash = `/login?redirect=${encodeURIComponent(redirect)}`
  }
}

export async function apiFetch(path, init = {}, options = {}) {
  const send = () => fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}), ...init.headers },
  })
  let response
  try { response = await send() } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('无法连接后端服务，请确认服务已启动后重试')
  }
  if (response.status === 401 && options.auth !== false) {
    try { await refreshAccessToken(); response = await send() }
    catch { expireSession(); throw new Error('登录已过期，请重新登录') }
    if (response.status === 401) expireSession()
  }
  if (!response.ok) {
    let detail = ''
    try { detail = describeError(await response.json()) } catch { /* server may return HTML */ }
    const error = new Error(detail || `请求失败（${response.status}），请稍后重试`)
    error.status = response.status
    throw error
  }
  return response
}

export async function requestJson(path, init = {}, options = {}) {
  const response = await apiFetch(path, init, options)
  return response.status === 204 ? null : response.json()
}

export const jsonRequest = (path, method, data, options) => requestJson(path, {
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
}, options)
