import { apiFetch, requestJson, jsonRequest } from './apiClient'

export const getSharedOptions = () => requestJson('/shared-options/')
export const getHomeDashboardData = () => requestJson('/home/')
export const getAdmissionData = () => requestJson('/admission/')
export const getAcademicStatusData = () => requestJson('/academic-status/')
export const getAcademicChangeData = () => requestJson('/academic-change/')
export const getTrainingData = () => requestJson('/training/')
export const getTrainingCourseData = () => requestJson('/training-course/')
export const getDegreeData = () => requestJson('/degree/')
export const getDegreeDefenseData = () => requestJson('/degree-defense/')
export const getIntelligentPredictionData = () => requestJson('/intelligent-prediction/')
export const getScholarshipData = () => requestJson('/scholarship/')
export const getEmploymentData = () => requestJson('/employment/')
export const getSystemSettingsData = () => requestJson('/system-settings/')
export const getPersonalCenterData = () => requestJson('/personal-center/')
export const getChangePasswordData = () => requestJson('/change-password/')
export const getIntelligentPredictionAnalysis = (payload = {}) => jsonRequest('/intelligent-prediction/analyze/', 'POST', payload)
export const getIntelligentPredictionChat = (payload = {}) => jsonRequest('/intelligent-prediction/chat/', 'POST', payload)
export const getGlobalSearchResults = (keyword) => requestJson('/search/?q=' + encodeURIComponent(String(keyword || '').trim()))
export function getCrossModuleQueryData(filters = {}) {
  const params = new URLSearchParams()
  if (filters.grade) params.set('grade', filters.grade)
  if (filters.major) params.set('major', filters.major)
  return requestJson('/cross-module-query/?' + params.toString())
}

export async function streamIntelligentPredictionChat(payload = {}, onEvent, options = {}) {
  const { signal } = options
  const response = await apiFetch('/intelligent-prediction/chat/stream/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`Request failed with status ${response.status}${detail ? ` - ${detail}` : ''}`)
  }
  if (!response.body) {
    throw new Error('Streaming is not supported in this environment')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let finalPayload = null

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分隔事件；最后一段可能不完整，留在 buffer 里等下一块
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''

      for (const block of blocks) {
        const line = block.trim()
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw || raw === '[DONE]') continue

        let event
        try {
          event = JSON.parse(raw)
        } catch {
          continue
        }
        if (event.type === 'final') {
          finalPayload = event.payload ?? null
        }
        if (typeof onEvent === 'function') {
          onEvent(event)
        }
      }
    }
  } finally {
    reader.releaseLock?.()
  }

  if (!finalPayload) {
    throw new Error('Stream ended without a final answer')
  }
  return finalPayload
}
