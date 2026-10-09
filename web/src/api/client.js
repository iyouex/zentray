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

/** 以任务为对象开始番茄钟专注（无 task_id 则等同托盘菜单启动） */
export async function startPomodoro(taskId = '') {
  return http.post('/api/pomodoro/start', { task_id: taskId })
}

// ---- Windows 托盘速览面板（/glance）----

/** 速览复合状态：轮播槽任务 + 活跃序 + 番茄态 + 待看报告 + 脚本占用 */
export async function getGlance() {
  const { data } = await http.get('/api/glance')
  return data
}

/** 番茄控制：stop / extend / skip_break */
export async function pomodoroControl(action) {
  const { data } = await http.post('/api/pomodoro/control', { action })
  return data
}

/** 速览报告 chip：点开即消（run:/ai: key） */
export async function glanceReportOpen(key) {
  const { data } = await http.post('/api/glance/report-open', { key })
  return data
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
/** 任务导出 .ics 并用系统日历应用打开 */
export async function exportTasksCalendar() {
  const { data } = await http.post('/api/system/calendar-export', {})
  return data
}

export async function setAutostart(enabled) {
  const { data } = await http.post('/api/system/autostart', { enabled: !!enabled })
  return data
}

/** Windows：打开系统任务栏设置页（合并模式引导） */
export async function openTaskbarSettings() {
  const { data } = await http.post('/api/system/open-taskbar-settings', {})
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

/** 导入预览（只读）：包内各类/子类计数，供选择性恢复渲染勾选树 */
export async function importPreview(path, { password } = {}) {
  const body = { path }
  if (password) body.password = password
  const { data } = await http.post('/api/system/import-preview', body)
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

// ---- 插件 ----

/** 插件列表（含 failures；设置页可扫描） */
export async function listPlugins() {
  const { data } = await http.get('/api/plugins')
  return data
}

/** 预览校验插件目录（不安装） */
export async function validatePluginPath(path) {
  const { data } = await http.post('/api/plugins/validate', { path })
  return data
}

/** 校验通过后安装到用户插件目录 */
export async function installPluginPath(path, { overwrite = false } = {}) {
  const { data } = await http.post('/api/plugins/install', { path, overwrite })
  return data
}

/** 运行插件：script 可带 { task_id }；service 传 { action: 'start'|'stop'|'status' } */
export async function runPlugin(id, body = {}) {
  const { data } = await http.post(`/api/plugins/${id}/run`, body)
  return data
}

/** 运行历史（时间倒序，limit 上限 200） */
export async function listPluginRuns(limit = 50) {
  const { data } = await http.get('/api/plugins/runs', { params: { limit } })
  return data
}

/** 单次运行日志内容（file 为日志文件名） */
export async function getPluginRunLog(file) {
  const { data } = await http.get('/api/plugins/runs/log', { params: { file } })
  return data
}

/** 生成运行报告 md 并用系统默认应用打开 */
export async function openPluginReport(runId) {
  const { data } = await http.post('/api/plugins/runs/open', { run_id: runId })
  return data
}

/** 设置插件自动运行授权（插件级一次性授权的开关） */
export async function authorizePlugin(id, allow) {
  const { data } = await http.post(`/api/plugins/${id}/authorize`, { allow })
  return data
}

/** 本地 zip 包安装（解压校验后落用户插件目录） */
export async function installPluginZip(path, { overwrite = false } = {}) {
  const { data } = await http.post('/api/plugins/install-zip', { path, overwrite })
  return data
}

/** zip 包预览校验（解压临时目录校验后清理，不安装） */
export async function previewPluginZip(path) {
  const { data } = await http.post('/api/plugins/preview-zip', { path })
  return data
}

/** 编辑插件名称/描述（就地改写 plugin.yaml，仅用户目录插件） */
export async function updatePlugin(id, { name, description }) {
  const { data } = await http.put(`/api/plugins/${id}`, { name, description })
  return data
}

/** 删除用户目录插件（含目录与调度/预设覆盖） */
export async function deletePlugin(id) {
  const { data } = await http.delete(`/api/plugins/${id}`)
  return data
}
