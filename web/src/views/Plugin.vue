<template>
  <div class="page plugin-page">
    <div class="page-header">
      <h2>🧩 插件中心</h2>
    </div>

    <div class="page-body plugin-page-body">
      <a-spin :loading="loading" style="width: 100%">
        <div class="plugin-center">
          <a-alert v-if="!enabled" type="warning" class="pc-gap">
            插件功能未启用。请到 <b>设置 → 🧩 插件</b> 打开总开关并保存后再来管理。
          </a-alert>

          <!-- 已安装 -->
          <a-card class="pc-card" :bordered="false">
            <template #title>
              <span>已安装插件</span>
              <a-tag size="small" color="arcoblue" style="margin-left: 8px">{{ items.length }}</a-tag>
            </template>
            <template #extra>
              <a-space size="mini">
                <a-tag v-if="busy" size="small" color="orange">运行中</a-tag>
                <a-button size="mini" type="text" :loading="listLoading" @click="refresh">刷新</a-button>
              </a-space>
            </template>

            <div v-if="items.length" class="plug-list">
              <div v-for="p in items" :key="p.id" class="plug-item">
                <div class="plug-main">
                  <div class="plug-head">
                    <span class="plug-name">{{ p.name }}</span>
                    <a-tag size="small" :color="p.type === 'service' ? 'orangered' : 'green'">
                      {{ p.type === 'service' ? '服务' : '脚本' }}
                    </a-tag>
                    <a-tag size="small" color="gray">{{ p.source === 'bundled' ? '内置' : '用户' }}</a-tag>
                    <a-tag size="small" color="gray">v{{ p.version }}</a-tag>
                    <a-tag v-if="p.write_back" size="small" color="purple">结果写回任务</a-tag>
                  </div>
                  <div v-if="p.description" class="plug-desc">{{ p.description }}</div>
                  <div v-if="p.triggers?.length" class="plug-triggers">
                    <span class="plug-trig-k">自动触发：</span>
                    <a-tag v-for="(t, i) in p.triggers" :key="i" size="small" color="arcoblue">
                      {{ t }}
                    </a-tag>
                  </div>
                </div>
                <div class="plug-ops">
                  <div v-if="p.triggers?.length" class="plug-auth">
                    <a-switch
                      size="small"
                      :model-value="p.authorized === true"
                      :disabled="!enabled || authBusy === p.id"
                      @change="(v) => onAuthorize(p, v)"
                    />
                    <span class="plug-auth-text">
                      {{ p.authorized === true ? '已授权' : p.authorized === false ? '已拒绝' : '未授权' }}
                    </span>
                  </div>
                  <template v-if="p.type === 'service'">
                    <a-button size="mini" :disabled="!enabled || busy" @click="onServiceCmd(p, 'start')">▶ 启动</a-button>
                    <a-button size="mini" :disabled="!enabled || busy" @click="onServiceCmd(p, 'stop')">⏹ 停止</a-button>
                    <a-button size="mini" :disabled="!enabled" @click="onServiceCmd(p, 'status')">ℹ 状态</a-button>
                  </template>
                  <a-button
                    v-else
                    size="mini"
                    type="primary"
                    :disabled="!enabled || busy"
                    :loading="runBusy === p.id"
                    @click="onRun(p)"
                  >
                    ▶ 运行
                  </a-button>
                </div>
              </div>
            </div>
            <a-empty v-else description="暂无已加载插件，可在下方添加" />

            <div v-if="failures.length" class="plug-fail-box">
              <div class="plug-fail-title">校验失败（未加载）</div>
              <div v-for="(f, i) in failures" :key="i" class="plug-fail-item">
                <code>{{ f.path }}</code>
                <ul>
                  <li v-for="(e, j) in f.errors" :key="j">{{ e }}</li>
                </ul>
              </div>
            </div>
          </a-card>

          <!-- 添加 / 安装 -->
          <a-card class="pc-card" :bordered="false" title="添加插件">
            <a-tabs v-model:active-key="addTab" size="small">
              <a-tab-pane key="zip" title="从 zip 包安装">
                <p class="pc-hint">选择本机插件 zip 包，解压校验通过后安装到用户插件目录。</p>
                <div class="pc-add-row">
                  <a-input v-model="zipPath" placeholder="本机 zip 包路径，或点右侧按钮选择" allow-clear />
                  <a-button @click="onPickZip">选择文件</a-button>
                  <a-button type="primary" :loading="zipInstalling" :disabled="!zipPath.trim()" @click="onInstallZip">
                    安装
                  </a-button>
                </div>
              </a-tab-pane>

              <a-tab-pane key="dir" title="从目录安装">
                <p class="pc-hint">填写本机插件目录路径（含 <code>plugin.yaml</code>），先预览校验，通过后再安装。</p>
                <div class="pc-add-row">
                  <a-input
                    v-model="addPath"
                    placeholder="插件目录路径"
                    allow-clear
                    @press-enter="onPreview"
                  />
                  <a-button type="outline" :loading="previewing" @click="onPreview">预览校验</a-button>
                  <a-button type="primary" :loading="installing" :disabled="!preview?.ok" @click="onInstall">
                    安装
                  </a-button>
                </div>
                <div v-if="preview" class="pc-preview" :class="{ ok: preview.ok, bad: !preview.ok }">
                  <div class="pc-preview-head">
                    <a-tag :color="preview.ok ? 'green' : 'red'" size="small">
                      {{ preview.ok ? '校验通过' : '校验失败' }}
                    </a-tag>
                    <span class="pc-muted">{{ preview.path }}</span>
                  </div>
                  <a-descriptions v-if="preview.ok && preview.preview" :column="2" size="small" bordered>
                    <a-descriptions-item label="名称">{{ preview.preview.name }}</a-descriptions-item>
                    <a-descriptions-item label="ID">{{ preview.preview.id }}</a-descriptions-item>
                    <a-descriptions-item label="类型">{{ preview.preview.type }}</a-descriptions-item>
                    <a-descriptions-item label="版本">{{ preview.preview.version }}</a-descriptions-item>
                    <a-descriptions-item label="说明" :span="2">
                      {{ preview.preview.description || '—' }}
                    </a-descriptions-item>
                  </a-descriptions>
                  <ul v-if="preview.errors?.length" class="pc-err-list">
                    <li v-for="(e, i) in preview.errors" :key="i">{{ e }}</li>
                  </ul>
                </div>
              </a-tab-pane>
            </a-tabs>

            <a-collapse :bordered="false" class="pc-advanced">
              <a-collapse-item key="adv" header="高级">
                <p class="pc-hint">用户插件目录（安装目标）；留空 = 数据目录/plugins。更改需点保存。</p>
                <div class="pc-add-row">
                  <a-input v-model="userDir" :placeholder="userDirHint || '留空 = 数据目录/plugins'" allow-clear />
                  <a-button :loading="dirSaving" @click="onSaveUserDir">保存目录</a-button>
                </div>
              </a-collapse-item>
            </a-collapse>
          </a-card>

          <!-- 运行历史 -->
          <a-card class="pc-card" :bordered="false">
            <template #title>
              <span>运行历史</span>
              <a-tag size="small" style="margin-left: 8px">{{ runs.length }}</a-tag>
            </template>
            <template #extra>
              <a-button size="mini" type="text" :loading="runsLoading" @click="loadRuns">刷新</a-button>
            </template>
            <a-table
              v-if="runs.length"
              :data="runs"
              :columns="runColumns"
              :pagination="runs.length > 10 ? { pageSize: 10 } : false"
              size="small"
              row-key="time"
              :bordered="{ cell: true }"
              @row-click="onRunRow"
              class="pc-runs"
            >
              <template #ok="{ record }">
                <a-tag size="small" :color="record.ok ? 'green' : 'red'">
                  {{ record.ok ? '成功' : '失败' }}
                </a-tag>
              </template>
              <template #trigger="{ record }">
                {{ TRIGGER_LABEL[record.trigger] || record.trigger || '—' }}
              </template>
            </a-table>
            <a-empty v-else description="暂无运行记录" />
          </a-card>
        </div>
      </a-spin>
    </div>

    <div class="page-footer">
      <a-button @click="cancelHost">关闭</a-button>
    </div>

    <a-drawer
      v-model:visible="logVisible"
      :title="logTitle"
      width="560"
      unmount-on-close
      :footer="false"
    >
      <a-spin :loading="logLoading" style="width: 100%">
        <pre class="pc-log">{{ logContent }}<template v-if="logTruncated">
（日志超长已截断）</template></pre>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  authorizePlugin,
  cancelHost,
  getPluginRunLog,
  getSettings,
  installPluginPath,
  installPluginZip,
  listPluginRuns,
  listPlugins,
  pickPath,
  runPlugin,
  saveSettings,
  validatePluginPath,
} from '@/api/client'

const loading = ref(false)
const enabled = ref(false)
const busy = ref(false)
const items = ref([])
const failures = ref([])
const listLoading = ref(false)
const runBusy = ref('')
const authBusy = ref('')

const addTab = ref('zip')
const zipPath = ref('')
const zipInstalling = ref(false)
const addPath = ref('')
const previewing = ref(false)
const installing = ref(false)
const preview = ref(null)
const userDir = ref('')
const userDirHint = ref('')
const dirSaving = ref(false)

const runs = ref([])
const runsLoading = ref(false)
const logVisible = ref(false)
const logLoading = ref(false)
const logTitle = ref('')
const logContent = ref('')
const logTruncated = ref(false)

const TRIGGER_LABEL = {
  manual: '手动',
  daily: '每日',
  interval: '间隔',
  cron: 'cron',
  task_done: '任务完成',
  pomodoro_end: '番茄结束',
  startup: '启动时',
}

const runColumns = [
  { title: '时间', dataIndex: 'time', width: 150 },
  { title: '插件', dataIndex: 'name', width: 120 },
  { title: '触发', slotName: 'trigger', width: 90 },
  { title: '结果', slotName: 'ok', width: 72 },
  { title: '摘要', dataIndex: 'summary', ellipsis: true, tooltip: true },
]

function applyList(data) {
  enabled.value = !!data.enabled
  busy.value = !!data.busy
  items.value = data.items || []
  failures.value = data.failures || []
  if (data.user_dir) userDirHint.value = data.user_dir
}

async function refresh() {
  listLoading.value = true
  try {
    applyList(await listPlugins())
  } catch (e) {
    Message.warning(e?.response?.data?.error || e?.message || '加载插件列表失败')
  } finally {
    listLoading.value = false
  }
}

async function loadRuns() {
  runsLoading.value = true
  try {
    const data = await listPluginRuns(100)
    runs.value = data.items || []
  } catch (e) {
    runs.value = []
    Message.warning(e?.response?.data?.error || e?.message || '加载运行历史失败')
  } finally {
    runsLoading.value = false
  }
}

async function onAuthorize(p, allow) {
  authBusy.value = p.id
  try {
    await authorizePlugin(p.id, !!allow)
    p.authorized = !!allow
    Message.success(allow ? '已授权自动运行' : '已拒绝自动运行（不再询问）')
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '设置授权失败')
  } finally {
    authBusy.value = ''
  }
}

function onRun(p) {
  Modal.confirm({
    draggable: true,
    title: '运行脚本',
    content: `确定运行「${p.name}」？进度将显示在托盘顶栏，结果可在运行历史查看。`,
    okText: '运行',
    async onOk() {
      runBusy.value = p.id
      try {
        await runPlugin(p.id)
        Message.success('已开始运行，完成后可在运行历史查看')
      } catch (e) {
        Message.error(e?.response?.data?.error || e?.message || '运行失败')
      } finally {
        runBusy.value = ''
      }
    },
  })
}

async function onServiceCmd(p, action) {
  try {
    const data = await runPlugin(p.id, { action })
    Message.info(`${p.name}：${data.detail ?? action}`)
    if (action === 'status') return
    await refresh()
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '服务命令失败')
  }
}

async function onPickZip() {
  const r = await pickPath('file', { title: '选择插件 zip 包' })
  if (r.cancelled || !r.path) {
    if (!r.id) Message.info('仅桌面端支持文件选择')
    return
  }
  zipPath.value = r.path
}

async function onInstallZip() {
  const path = zipPath.value.trim()
  if (!path) return
  const doInstall = async (overwrite = false) => {
    zipInstalling.value = true
    try {
      const data = await installPluginZip(path, { overwrite })
      Message.success(data.message || '安装成功')
      if (data.plugins) applyList(data.plugins)
      else await refresh()
      zipPath.value = ''
    } catch (e) {
      onInstallConflict(e, () => doInstall(true), '安装失败')
    } finally {
      zipInstalling.value = false
    }
  }
  await doInstall(false)
}

/** 409 目标已存在 → 询问覆盖重装 */
function onInstallConflict(e, onOverwrite, fallback) {
  const status = e?.response?.status
  const err = e?.response?.data
  if (status === 409) {
    Modal.confirm({
      draggable: true,
      title: '目标已存在',
      content: err?.error || '是否覆盖安装？',
      okText: '覆盖',
      onOk,
    })
  } else {
    Message.error(err?.error || e?.message || fallback)
  }
}

async function onPreview() {
  const path = addPath.value.trim()
  if (!path) {
    Message.warning('请填写插件目录路径')
    return
  }
  previewing.value = true
  preview.value = null
  try {
    const data = await validatePluginPath(path)
    preview.value = data
    if (data.ok) Message.success('校验通过')
    else Message.error('校验未通过，见下方错误')
  } catch (e) {
    const err = e?.response?.data
    preview.value = {
      ok: false,
      errors: err?.errors || [err?.error || e?.message || '校验请求失败'],
      preview: null,
      path,
    }
  } finally {
    previewing.value = false
  }
}

async function onInstall() {
  const path = addPath.value.trim()
  if (!path || !preview.value?.ok) {
    Message.warning('请先预览校验并通过')
    return
  }
  const doInstall = async (overwrite = false) => {
    installing.value = true
    try {
      const data = await installPluginPath(path, { overwrite })
      Message.success(data.message || '安装成功')
      if (data.plugins) applyList(data.plugins)
      else await refresh()
      addPath.value = ''
      preview.value = null
    } catch (e) {
      onInstallConflict(e, () => doInstall(true), '安装失败')
    } finally {
      installing.value = false
    }
  }
  await doInstall(false)
}

async function onSaveUserDir() {
  dirSaving.value = true
  try {
    // 后端 ops 分支整体替换：先取当前值合并，避免重置总开关
    const s = await getSettings()
    const ops = s?.ops || {}
    await saveSettings({ ops: { ...ops, user_plugins_dir: userDir.value.trim() } })
    Message.success('用户插件目录已保存')
    await refresh()
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '保存失败')
  } finally {
    dirSaving.value = false
  }
}

async function onRunRow(record) {
  const file = (record.log || '').split('/').pop()
  if (!file) return
  logVisible.value = true
  logTitle.value = `${record.name || record.id} · ${record.time || ''}`
  logLoading.value = true
  logContent.value = ''
  logTruncated.value = false
  try {
    const data = await getPluginRunLog(file)
    logContent.value = data.content || ''
    logTruncated.value = !!data.truncated
  } catch (e) {
    logContent.value = e?.response?.data?.error || e?.message || '日志读取失败'
  } finally {
    logLoading.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const data = await listPlugins()
    applyList(data)
    // 添加来源路径默认值 = 内置插件目录
    if (data.bundled_dir) addPath.value = data.bundled_dir
    await loadRuns()
  } catch (e) {
    Message.warning(e?.response?.data?.error || e?.message || '加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.plugin-page {
  overflow: hidden;
}
.plugin-page-body {
  overflow: auto;
}
.plugin-center {
  max-width: 860px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-bottom: 8px;
}
.pc-gap {
  flex: none;
}
.pc-card :deep(.arco-card-body) {
  padding-top: 12px;
}
.pc-hint {
  margin: 0 0 10px;
  font-size: 12.5px;
  color: var(--color-text-3);
  line-height: 1.5;
}
.pc-muted {
  color: var(--color-text-3);
  font-size: 12px;
}
/* —— 插件条目 —— */
.plug-list {
  display: flex;
  flex-direction: column;
}
.plug-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 2px;
  border-bottom: 1px solid var(--color-border-2);
}
.plug-item:last-child {
  border-bottom: none;
}
.plug-main {
  flex: 1;
  min-width: 0;
}
.plug-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.plug-name {
  font-weight: 600;
  font-size: 14px;
}
.plug-desc {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--color-text-3);
  line-height: 1.45;
}
.plug-triggers {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.plug-trig-k {
  font-size: 12px;
  color: var(--color-text-3);
}
.plug-ops {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  flex: none;
}
.plug-auth {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-right: 8px;
}
.plug-auth-text {
  font-size: 12px;
  color: var(--color-text-3);
  white-space: nowrap;
}
/* —— 添加 / 安装 —— */
.pc-add-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.pc-add-row .arco-input-wrapper {
  flex: 1;
  min-width: 220px;
}
.pc-preview {
  margin-top: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--color-border-2);
  background: var(--color-bg-2, #fff);
}
.pc-preview.ok {
  border-color: rgb(var(--green-6, 0 180 42));
}
.pc-preview.bad {
  border-color: rgb(var(--red-6, 245 63 63));
}
.pc-preview-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.pc-err-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: rgb(var(--red-6, 245 63 63));
  font-size: 12px;
}
.pc-advanced {
  margin-top: 4px;
  border-top: 1px dashed var(--color-border-2);
}
.pc-advanced :deep(.arco-collapse-item) {
  border: none;
}
.pc-advanced :deep(.arco-collapse-item-header) {
  padding-left: 0;
}
.pc-advanced :deep(.arco-collapse-item-content-box) {
  padding-left: 0;
}
/* —— 校验失败 —— */
.plug-fail-box {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-danger-light-1, #ffece8);
  font-size: 12px;
}
.plug-fail-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--color-text-1);
}
.plug-fail-item {
  margin-bottom: 8px;
}
.plug-fail-item ul {
  margin: 4px 0 0;
  padding-left: 18px;
  color: var(--color-text-2);
}
.plug-fail-item code {
  font-size: 11px;
  word-break: break-all;
}
/* —— 运行历史 / 日志 —— */
.pc-runs :deep(.arco-table-tr) {
  cursor: pointer;
}
.pc-log {
  margin: 0;
  padding: 0;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: var(--font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
}
</style>
