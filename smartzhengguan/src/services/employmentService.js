import { requestJson, jsonRequest } from './apiClient'
import { employmentQuery } from '../utils/employmentHub'

const base = '/employment-hub/'
export const getOpportunities = (filters) => requestJson(`${base}${employmentQuery(filters)}`)
export const getEmploymentMeta = () => requestJson(`${base}meta/`)
export const getEmploymentSources = () => requestJson(`${base}sources/`)
export const getEmploymentSync = () => requestJson(`${base}sync/`)
export const syncEmploymentSources = (sourceId) => jsonRequest(`${base}sync/`, 'POST', sourceId ? { sourceId } : {})
export const getOpportunity = (id) => requestJson(`${base}${encodeURIComponent(id)}/`)
export const createOpportunity = (data) => jsonRequest(base, 'POST', data)
export const updateOpportunity = (id, data) => jsonRequest(`${base}${encodeURIComponent(id)}/`, 'PATCH', data)
export const saveOpportunity = (id, saved) => jsonRequest(`${base}${encodeURIComponent(id)}/save/`, 'POST', { saved })
export const featureOpportunity = (id, featured) => jsonRequest(`${base}${encodeURIComponent(id)}/feature/`, 'POST', { featured })
export const getEmploymentDigest = (ids) => jsonRequest(`${base}digest/`, 'POST', { ids })
export const getEmploymentCalendar = (filters) => requestJson(`${base}calendar/${employmentQuery(filters)}`)
