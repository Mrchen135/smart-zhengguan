import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = await readFile(new URL('../src/services/apiClient.js', import.meta.url), 'utf8')
let sequence = 0
async function setup() {
  const items = new Map()
  globalThis.localStorage = { getItem: (key) => items.get(key) ?? null, setItem: (key, value) => items.set(key, value), removeItem: (key) => items.delete(key) }
  globalThis.window = { location: { hash: '#/home' } }
  const client = await import('data:text/javascript;base64,' + Buffer.from(source + `\n// test ${sequence++}`).toString('base64'))
  return { client, items }
}

test('failed API requests expose the error and never return demonstration data', async () => {
  const { client } = await setup()
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: '数据库暂不可用' }), { status: 503 })
  await assert.rejects(client.requestJson('/home/'), /数据库暂不可用/)
  globalThis.fetch = async () => { throw new TypeError('offline') }
  await assert.rejects(client.requestJson('/home/'), /无法连接后端/)
})

test('zero business values and empty arrays are returned unchanged', async () => {
  const { client } = await setup()
  const data = { mode: 'empty', comparisonRows: [], totalStudents: 0 }
  globalThis.fetch = async () => Response.json(data)
  assert.deepEqual(await client.requestJson('/cross-module-query/'), data)
})

test('mock sessions are rejected and real JWTs are sent with writes', async () => {
  const { client, items } = await setup()
  items.set('token', 'mock-token-123')
  assert.equal(client.getAccessToken(), '')
  client.saveSession({ access: 'real-access', refresh: 'real-refresh' })
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/v1/personal-center/')
    assert.equal(init.headers.Authorization, 'Bearer real-access')
    assert.equal(init.method, 'PATCH')
    assert.deepEqual(JSON.parse(init.body), { name: '数据库账号' })
    return Response.json({ saved: true })
  }
  assert.deepEqual(await client.jsonRequest('/personal-center/', 'PATCH', { name: '数据库账号' }), { saved: true })
})

test('expired access tokens are refreshed once for concurrent requests', async () => {
  const { client, items } = await setup()
  client.saveSession({ access: 'expired', refresh: 'refresh' })
  let refreshes = 0
  globalThis.fetch = async (url, init) => {
    if (url.endsWith('/auth/token/refresh/')) {
      refreshes++
      await new Promise(resolve => setTimeout(resolve, 15))
      return Response.json({ access: 'renewed' })
    }
    return init.headers.Authorization === 'Bearer renewed' ? Response.json({ ok: true }) : new Response('{}', { status: 401 })
  }
  await Promise.all([client.requestJson('/personal-center/'), client.requestJson('/notifications/')])
  assert.equal(refreshes, 1)
  assert.equal(items.get('token'), 'renewed')
})

test('invalid sessions are cleared and sent back to login', async () => {
  const { client, items } = await setup()
  client.saveSession({ access: 'invalid', refresh: 'invalid' })
  globalThis.fetch = async () => new Response('{}', { status: 401 })
  await assert.rejects(client.requestJson('/system-settings/'), /重新登录/)
  assert.equal(items.has('token'), false)
  assert.equal(items.has('refresh-token'), false)
  assert.match(window.location.hash, /^\/login\?redirect=/)
})

test('live page service has no mock import or cross-module metric substitution', async () => {
  const service = await readFile(new URL('../src/services/dataService.js', import.meta.url), 'utf8')
  assert.doesNotMatch(service, /graduateManagementMock|buildCrossModuleQueryFallback|enhanceCrossModule|allowFallback/)
})
