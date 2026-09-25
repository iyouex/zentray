import axios from 'axios'

/** 从 hash query 或 location 解析 API 基址（WebEngine 宿主会注入） */
export function resolveApiBase() {
  try {
    const hash = window.location.hash || ''
    const qi = hash.indexOf('?')
    if (qi >= 0) {
      const qs = new URLSearchParams(hash.slice(qi + 1))
      const api = qs.get('api')
      if (api) return api.replace(/\/$/, '')
    }
  } catch (_) {}
  // 开发代理
  return ''
}

const http = axios.create({
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const base = resolveApiBase()
  if (base && !config.url?.startsWith('http')) {
    config.baseURL = base
  }
  return config
})

export async function getMeta() {
  const { data } = await http.get('/api/meta')
  return data
}

export async function listTasks() {
  const { data } = await http.get('/api/tasks')
  return data.items || []
}

export async function getTask(id) {
  const { data } = await http.get(`/api/tasks/${id}`)
  return data.item
}

export async function createTask(payload) {
  const { data } = await http.post('/api/tasks', payload)
  return data.item
}

export async function updateTask(id, payload) {
  const { data } = await http.put(`/api/tasks/${id}`, payload)
  return data.item
}

/** 追加子任务 */
export async function addSubtask(id, title) {
  const { data } = await http.post(`/api/tasks/${id}/subtasks`, { title })
  return data.item
}

/** 子任务置 done/abandoned；返回 { item, auto_completed } */
export async function setSubtaskStatus(id, sid, action) {
  const { data } = await http.post(`/api/tasks/${id}/subtasks/${sid}/${action}`)
  return data
}

/** 提醒卡片动作：done / snooze / dismiss */
export async function reminderAction(id, body) {
  const { data } = await http.post(`/api/tasks/${id}/reminder-action`, body)
  return data.item
}

export async function markDone(id) {
  await http.post(`/api/tasks/${id}/done`)
}

export async function abandonTask(id) {
  await http.post(`/api/tasks/${id}/abandon`)
}

export async function selectTask(id) {
  await http.post(`/api/tasks/${id}/select`)
}

export async function listTemplates() {
  const { data } = await http.get('/api/templates')
  return data.items || []
}

/** 历史任务：归档的已完成/废弃任务（时间倒序） */
export async function listArchivedTasks({ status = 'all', category = '', days = 90 } = {}) {
  const { data } = await http.get('/api/tasks/archived', { params: { status, category, days } })
  return data.items || []
}

export async function getTemplate(id) {
  const { data } = await http.get(`/api/templates/${id}`)
  return data.item
}

export async function createTemplate(payload) {
  const { data } = await http.post('/api/templates', payload)
  return data.item
}

export async function updateTemplate(id, payload) {
  const { data } = await http.put(`/api/templates/${id}`, payload)
  return data.item
}

export async function deleteTemplate(id) {
  await http.delete(`/api/templates/${id}`)
}

/** 周期模板：跳过接下来 count 次派发 */
export async function skipTemplate(id, count = 1) {
  const { data } = await http.post(`/api/templates/${id}/skip`, { count })
  return data.item
}

export async function getSettings() {
  const { data } = await http.get('/api/settings')
  return data.settings
}

/**
 * 检查弹窗提醒时间冲突（任务/周期模板/每日计划/复盘）
 * body: { reminder, exclude_task_id?, exclude_template_id? }
 */
export async function checkReminderConflicts(body) {
  const { data } = await http.post('/api/reminders/check-conflicts', body)
  return data
}

export async function saveSettings(settings) {
  const { data } = await http.put('/api/settings', { settings })
  return data.settings
}

/** 系统页：自启状态 + 导出选项 */
export async function getSystemStatus() {
  const { data } = await http.get('/api/system/status')
  return data
}

/** 即时开关开机自启 */
export async function setAutostart(enabled) {
  const { data } = await http.post('/api/system/autostart', { enabled: !!enabled })
  return data
}

/** 导出备份 zip；opts.password AES-256 加密、opts.destPath 另存为绝对路径 */
export async function exportBackup(include, { password, destPath } = {}) {
  const body = { include }
  if (password) body.password = password
  if (destPath) body.dest_path = destPath
  const { data } = await http.post('/api/system/export', body)
  return data
}

/** 从本机 zip 路径导入（替换）；加密包需带 password */
export async function importBackup(path, { include, safety_backup = true, password } = {}) {
  const body = { path, safety_backup }
  if (include) body.include = include
  if (password) body.password = password
  const { data } = await http.post('/api/system/import', body)
  return data
}

/** 仅打包 archive/ */
export async function packArchive() {
  const { data } = await http.post('/api/system/archive/pack')
  return data
}

/** 备份目录快照列表 */
export async function listBackups() {
  const { data } = await http.get('/api/system/backups')
  return data
}

/** 删除备份目录内的 zip */
export async function deleteBackup(path) {
  const { data } = await http.post('/api/system/backups/delete', { path })
  return data
}

/**
 * 原生路径选择（Qt WebEngine 桥）。kind: 'dir' | 'file' | 'save'。
 * 返回 { kind, id, path, cancelled }；纯浏览器 dev（无注入 api 基址）直接取消。
 */
export function pickPath(kind, { title = '', startDir = '', defaultName = '' } = {}) {
  if (!resolveApiBase()) {
    return Promise.resolve({ kind, id: '', path: '', cancelled: true })
  }
  const id = Math.random().toString(36).slice(2)
  return new Promise((resolve) => {
    const handler = (e) => {
      const r = e.detail || {}
      if (r.id !== id) return
      window.removeEventListener('zentray:pick-result', handler)
      resolve(r)
    }
    window.addEventListener('zentray:pick-result', handler)
    const payload = encodeURIComponent(
      JSON.stringify({ id, title, start_dir: startDir, default_name: defaultName })
    )
    window.location.href = `zentray://pick-${kind}?payload=${payload}`
  })
}

/** 首次配置向导完成 */
export async function completeSetup(form = {}) {
  const { data } = await http.post('/api/setup/complete', form)
  return data
}

/** 任务表单：在已有一级下添加二级分类 */
export async function addSecondaryCategory(primaryId, name) {
  const { data } = await http.post('/api/categories/secondary', {
    primary_id: primaryId,
    name,
  })
  return data
}

/** 历史记录：操作日志 + AI 报告列表 */
export async function fetchHistory({ days = 30, category = 'all' } = {}) {
  const { data } = await http.get('/api/history', {
    params: { days, category },
  })
  return data
}

export async function fetchAiReport(name) {
  const { data } = await http.get(`/api/history/ai/${encodeURIComponent(name)}`)
  return data
}

// ---- AI 场景能力（docs/AI-FEATURES.md）——模型可能较慢，单独放宽超时 ----

/** 文本 → 任务草稿 */
export async function aiParse(text) {
  const { data } = await http.post('/api/ai/parse', { text }, { timeout: 70000 })
  return data.draft
}

/** 图片 dataURL → 多条任务草稿 */
export async function aiOcr(image) {
  const { data } = await http.post('/api/ai/ocr', { image }, { timeout: 90000 })
  return data.drafts || []
}

/** 任务建议；focusId 可选（当前选中任务优先围绕） */
export async function aiSuggest(focusId = '') {
  const body = focusId ? { focus_id: focusId } : {}
  const { data } = await http.post('/api/ai/suggest', body, { timeout: 70000 })
  return data.suggestions || []
}

/** 关闭宿主窗口并回传结果（Qt WebEngine） */
export function closeHost(payload = {}) {
  const json = encodeURIComponent(JSON.stringify(payload || {}))
  window.location.href = `zentray://close?payload=${json}`
}

export function cancelHost() {
  closeHost({ cancelled: true })
}
