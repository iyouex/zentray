// updateStore 回归断言（node web/tests/updateStore.test.mjs）——重点：代次隔离与两道确认闸。
// 假接口按剧本逐次给出服务端快照；一切都以「调用了什么、最终停在哪个状态」来断言。
import assert from 'node:assert/strict'
import { createUpdateStore } from '../src/utils/updateStore.js'

const FOUND = {
  has_update: true, asset_ready: true, version: '9.9.9', asset_size: 100,
  asset_url: 'https://github.com/iyouex/zentray/releases/download/v9.9.9/x', sha256: 'a',
  notes_url: 'https://github.com/iyouex/zentray/releases/tag/v9.9.9', body: '## 主题\n- 更新内容',
}

/** 服务端状态机快照（与 UpdaterService.status() 同构） */
const snap = (state, extra = {}) => ({
  state, progress: 0, downloaded: 0, total: 0, error: '', version: '', manual: true,
  result: null, ...extra,
})

/** 可编排的假接口：状态快照按剧本出队，元素可以是快照、Error 或返回 Promise 的函数 */
function fakeApi() {
  const calls = []
  const statuses = []
  const record = (name) => calls.push(name)
  return {
    calls,
    push(...items) { statuses.push(...items) },
    async updatesCheck() { record('check'); return { started: true } },
    async updatesDownload(body) { record(`download:${body.version}`); return { started: true } },
    async updatesCancel() { record('cancel'); return { cancelled: true, state: 'available' } },
    async updatesInstall() { record('install'); return { started: true } },
    async updatesRestart() { record('restart'); return { restarting: true } },
    async updatesDefer() { record('defer'); return { deferred: true } },
    async updatesStatus() {
      record('status')
      const next = statuses.shift()
      if (next instanceof Error) throw next
      return typeof next === 'function' ? next() : next
    },
  }
}

const errorWith = (message) => Object.assign(new Error('Request failed'), {
  response: { data: { error: message } },
})

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function until(condition, what = '条件') {
  for (let i = 0; i < 1000 && !condition(); i++) await sleep(2)
  assert.ok(condition(), `${what}未在限定时间内成立`)
}

const store = (api) => createUpdateStore(api, { pollMs: 1, maxPollFailures: 3 })
const count = (api, name) => api.calls.filter((c) => c === name).length

let passed = 0
async function test(name, fn) {
  await fn()
  passed += 1
  console.log(`ok ${passed} - ${name}`)
}

// 1) 检查：无更新 → uptodate（手动检查的结果要给用户看）
await test('check: 无更新停在 uptodate', async () => {
  const api = fakeApi()
  api.push(snap('checking'), snap('uptodate', { result: { has_update: false, version: '0.7.24' } }))
  const s = store(api)
  assert.equal(await s.check(), true)
  assert.equal(s.getState().state, 'uptodate')
  assert.equal(s.getState().manual, true)
})

// 2) 检查：发现新版 → available，带上结果
await test('check: 发现新版停在 available', async () => {
  const api = fakeApi()
  api.push(snap('available', { version: '9.9.9', result: FOUND }))
  const s = store(api)
  await s.check()
  const st = s.getState()
  assert.equal(st.state, 'available')
  assert.equal(st.result.version, '9.9.9')
  assert.equal(st.result.asset_ready, true)
})

// 3) 检查发起即失败 → error + 服务端给的原因
await test('check: 发起失败显示原因', async () => {
  const api = fakeApi()
  const s = store(api)
  api.updatesCheck = async () => { throw errorWith('检查更新失败：boom') }
  await s.check()
  assert.equal(s.getState().state, 'error')
  assert.equal(s.getState().error, '检查更新失败：boom')
})

// 4) 进行中 / 已就绪 / 待重启：重复检查不替换当前任务
for (const held of ['downloading', 'ready', 'installed']) {
  await test(`check: ${held} 时不重复发起`, async () => {
    const api = fakeApi()
    const s = store(api)
    let heldDownload = null
    let finish
    if (held === 'downloading') {
      // 让下载停在轮询里：之后放行一个失败终态，收掉这条下载（它不是本用例的被测对象）
      api.push(snap('available', { version: '9.9.9', result: FOUND }),
               snap('downloading', { progress: 10 }),
               () => new Promise((resolve) => { finish = () => resolve(snap('error', { error: 'x' })) }))
      await s.sync()
      const pending = s.downloadAndInstall()
      await until(() => typeof finish === 'function', '下载进入轮询')
      heldDownload = () => pending
    } else {
      api.push(snap(held, { version: '9.9.9', result: FOUND }))
      await s.sync()
    }
    assert.equal(await s.check(), false)
    assert.equal(count(api, 'check'), 0)
    assert.equal(s.getState().state, held)
    if (heldDownload) {
      finish()
      await heldDownload()
    }
  })
}

// 5) 下载并安装一步到位：downloading → ready 自动续安装 → installed
await test('downloadAndInstall: ready 后自动续安装到 installed', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('available', { version: '9.9.9', result: FOUND }))
  await s.sync()
  api.push(snap('downloading', { downloaded: 40, total: 100, progress: 40 }),
           snap('ready', { version: '9.9.9', progress: 100 }),
           snap('installing', { version: '9.9.9' }),
           snap('installed', { version: '9.9.9' }))
  assert.equal(await s.downloadAndInstall(), true)
  assert.equal(s.getState().state, 'installed')
  const actions = api.calls.filter((c) => c !== 'status')
  assert.deepEqual(actions, ['download:9.9.9', 'install'])
  assert.equal(count(api, 'restart'), 0) // 装完不自动重启
})

// 6) 进度单调不回退
await test('downloadAndInstall: 进度单调不回退', async () => {
  const api = fakeApi()
  const s = store(api)
  const seen = []
  s.subscribe((st) => { if (st.state === 'downloading') seen.push(st.progress) })
  api.push(snap('available', { version: '9.9.9', result: FOUND }))
  await s.sync()
  api.push(snap('downloading', { progress: 30, downloaded: 30, total: 100 }),
           snap('downloading', { progress: 99, downloaded: 99, total: 100 }),
           snap('error', { error: '更新包校验失败（SHA256 不符），已丢弃，请重试', result: FOUND }))
  assert.equal(await s.downloadAndInstall(), false)
  assert.deepEqual(seen, [0, 30, 99])
  assert.equal(count(api, 'install'), 0) // 校验失败的包不会被安装
})

// 7) 下载失败 → error，带服务端原因，不续安装
await test('downloadAndInstall: 下载失败不续安装', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('available', { version: '9.9.9', result: FOUND }))
  await s.sync()
  api.push(snap('error', { error: '下载失败：reset by peer', result: FOUND }))
  assert.equal(await s.downloadAndInstall(), false)
  assert.equal(s.getState().state, 'error')
  assert.equal(s.getState().error, '下载失败：reset by peer')
  assert.equal(count(api, 'install'), 0)
})

// 8) 安装失败 → 回到 ready 并带原因；不自动循环重试；可手动重试
await test('downloadAndInstall: 安装失败回 ready，不自动重试', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('available', { version: '9.9.9', result: FOUND }))
  await s.sync()
  api.push(snap('ready', { version: '9.9.9' }),
           snap('ready', { version: '9.9.9', error: '安装失败：已取消系统认证，可手动安装' }))
  assert.equal(await s.downloadAndInstall(), false)
  assert.equal(s.getState().state, 'ready')
  assert.match(s.getState().error, /已取消系统认证/)
  assert.equal(count(api, 'install'), 1)

  api.push(snap('installed', { version: '9.9.9' }))
  assert.equal(await s.install(), true) // 重试用的是已下载的包，不再下载
  assert.equal(count(api, 'download:9.9.9'), 1)
  assert.equal(count(api, 'install'), 2)
})

// 9) 取消：旧轮询迟到的「完成」不回写，也不会触发安装
await test('cancelDownload: 迟到的完成被忽略', async () => {
  const api = fakeApi()
  const s = store(api)
  const seen = []
  s.subscribe((st) => seen.push(st.state))
  api.push(snap('available', { version: '9.9.9', result: FOUND }))
  await s.sync()
  let release
  api.push(snap('downloading', { progress: 40 }),
           () => new Promise((resolve) => { release = () => resolve(snap('ready')) }))
  api.push(snap('available', { version: '9.9.9', result: FOUND })) // 取消后的对齐
  const pending = s.downloadAndInstall()
  await until(() => typeof release === 'function', '下载进入轮询')

  assert.equal(await s.cancelDownload(), true)
  assert.equal(s.getState().state, 'available')
  assert.equal(s.getState().progress, 0)

  release() // 旧任务的「下载完成」此刻才到
  assert.equal(await pending, false)
  await sleep(10)
  assert.equal(s.getState().state, 'available')
  assert.equal(seen.includes('ready'), false)
  assert.equal(count(api, 'install'), 0)
})

// 10) 取消：旧轮询迟到的「失败」同样被忽略
await test('cancelDownload: 迟到的失败被忽略', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('available', { version: '9.9.9', result: FOUND }))
  await s.sync()
  let reject
  api.push(snap('downloading', { progress: 40 }),
           () => new Promise((_, fail) => { reject = () => fail(new Error('socket hang up')) }))
  api.push(snap('available', { version: '9.9.9', result: FOUND })) // 取消后的对齐
  const pending = s.downloadAndInstall()
  await until(() => typeof reject === 'function', '下载进入轮询')
  await s.cancelDownload()
  reject()
  await pending
  await sleep(10)
  assert.equal(s.getState().state, 'available')
  assert.equal(s.getState().error, '')
})

// 11) 本平台安装包未就绪 → 不发起下载
await test('downloadAndInstall: 包未就绪时不发起', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('available', { version: '9.9.9', result: { ...FOUND, asset_ready: false } }))
  await s.sync()
  assert.equal(await s.downloadAndInstall(), false)
  assert.equal(s.getState().state, 'available')
  assert.equal(count(api, 'download:9.9.9'), 0)
})

// 12) 页面重载后与服务端对齐：后台仍在下载则接上轮询，但不擅自续安装
await test('sync: 接上后台仍在跑的任务，不擅自续安装', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('downloading', { progress: 60 }), snap('ready', { version: '9.9.9' }))
  await s.sync()
  assert.equal(s.getState().state, 'ready')
  assert.equal(count(api, 'install'), 0)
})

// 13) 轮询偶发失败可容忍，连续失败才报错
await test('poll: 偶发失败可容忍', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('checking'), new Error('ECONNRESET'), snap('uptodate'))
  await s.check()
  assert.equal(s.getState().state, 'uptodate')
})

await test('poll: 连续失败报错', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('checking'), new Error('x'), new Error('x'), new Error('x'))
  await s.check()
  assert.equal(s.getState().state, 'error')
  assert.equal(s.getState().error, 'x')
})

// 14) 重启与稍后只是转调；重启不会被 store 自己触发
await test('restart / defer: 只在界面确认后转调', async () => {
  const api = fakeApi()
  const s = store(api)
  await s.restart()
  await s.defer()
  assert.equal(count(api, 'restart'), 1)
  assert.equal(count(api, 'defer'), 1)
})

// 15) 订阅与退订
await test('subscribe: 退订后不再通知', async () => {
  const api = fakeApi()
  const s = store(api)
  let notified = 0
  const off = s.subscribe(() => { notified += 1 })
  api.push(snap('idle'))
  await s.sync()
  off()
  api.push(snap('idle'))
  await s.sync()
  assert.equal(notified, 1)
})

// 16) 下载失败后可直接重试，不必先重新检查
await test('downloadAndInstall: error 态可直接重试', async () => {
  const api = fakeApi()
  const s = store(api)
  api.push(snap('error', { error: '下载失败：reset by peer', result: FOUND }))
  await s.sync()
  api.push(snap('ready', { version: '9.9.9' }), snap('installed', { version: '9.9.9' }))
  assert.equal(await s.downloadAndInstall(), true)
  assert.equal(count(api, 'download:9.9.9'), 1)
  assert.equal(count(api, 'check'), 0)
})

console.log(`updateStore.test.mjs: ${passed}/${passed} PASS`)
