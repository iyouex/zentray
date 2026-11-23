/**
 * 应用内更新的前端镜像：状态真相在服务端（zentray/services/updater.py 的状态机），
 * 这里只负责发起、轮询与过期结果隔离。
 *
 * 逻辑对齐 taomni 的 updateStore：
 * - 代次守卫：取消、重查之后，旧任务的进度/完成/失败一律不回写；
 * - 检查/下载/安装进行中，或包已就绪、已安装待重启时，重复发起不替换当前任务；
 * - 「下载并安装」一步到位：下载到 ready 自动续安装；装完不自动重启，由界面再确认。
 *
 * 不依赖 Vue：状态是一个普通对象，变化时通知订阅者（组件里包一层 ref 即可），
 * 也便于在 node 里直接测（web/tests/updateStore.test.mjs）。
 */

const BUSY = ['checking', 'downloading', 'installing']
const HOLD = [...BUSY, 'ready', 'installed']

export function createUpdateStore(api, { pollMs = 500, maxPollFailures = 10 } = {}) {
  const state = {
    state: 'idle', progress: 0, downloaded: 0, total: 0, error: '',
    version: '', manual: false, result: null,
  }
  const listeners = new Set()
  const polling = new Set() // 正在轮询的代次
  let generation = 0

  const snapshot = () => ({ ...state, result: state.result ? { ...state.result } : null })
  const emit = () => listeners.forEach((fn) => fn(snapshot()))
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  function apply(server) {
    Object.assign(state, {
      state: server.state || 'idle',
      progress: server.progress || 0,
      downloaded: server.downloaded || 0,
      total: server.total || 0,
      error: server.error || '',
      version: server.version || '',
      manual: !!server.manual,
      result: server.result ? { ...server.result } : null,
    })
    emit()
  }

  function fail(gen, err, fallback) {
    if (gen !== generation) return
    state.state = 'error'
    state.error = err?.response?.data?.error || err?.message || fallback
    emit()
  }

  /** 轮询到服务端离开 checking/downloading/installing；期间被新一轮取代则返回 null */
  async function pollUntilSettled(gen) {
    polling.add(gen)
    let failures = 0
    try {
      for (;;) {
        await sleep(pollMs)
        if (gen !== generation) return null
        let server
        try {
          server = await api.updatesStatus()
          if (typeof server?.state !== 'string') throw new Error('更新状态响应异常')
        } catch (err) {
          if (++failures >= maxPollFailures) {
            fail(gen, err, '无法获取更新进度')
            return null
          }
          continue
        }
        if (gen !== generation) return null // 请求在途时已被取消或重查
        failures = 0
        apply(server)
        if (!BUSY.includes(server.state)) return server
      }
    } finally {
      polling.delete(gen)
    }
  }

  /** 手动检查；进行中/已就绪/待重启时不重复发起 */
  async function check() {
    if (HOLD.includes(state.state)) return false
    const gen = ++generation
    state.state = 'checking'
    state.error = ''
    emit()
    try {
      await api.updatesCheck()
    } catch (err) {
      fail(gen, err, '检查失败')
      return false
    }
    await pollUntilSettled(gen)
    return true
  }

  async function installStep(gen) {
    state.state = 'installing'
    state.error = ''
    emit()
    try {
      await api.updatesInstall()
    } catch (err) {
      fail(gen, err, '安装启动失败')
      return
    }
    await pollUntilSettled(gen)
  }

  /** 「下载并安装」：下载到 ready 自动续安装；返回是否已装到待重启 */
  async function downloadAndInstall() {
    const result = state.result
    // error 态也可重试：一次网络/校验失败不该逼用户先重新检查
    const startable = state.state === 'available' || state.state === 'error'
    if (!startable || !result?.has_update || !result?.asset_ready) return false
    const gen = ++generation
    state.state = 'downloading'
    state.error = ''
    state.downloaded = 0
    state.progress = 0
    state.total = result.asset_size || 0
    emit()
    try {
      await api.updatesDownload({ version: result.version })
    } catch (err) {
      fail(gen, err, '下载启动失败')
      return false
    }
    const settled = await pollUntilSettled(gen)
    if (!settled || gen !== generation) return false
    if (settled.state === 'ready') await installStep(gen)
    return state.state === 'installed'
  }

  /** 包已就绪时的（重试）安装 */
  async function install() {
    if (state.state !== 'ready') return false
    await installStep(++generation)
    return state.state === 'installed'
  }

  /** 取消下载：立即作废当前代次，再以服务端状态为准对齐 */
  async function cancelDownload() {
    if (state.state !== 'downloading') return false
    ++generation
    try {
      await api.updatesCancel()
    } catch (_) {
      /* 以随后 sync 到的服务端状态为准 */
    }
    await sync()
    return true
  }

  /** 与服务端对齐一次；页面重载后若服务端仍有任务在跑，则接上轮询 */
  async function sync() {
    let server
    try {
      server = await api.updatesStatus()
      if (typeof server?.state !== 'string') throw new Error('更新状态响应异常')
    } catch (err) {
      fail(generation, err, '无法获取更新状态')
      return
    }
    apply(server)
    if (BUSY.includes(server.state) && !polling.has(generation)) {
      await pollUntilSettled(generation)
    }
  }

  async function restart() {
    await api.updatesRestart()
  }

  async function defer() {
    await api.updatesDefer()
  }

  return {
    getState: snapshot,
    subscribe(fn) {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    check,
    downloadAndInstall,
    install,
    cancelDownload,
    sync,
    restart,
    defer,
  }
}

export const BUSY_STATES = BUSY
export const HOLD_STATES = HOLD
