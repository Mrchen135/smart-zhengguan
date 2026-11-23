import axios from 'axios'
import { getAccessToken, refreshAccessToken, expireSession } from './apiClient'

const client = axios.create()
client.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
client.interceptors.response.use((response) => response, async (error) => {
  const config = error.config
  if (error.response?.status === 401 && !config?._retried) {
    try {
      await refreshAccessToken()
      return client({ ...config, _retried: true })
    } catch { expireSession() }
  }
  const data = error.response?.data
  error.message = data?.error || data?.detail || (error.response ? `请求失败（${error.response.status}）` : '无法连接后端服务，请重试')
  return Promise.reject(error)
})
export default client
