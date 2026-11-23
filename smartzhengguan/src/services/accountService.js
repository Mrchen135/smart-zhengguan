import { requestJson, jsonRequest, saveSession } from './apiClient'

export async function login(username, password) {
  const tokens = await jsonRequest('/auth/token/', 'POST', { username, password }, { auth: false })
  saveSession(tokens)
  return requestJson('/auth/me/')
}
export const getCurrentUser = () => requestJson('/auth/me/')
export const saveProfile = (profile) => jsonRequest('/personal-center/', 'PATCH', profile)
export const changePassword = (form) => jsonRequest('/change-password/', 'POST', form)
export const saveSystemSettings = (values) => jsonRequest('/system-settings/', 'PATCH', values)
export const getNotifications = () => requestJson('/notifications/')
export const markNotificationsRead = (ids) => jsonRequest('/notifications/', 'POST', { ids })
export const getSearchHistory = () => requestJson('/search-history/')
export const saveSearchHistory = (keyword) => jsonRequest('/search-history/', 'POST', { keyword })
export const clearSearchHistory = () => requestJson('/search-history/', { method: 'DELETE' })
export const saveAcademicRecord = (record) => jsonRequest(`/academic-status/records/${encodeURIComponent(record.id)}/`, 'PATCH', record)

export async function readNotice(notice) {
  if (!Number.isInteger(notice?.id)) return
  await markNotificationsRead([notice.id])
  notice.read = true
  window.dispatchEvent(new Event('notifications-updated'))
}
