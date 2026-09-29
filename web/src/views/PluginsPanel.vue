<template>
  <div class="page pp-page">
    <div class="page-header pp-header">
      <h2>🧩 插件</h2>
      <a-space size="mini">
        <a-tag v-if="busy" size="small" color="orange">脚本运行中</a-tag>
        <a-button size="mini" type="text" :loading="loading || runsLoading" @click="refresh">
          刷新
        </a-button>
        <a-button size="mini" type="text" @click="cancelHost" aria-label="关闭窗口">
          <template #icon><PhX :size="16" /></template>
        </a-button>
      </a-space>
    </div>

    <div class="page-body pp-body">
      <a-alert v-if="!enabled" type="warning">
        插件功能未启用。可在 设置 → 🧩 插件 中开启并导入。
      </a-alert>

      <a-tabs v-else v-model:active-key="tab" class="pp-tabs" type="rounded" @change="onTabChange">
        <!-- Tab1 插件：分类筛选 + 卡片（点卡展开 调参/确认运行） -->
        <a-tab-pane key="plugins" title="插件">
          <a-spin :loading="loading" style="width: 100%">
            <div v-if="items.length">
              <div class="pp-filter">
                <a-space wrap size="small">
                  <a-tag
                    v-for="c in categoryChips"
                    :key="c || '_all'"
                    size="small"
                    :color="category === c ? 'arcoblue' : 'gray'"
                    :class="['pp-chip', { on: category === c }]"
                    @click="category = c"
                  >
                    {{ c || '全部分类' }}
                  </a-tag>
                </a-space>
                <a-select v-model="type" size="small" style="width: 108px">
                  <a-option value="">全部类型</a-option>
                  <a-option value="script">脚本</a-option>
                  <a-option value="service">服务</a-option>
                </a-select>
              </div>

              <div class="pp-list">
                <div
                  v-for="p in filteredItems"
                  :key="p.id"
                  class="pp-card"
                  :class="{ open: expanded === p.id }"
                >
                  <div class="pp-card-head" @click="onCardClick(p)">
                    <span class="pp-name">{{ p.name }}</span>
                    <a-tag size="small" :color="p.type === 'service' ? 'orangered' : 'green'">
                      {{ p.type === 'service' ? '服务' : '脚本' }}
                    </a-tag>
                    <a-tag v-if="p.category" size="small" color="cyan">{{ p.category }}</a-tag>
                    <span class="pp-spacer" />
                    <a-button size="mini" type="text" @click.stop="docPlugin = p">说明</a-button>
                    <a-button size="mini" type="text" @click.stop="onCardReport(p)">报告</a-button>
                    <a-button size="mini" type="text" @click.stop="onCardLog(p)">日志</a-button>
                    <span v-if="p.type !== 'service'" class="pp-hint">
                      {{ expanded === p.id ? '收起' : (p.params?.length ? '设参数运行' : '运行') }}
                    </span>
                  </div>

                  <!-- 服务：三按钮直接放卡片上 -->
                  <div v-if="p.type === 'service'" class="pp-actions">
                    <a-button size="mini" type="primary" :disabled="busy" :loading="acting === p.id" @click="serviceCmd(p, 'start')">▶ 启动</a-button>
                    <a-button size="mini" :disabled="busy" :loading="acting === p.id" @click="serviceCmd(p, 'stop')">⏹ 停止</a-button>
                    <a-button size="mini" :loading="acting === p.id" @click="serviceCmd(p, 'status')">ℹ 状态</a-button>
                  </div>

                  <!-- 脚本：同窗展开 确认卡 / 参数表单 -->
                  <div v-else-if="expanded === p.id" class="pp-expand">
                    <template v-if="p.params?.length">
                      <div v-for="prm in p.params" :key="prm.name" class="pp-param">
                        <span class="pp-param-k" :title="prm.description || prm.name">
                          {{ prm.description || prm.name }}
                        </span>
                        <a-input
                          v-model="drafts[p.id][prm.name]"
                          size="small"
                          :placeholder="`缺省 ${prm.default || '空'}`"
                          @press-enter="runScript(p)"
                        />
                      </div>
                    </template>
                    <p v-else class="pp-confirm">确定运行？进度显示在托盘顶栏，结果可在「记录」标签查看。</p>
                    <div class="pp-actions">
                      <a-button type="primary" :loading="acting === p.id" @click="runScript(p)">
                        ▶ 运行
                      </a-button>
                      <a-button size="small" @click="expanded = ''">收起</a-button>
                    </div>
                  </div>
                </div>
              </div>
              <a-empty
                v-if="!filteredItems.length"
                description="该筛选下无插件"
                style="margin-top: 16px"
              />
            </div>
            <a-empty v-else description="暂无已加载插件，可在 设置 → 🧩 插件 导入" />

            <div v-if="failures.length" class="pp-fail">
              <div class="pp-fail-title">校验失败（未加载）</div>
              <div v-for="(f, i) in failures" :key="i" class="pp-fail-item">
                <code>{{ f.path }}</code>
              </div>
            </div>
          </a-spin>
        </a-tab-pane>

        <!-- Tab2 记录：运行历史 + 执行报告抽屉 -->
        <a-tab-pane key="runs" title="记录">
          <a-spin :loading="runsLoading" style="width: 100%">
            <div class="pp-runs-bar">
              <a-select v-model="runFilterId" size="small" style="width: 180px" allow-clear placeholder="全部插件">
                <a-option v-for="p in items" :key="p.id" :value="p.id">{{ p.name }}</a-option>
              </a-select>
              <span class="pp-muted">点行查看执行报告</span>
            </div>
            <a-table
              v-if="filteredRuns.length"
              :data="filteredRuns"
              :columns="runColumns"
              :pagination="filteredRuns.length > 12 ? { pageSize: 12 } : false"
              size="small"
              :row-key="(r) => r.run_id || r.time"
              :bordered="{ cell: true }"
              class="pp-runs"
              @row-click="openReport"
            >
              <template #runId="{ record }">
                <code class="pp-runid">{{ record.run_id || record.time }}</code>
              </template>
              <template #trigger="{ record }">
                {{ TRIGGER_LABEL[record.trigger] || record.trigger || '—' }}
              </template>
              <template #ok="{ record }">
                <a-tag size="small" :color="record.ok ? 'green' : 'red'">
                  {{ record.ok ? '成功' : '失败' }}
                </a-tag>
              </template>
            </a-table>
            <a-empty v-else-if="!runsLoading" description="暂无运行记录" />
          </a-spin>
        </a-tab-pane>
      </a-tabs>
    </div>

    <!-- 执行报告：单次运行详情 -->
    <a-drawer
      v-model:visible="reportVisible"
      :title="reportTitle"
      width="420"
      unmount-on-close
      :footer="false"
    >
      <a-spin :loading="reportLoading" style="width: 100%">
        <a-descriptions v-if="report && !reportLogOnly" :column="2" size="small" bordered>
          <a-descriptions-item label="插件" :span="2">{{ report.name || report.id }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag size="small" :color="report.ok ? 'green' : 'red'">
              {{ report.ok ? '成功' : '失败' }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="触发">
            {{ TRIGGER_LABEL[report.trigger] || report.trigger || '—' }}
          </a-descriptions-item>
          <a-descriptions-item label="开始" :span="2">{{ fmt(report.started_at) }}</a-descriptions-item>
          <a-descriptions-item label="结束" :span="2">{{ fmt(report.time) }}</a-descriptions-item>
          <a-descriptions-item label="耗时">{{ duration }}</a-descriptions-item>
          <a-descriptions-item label="关联任务">
            <code v-if="report.task_id" class="pp-runid">{{ report.task_id }}</code>
            <span v-else>—</span>
          </a-descriptions-item>
        </a-descriptions>

        <div v-if="!reportLogOnly && report?.summary" class="pp-report-sec">
          <div class="pp-report-k">摘要</div>
          <p class="pp-report-text">{{ report.summary }}</p>
        </div>
        <div v-if="!reportLogOnly && report?.result_text" class="pp-report-sec">
          <div class="pp-report-k">结果正文</div>
          <p class="pp-report-text pp-result">{{ report.result_text }}</p>
        </div>
        <div class="pp-report-sec">
          <div class="pp-report-k">完整日志</div>
          <pre class="pp-log">{{ reportLog }}<template v-if="reportLogTruncated">（日志超长已截断）</template></pre>
        </div>
      </a-spin>
    </a-drawer>

    <!-- 使用说明抽屉（详情 + README） -->
    <PluginDocDrawer v-model:visible="docVisible" :plugin="docPlugin" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { PhX } from '@phosphor-icons/vue'
import PluginDocDrawer from '@/components/PluginDocDrawer.vue'
import { cancelHost, getPluginRunLog, getSettings, listPluginRuns, listPlugins, openPluginReport, runPlugin } from '@/api/client'

const loading = ref(true)
const enabled = ref(false)
const busy = ref(false)
const items = ref([])
const failures = ref([])
const expanded = ref('') // 当前展开的脚本卡 id
const acting = ref('') // 运行/服务命令进行中的插件 id
const drafts = reactive({}) // pid -> {param_name: value}
const tab = ref('plugins')

// Tab1 筛选
const category = ref('') // '' = 全部分类
const type = ref('') // '' = 全部类型

const categoryChips = computed(() => {
  const cats = [...new Set(items.value.map((p) => (p.category || '').trim()).filter(Boolean))]
  return ['', ...cats]
})

const filteredItems = computed(() =>
  items.value.filter(
    (p) =>
      (!category.value || p.category === category.value) &&
      (!type.value || p.type === type.value),
  ),
)

// 刷新 / 筛选 / 切标签 → 收起所有展开的插件卡（单 expanded 本身即手风琴）
watch([category, type], () => {
  expanded.value = ''
})

// Tab2 记录
const runsLoaded = ref(false)
const runsLoading = ref(false)
const runs = ref([])
const runFilterId = ref('')
const reportVisible = ref(false)
const reportLoading = ref(false)
const report = ref(null)
const reportTitle = ref('')
const reportLog = ref('')
const reportLogTruncated = ref(false)
const reportLogOnly = ref(false) // 卡片「日志」按钮：只看完整日志

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
  { title: '运行ID', slotName: 'runId', width: 150 },
  { title: '插件', dataIndex: 'name', width: 110 },
  { title: '触发', slotName: 'trigger', width: 82 },
  { title: '开始', dataIndex: 'started_at', width: 138 },
  { title: '结果', slotName: 'ok', width: 68 },
  { title: '摘要', dataIndex: 'summary', ellipsis: true, tooltip: true },
]

const filteredRuns = computed(() =>
  runs.value.filter((r) => !runFilterId.value || r.id === runFilterId.value),
)

const duration = computed(() => {
  const r = report.value
  if (!r?.started_at || !r?.time) return '—'
  const ms = new Date(r.time) - new Date(r.started_at)
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s} 秒` : `${Math.floor(s / 60)} 分 ${s % 60} 秒`
})

function fmt(iso) {
  return (iso || '').replace('T', ' ') || '—'
}

function applyList(data) {
  enabled.value = !!data.enabled
  busy.value = !!data.busy
  items.value = data.items || []
  failures.value = data.failures || []
  // 预填基线：参数预设 → manifest default
  for (const p of items.value) {
    drafts[p.id] = {}
    for (const prm of p.params || []) {
      drafts[p.id][prm.name] = prm.default ?? ''
    }
  }
}

async function refresh() {
  expanded.value = ''
  if (tab.value === 'runs') {
    await Promise.all([loadPlugins(), loadRuns()])
  } else {
    await loadPlugins()
  }
}

async function loadPlugins() {
  loading.value = true
  try {
    applyList(await listPlugins())
    if (enabled.value) {
      const s = await getSettings()
      const presets = s?.ops?.param_presets || {}
      for (const p of items.value) {
        const saved = presets[p.id] || {}
        for (const prm of p.params || []) {
          if (saved[prm.name] != null) drafts[p.id][prm.name] = saved[prm.name]
        }
      }
    }
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '加载插件列表失败')
  } finally {
    loading.value = false
  }
}

async function loadRuns() {
  runsLoading.value = true
  try {
    const data = await listPluginRuns(100)
    runs.value = data.items || []
    runsLoaded.value = true
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '加载运行记录失败')
  } finally {
    runsLoading.value = false
  }
}

function onTabChange(key) {
  expanded.value = ''
  if (key === 'runs' && !runsLoaded.value) loadRuns()
}

async function onCardClick(p) {
  if (p.type === 'service') return
  expanded.value = expanded.value === p.id ? '' : p.id
}

async function runScript(p) {
  acting.value = p.id
  try {
    const body = p.params?.length ? { params: { ...(drafts[p.id] || {}) } } : {}
    await runPlugin(p.id, body)
    Message.success('已开始运行，完成后可在「记录」标签查看执行报告')
    expanded.value = ''
    const d = await listPlugins()
    busy.value = !!d.busy
    runsLoaded.value = false // 下次进记录标签重拉
    if (tab.value === 'runs') loadRuns()
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '运行失败')
  } finally {
    acting.value = ''
  }
}

async function serviceCmd(p, action) {
  acting.value = p.id
  try {
    const data = await runPlugin(p.id, { action })
    Message.info(`${p.name}：${data.detail ?? action}`)
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '服务命令失败')
  } finally {
    acting.value = ''
  }
}

/** 卡片「报告/日志」→ 该插件最近一次运行；无记录时提示 */
async function latestRunOf(pid) {
  if (!runsLoaded.value) await loadRuns()
  return runs.value.find((r) => r.id === pid) || null
}

/** 卡片「报告」→ 生成 md 报告并用系统默认应用打开 */
async function onCardReport(p) {
  const r = await latestRunOf(p.id)
  if (!r) {
    Message.info(`「${p.name}」暂无运行记录`)
    return
  }
  try {
    await openPluginReport(r.run_id)
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '打开报告失败')
  }
}

async function onCardLog(p) {
  const r = await latestRunOf(p.id)
  if (!r) {
    Message.info(`「${p.name}」暂无运行记录`)
    return
  }
  openReport(r, true)
}

/** 打开执行报告抽屉（详情 + result_text + 完整日志；logOnly 只看日志） */
async function openReport(record, logOnly = false) {
  report.value = record
  reportLogOnly.value = logOnly
  reportTitle.value = logOnly
    ? `${record.name || record.id} · 日志`
    : `${record.name || record.id} · ${record.run_id || ''}`
  reportVisible.value = true
  reportLoading.value = true
  reportLog.value = ''
  reportLogTruncated.value = false
  const file = (record.log || '').split('/').pop()
  if (!file) {
    reportLog.value = '（无日志文件）'
    reportLoading.value = false
    return
  }
  try {
    const data = await getPluginRunLog(file)
    reportLog.value = data.content || '（空日志）'
    reportLogTruncated.value = !!data.truncated
  } catch (e) {
    reportLog.value = e?.response?.data?.error || e?.message || '日志读取失败'
  } finally {
    reportLoading.value = false
  }
}

onMounted(loadPlugins)

// 卡片「说明」→ 使用说明抽屉
const docVisible = ref(false)
const docPlugin = ref(null)
watch(docPlugin, (v) => { if (v) docVisible.value = true })
</script>

<style scoped>
.pp-page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.pp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pp-header h2 {
  margin: 0;
}
.pp-body {
  padding-top: 0;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
/* 纵向滚动：页头/标签导航固定，列表在内容区内部滚 */
.pp-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.pp-tabs :deep(.arco-tabs-content) {
  flex: 1;
  min-height: 0;
  padding-top: 8px;
  overflow-y: auto;
}
/* —— Tab1 筛选条 —— */
.pp-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.pp-chip {
  cursor: pointer;
}
.pp-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pp-card {
  padding: 12px 14px;
  border: 1px solid var(--color-border-2);
  border-radius: var(--zt-radius-card, 12px);
  background: var(--color-fill-1, rgba(148, 163, 184, 0.06));
  transition: border-color 0.2s ease;
}
.pp-card.open {
  border-color: var(--color-primary);
  background: var(--color-primary-glow, var(--color-fill-1));
}
.pp-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-wrap: wrap;
}
.pp-name {
  font-weight: 600;
  font-size: 14px;
}
.pp-spacer {
  flex: 1;
}
.pp-hint {
  font-size: 12px;
  color: var(--color-text-3);
}
.pp-expand {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border-2);
}
.pp-param {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.pp-param-k {
  min-width: 96px;
  font-size: 12.5px;
  color: var(--color-text-2);
}
.pp-param .arco-input-wrapper {
  flex: 1;
}
.pp-confirm {
  margin: 0 0 8px;
  font-size: 12.5px;
  color: var(--color-text-2);
  line-height: 1.5;
}
.pp-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.pp-fail {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-danger-light-1, #ffece8);
  font-size: 12px;
}
.pp-fail-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.pp-fail-item code {
  font-size: 11px;
  word-break: break-all;
}
/* —— Tab2 记录 —— */
.pp-runs-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.pp-muted {
  font-size: 12px;
  color: var(--color-text-3);
}
.pp-runs :deep(.arco-table-tr) {
  cursor: pointer;
}
.pp-runid {
  font-size: 11px;
  word-break: break-all;
}
/* —— 执行报告抽屉 —— */
.pp-report-sec {
  margin-top: 14px;
}
.pp-report-k {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-text-2);
  margin-bottom: 6px;
}
.pp-report-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}
.pp-result {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-fill-1, rgba(148, 163, 184, 0.08));
}
.pp-log {
  margin: 0;
  padding: 0;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: var(--font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
}
</style>
