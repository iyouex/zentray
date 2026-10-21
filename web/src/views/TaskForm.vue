<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ isEdit ? '修改任务' : '新建任务' }}</h2>
      <a-space v-if="aiParseOn">
        <a-button type="outline" :loading="aiParsing" @click="onAiParse">
          <template #icon><PhSparkle :size="16" /></template>
          AI 解析
        </a-button>
      </a-space>
    </div>
    <input v-if="aiOcrOn" ref="fileRef" type="file" accept="image/*" style="display: none" @change="onFile" />

    <div class="page-body tf-body">
      <a-spin :loading="loading" style="width: 100%; height: 100%">
        <div class="tf-grid">
          <!-- ============ 基本信息（行式范式） ============ -->
          <section class="zt-block">
            <div class="zt-block-head"><h3 class="zt-h3">基本信息</h3></div>
            <div class="field-table tf-fields">
              <div v-if="!isEdit || isTemplate" class="field-line">
                <span class="field-k">任务模式</span>
                <div class="tf-ctl">
                  <a-radio-group v-model="form.mode" :disabled="isTemplate" size="small">
                    <a-radio value="one-time" :disabled="isTemplate">一次性</a-radio>
                    <a-radio value="periodic">周期</a-radio>
                  </a-radio-group>
                  <a-select
                    v-if="form.mode === 'periodic'"
                    v-model="form.periodicity"
                    size="small"
                    style="width: 96px"
                    :options="periodOpts"
                  />
                </div>
              </div>

              <div class="field-line">
                <span class="field-k">标题</span>
                <a-input
                  v-model="form.title"
                  size="small"
                  :max-length="100"
                  show-word-limit
                  placeholder="用一句话描述待办"
                />
              </div>

              <div class="tf-pair">
                <div class="field-line">
                  <span class="field-k">一级分类</span>
                  <a-select
                    v-model="form.category_primary_id"
                    size="small"
                    :options="primaryOpts"
                    :fallback-option="false"
                    placeholder="仅可选已有"
                    allow-search
                    @change="onPrimaryChange"
                  />
                </div>
                <div class="field-line">
                  <span class="field-k">二级分类</span>
                  <div class="tf-ctl">
                    <a-select
                      v-if="secondaryEnabled"
                      v-model="form.category_secondary_id"
                      size="small"
                      allow-clear
                      allow-search
                      :options="secondaryOpts"
                      :fallback-option="false"
                      placeholder="可选"
                      style="flex: 1"
                    />
                    <span v-else class="hint">未启用</span>
                    <a-button
                      v-if="secondaryEnabled"
                      size="mini"
                      :disabled="!form.category_primary_id"
                      title="添加二级分类"
                      @click="showAddSec = true"
                    >➕</a-button>
                  </div>
                </div>
              </div>

              <div class="tf-pair">
                <div class="field-line">
                  <span class="field-k">优先级</span>
                  <a-select v-model="form.priority" size="small" :options="priorityOpts" />
                </div>
                <div v-if="isPeriodic" class="field-line">
                  <span class="field-k">调度间隔</span>
                  <div class="tf-ctl">
                    <NumberSpinner v-model="form.interval" :min="1" :max="365" />
                    <span class="tf-unit">{{ intervalUnit }}</span>
                  </div>
                </div>
                <div v-else class="field-line">
                  <span class="field-k">逾期废弃</span>
                  <a-switch v-model="form.auto_abandon_on_overdue" size="small" />
                  <span class="hint">逾期未完成自动废弃</span>
                </div>
              </div>

              <div v-if="isPeriodic" class="field-line">
                <span class="field-k">有效期</span>
                <div class="tf-ctl">
                  <a-select v-model="validity" size="small" style="width: 104px">
                    <a-option value="long">长期有效</a-option>
                    <a-option value="until">派发至</a-option>
                  </a-select>
                  <a-date-picker
                    v-if="validity === 'until'"
                    v-model="form.schedule_end_date"
                    size="small"
                    style="width: 138px"
                    value-format="YYYY-MM-DD"
                  />
                </div>
              </div>

              <div class="field-line">
                <span class="field-k">关联插件</span>
                <div class="tf-ctl">
                  <a-select
                    v-model="form.plugin_id"
                    size="small"
                    allow-clear
                    allow-search
                    :options="pluginOpts"
                    :disabled="!pluginsEnabled"
                    :placeholder="pluginsEnabled ? '可选：关联插件' : '请先在设置中启用「插件」'"
                    style="flex: 1"
                  />
                  <a-button
                    v-if="isEdit && form.plugin_id"
                    size="mini"
                    type="outline"
                    :loading="runningPlugin"
                    :disabled="!canRunPlugin"
                    @click="onRunPlugin"
                  >▶ 运行</a-button>
                </div>
              </div>
              <p v-if="selectedPluginHint" class="hint tf-note">{{ selectedPluginHint }}</p>
              <p v-if="isPeriodic" class="hint tf-note">日历投影已移至 设置 → 任务 → 系统日历 统一配置。</p>
            </div>
          </section>

          <!-- ============ ⏰ 时间与提醒（统一组件：笔刷 + 日历/周期格 + 24h 时间轴） ============ -->
          <section class="zt-block">
            <div class="zt-block-head tf-time-head">
              <h3 class="zt-h3">⏰ 时间与提醒</h3>
              <div class="tf-brushes">
                <button type="button" class="b-start" :class="{ on: brush === 'start' }" title="选中后在日历/周期格上点选开始点；再点同格取消" @click="brush = 'start'">▶ 开始</button>
                <button type="button" class="b-due" :class="{ on: brush === 'due' }" title="选中后点选截止点；再点同格取消" @click="brush = 'due'">⏰ 截止</button>
                <button v-if="!isPeriodic" type="button" class="b-pop" :class="{ on: brush === 'pop' }" title="选中后在起止范围内点选弹窗时刻（可多个）" @click="brush = 'pop'">● 弹窗</button>
              </div>
            </div>

            <!-- 一次性：迷你月历（起止范围高亮 / 弹窗金点 / 跨度>3周省略行 / 公休置灰） -->
            <div v-if="!isPeriodic" class="tf-calwrap">
              <div class="tf-calbar">
                <button type="button" class="tf-nav" title="上月" @click="shiftMonth(-1)">‹</button>
                <span class="tf-calmon">{{ calLabel }}</span>
                <button type="button" class="tf-nav" title="下月" @click="shiftMonth(1)">›</button>
                <span class="tf-legend">
                  <span><i class="c-start" />开始</span>
                  <span><i class="c-due" />截止</span>
                  <span><i class="c-pop" />弹窗</span>
                </span>
              </div>
              <div class="tf-dowrow">
                <span v-for="w in DOW" :key="w" class="tf-dow">{{ w }}</span>
              </div>
              <div class="tf-cal">
                <template v-for="(row, ri) in calRows" :key="ri">
                  <div v-if="row.ellipsis" class="tf-ell" :title="row.title">⋯ {{ row.label }} ⋯</div>
                  <template v-else>
                    <template v-for="(c, ci) in row.cells" :key="ci">
                      <span v-if="!c" class="tf-day blank" />
                      <button
                        v-else
                        type="button"
                        class="tf-day"
                        :class="dayCls(c)"
                        :title="dayTitle(c)"
                        :disabled="dayLocked(c)"
                        @click="onDayClick(c)"
                        @dblclick="onDayDbl(c)"
                      >{{ c.day }}<span v-if="c.pops.length" class="tf-dot" /></button>
                    </template>
                  </template>
                </template>
              </div>
              <p class="hint tf-usenote">单击落点 · 双击关键格改时分 · 时间轴可拖</p>
            </div>

            <!-- 周期·每周：星期磁贴 -->
            <div v-else-if="form.periodicity === 'weekly'" class="tf-calwrap">
              <div class="tf-tiles">
                <button
                  v-for="(w, i) in WEEK_LABELS"
                  :key="i"
                  type="button"
                  class="tf-tile"
                  :class="tileCls(i)"
                  :title="tileTitle(i)"
                  :disabled="tileLocked(i)"
                  @click="onTileClick(i)"
                  @dblclick="onTileDbl(i)"
                >{{ w }}</button>
              </div>
              <p class="hint tf-usenote">单击磁贴按当前笔刷设开始/截止（各一点），双击已设磁贴改时分。</p>
            </div>

            <!-- 周期·每月：号点格 -->
            <div v-else-if="form.periodicity === 'monthly'" class="tf-calwrap">
              <div class="tf-mgrid">
                <button
                  v-for="d in 31"
                  :key="d"
                  type="button"
                  class="tf-mday"
                  :class="mdayCls(d)"
                  :title="mdayTitle(d)"
                  @click="onMDayClick(d)"
                  @dblclick="onMDayDbl(d)"
                >{{ d }}</button>
              </div>
              <p class="hint tf-usenote">每月号点：▶ 开始 / ⏰ 截止各一点，双击已设号点改时分。</p>
            </div>

            <!-- 周期·每天 -->
            <div v-else class="tf-calwrap">
              <p class="hint tf-usenote">每天循环：开始/截止的时分在下方时间轴上设点（可拖动）。</p>
            </div>

            <!-- 24h 时间轴：所有时刻标记一轴总览 -->
            <div ref="tlEl" class="tf-tl">
              <div ref="railEl" class="tf-rail" />
              <span v-for="h in TL_TICKS" :key="h" class="tf-tick" :style="{ left: (h / 24) * 100 + '%' }">{{ h }}</span>
              <button
                v-for="m in tlMarkers"
                :key="m.key"
                type="button"
                class="tf-mk"
                :class="[m.kind, { nopop: m.kind === 'due' && !form.popup_enabled }]"
                :style="{ left: m.left }"
                :title="m.title"
                @pointerdown="onMkDown($event, m)"
              >
                <span class="lab">{{ m.label }} {{ m.time }}</span>
                <span class="pin" />
              </button>
              <div v-if="timePop" class="tf-mkpop" :style="{ left: timePopLeft }">
                <TimeSpinner v-model="timePop.time" />
                <button v-if="timePop.del" type="button" class="tf-del" title="删除该弹窗时刻" @click="timePopDel">删</button>
                <span v-else class="hint">拖动标记改时分</span>
              </div>
            </div>

            <div class="tf-toggles">
              <label class="tf-tg"><a-switch v-model="form.popup_enabled" size="small" />到期弹窗</label>
              <label class="tf-tg"><a-switch v-model="form.skip_holidays" size="small" />跳过公休日</label>
              <span class="tf-tip" title="周末与法定节假日整体静默；开启后对应格置灰不可选">ⓘ</span>
            </div>
            <p class="hint tf-status" :class="{ warn: popHint }">{{ popHint || statusText }}</p>
          </section>

          <!-- ============ 详情（通栏） ============ -->
          <section class="zt-block">
            <div class="zt-block-head"><h3 class="zt-h3">详情</h3></div>
            <div class="field-table tf-detail-rows">
              <div v-if="aiOcrOn" class="field-line">
                <span class="field-k">图片识别</span>
                <div
                  class="ocr-drop ocr-thin"
                  :class="{ 'is-drag': dragOver, 'is-busy': aiOcrLoading }"
                  role="button"
                  tabindex="0"
                  @click="pickImage"
                  @keydown.enter.prevent="pickImage"
                  @dragover.prevent="dragOver = true"
                  @dragleave.prevent="dragOver = false"
                  @drop.prevent="onDrop"
                >
                  <template v-if="!ocrPreview">
                    <PhCamera :size="18" class="ocr-drop-icon" />
                    <span class="ocr-thin-text">点击选择、拖入或 Ctrl+V 粘贴图片，识别为任务草稿（≤9MB）</span>
                  </template>
                  <template v-else>
                    <img class="ocr-thumb" :src="ocrPreview" alt="" />
                    <div class="ocr-file-info">
                      <span class="ocr-file-name">{{ ocrFileName }}</span>
                      <span v-if="aiOcrLoading" class="ocr-status">识别中…</span>
                      <span v-else class="hint">点击可重新选择</span>
                    </div>
                    <a-button v-if="!aiOcrLoading" size="mini" status="danger" @click.stop="clearOcrFile">移除</a-button>
                  </template>
                </div>
              </div>
              <div class="field-line">
                <span class="field-k">任务详情</span>
                <a-textarea v-model="form.details" size="small" :auto-size="{ minRows: 1, maxRows: 2 }" placeholder="选填" />
              </div>
              <div class="field-line">
                <span class="field-k">{{ isPeriodic ? '预设子任务' : '子任务' }}</span>
                <div class="tf-ctl tf-chips">
                  <template v-for="(sub, idx) in form.subtasks" :key="idx">
                    <a-input
                      v-if="editSub === idx"
                      v-model="sub.title"
                      size="mini"
                      style="width: 180px"
                      :max-length="100"
                      autofocus
                      @blur="editSub = -1"
                      @press-enter="editSub = -1"
                    />
                    <span v-else class="chip editable" :title="isPeriodic ? '派发时复制到实例；点击编辑' : '点击编辑'" @click="editSub = idx">
                      {{ sub.title || '未命名' }}
                      <button type="button" class="tf-x" title="删除" @click.stop="removeSub(idx)">✕</button>
                    </span>
                  </template>
                  <a-button size="mini" @click="addSub">➕ 子任务</a-button>
                </div>
              </div>
              <!-- 附件/链接：仅一次性任务（模板无此字段） -->
              <div v-if="!isTemplate && form.mode !== 'periodic'" class="field-line">
                <span class="field-k">附件 / 链接</span>
                <div class="tf-ctl tf-chips">
                  <span v-for="(a, idx) in form.attachments" :key="idx" class="chip" :title="a">
                    {{ attIcon(a) }} {{ attLabel(a) }}
                    <button type="button" class="tf-x" title="移除" @click="form.attachments.splice(idx, 1)">✕</button>
                  </span>
                  <a-button size="mini" :loading="picking" @click="addAttachmentFile">📎 文件</a-button>
                  <a-input-search
                    v-model="newLink"
                    size="mini"
                    placeholder="粘贴 https:// 链接，回车添加"
                    style="width: 220px"
                    search-button
                    @search="addAttachmentLink"
                  />
                </div>
              </div>
            </div>
          </section>
        </div>
      </a-spin>
    </div>

    <div class="page-footer">
      <a-button @click="onCancel">取消</a-button>
      <a-button type="primary" :loading="saving" @click="onSave">💾 保存任务</a-button>
    </div>

    <a-modal
      v-model:visible="showAddSec"
      title="添加二级分类"
      draggable
      unmount-on-close
      @ok="onAddSecondary"
      :ok-loading="addingSec"
    >
      <div v-stagger>
        <a-input v-model="newSecName" placeholder="二级分类名称" @press-enter="onAddSecondary" />
        <p class="hint" style="margin-top: 8px">
          将添加到一级「{{ primaryName() }}」下（一级仅能选择已有项）。
        </p>
      </div>
    </a-modal>

    <!-- AI 解析 / 图片识别共用的草稿预览：逐字段确认后应用 -->
    <a-modal
      v-model:visible="showAiPreview"
      title="AI 解析结果"
      draggable
      :width="520"
      ok-text="应用到表单"
      cancel-text="取消"
      @ok="applyDraft"
    >
      <div v-if="previewDraft" class="ai-preview">
        <div class="ai-row"><span class="ai-k">标题</span><span class="ai-v strong">{{ previewDraft.title }}</span></div>
        <div class="ai-row">
          <span class="ai-k">分类</span>
          <span class="ai-v">
            <template v-if="categoryMatch">{{ categoryMatch.name }}<em class="ai-ok">（已匹配）</em></template>
            <template v-else-if="previewDraft.category">{{ previewDraft.category }}<em class="ai-warn">（未匹配已有分类，保持当前）</em></template>
            <template v-else>—</template>
          </span>
        </div>
        <div class="ai-row"><span class="ai-k">优先级</span><span class="ai-v">{{ PRI_LABEL[previewDraft.priority] || '中' }}</span></div>
        <div class="ai-row"><span class="ai-k">截止日期</span><span class="ai-v">{{ previewDraft.deadline || '—' }}</span></div>
        <div class="ai-row"><span class="ai-k">提醒时间</span><span class="ai-v">{{ previewDraft.reminder_time || '—' }}</span></div>
        <div class="ai-row"><span class="ai-k">详情</span><span class="ai-v pre">{{ previewDraft.details || '—' }}</span></div>
        <div class="ai-row">
          <span class="ai-k">子任务</span>
          <ul v-if="previewDraft.subtasks?.length" class="ai-subs">
            <li v-for="s in previewDraft.subtasks" :key="s">{{ s }}</li>
          </ul>
          <span v-else class="ai-v">—</span>
        </div>
      </div>
    </a-modal>

    <!-- 图片识别出多条：先选哪一条 -->
    <a-modal v-model:visible="showOcrPick" title="识别到多条任务" draggable :width="480" :footer="false">
      <p class="hint">选择一条填入表单：</p>
      <div v-for="(d, i) in ocrDrafts" :key="i" class="ocr-item" @click="chooseOcrDraft(d)">
        <span class="strong">{{ d.title }}</span>
        <span class="hint">{{ [d.category, PRI_LABEL[d.priority], d.deadline].filter(Boolean).join(' · ') }}</span>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { PhCamera, PhSparkle } from '@phosphor-icons/vue'
import {
  addSecondaryCategory,
  aiOcr,
  aiParse,
  cancelHost,
  closeHost,
  createTask,
  createTemplate,
  getHolidays,
  getMeta,
  getTask,
  getTemplate,
  listPlugins,
  pickPath,
  runPlugin,
  updateTask,
  updateTemplate,
} from '@/api/client'
import { attIcon, attLabel } from '@/utils/attachments'
import NumberSpinner from '@/components/NumberSpinner.vue'
import TimeSpinner from '@/components/TimeSpinner.vue'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()
const taskId = computed(() => props.id || route.params.id)
const isEdit = computed(() => Boolean(taskId.value))
const isTemplate = ref(false)

function handleExit(payload = { action: 'saved' }) {
  if (route.query.from === 'list') {
    router.push('/tasks')
  } else {
    closeHost(payload)
  }
}

function onCancel() {
  if (route.query.from === 'list') {
    router.push('/tasks')
  } else {
    cancelHost()
  }
}

const loading = ref(false)
const saving = ref(false)
const meta = ref(null)
const showAddSec = ref(false)
const newSecName = ref('')
const addingSec = ref(false)
const pluginsEnabled = ref(false)
const pluginItems = ref([])
const pluginsBusy = ref(false)
const runningPlugin = ref(false)

const form = reactive({
  mode: 'one-time',
  title: '',
  category_primary_id: null,
  category_secondary_id: null,
  priority: 'medium',
  has_deadline: false,
  deadline: '',
  due_time: '23:59',
  popup_enabled: false,
  deadline_weekday: 6,
  deadline_day_of_month: 31,
  details: '',
  auto_abandon_on_overdue: false,
  periodicity: 'daily',
  interval: 1,
  long_term: true,
  schedule_end_date: '',
  skip_holidays: false,
  start_enabled: false,
  start_date: '',
  start_time: '09:00',
  start_slots: [],
  deliveries: [],
  subtasks: [],
  task_type: 'one-time',
  template_id: null,
  plugin_id: null,
  attachments: [],
})

const periodOpts = [
  { label: '每天', value: 'daily' },
  { label: '每周', value: 'weekly' },
  { label: '每月', value: 'monthly' },
]
// 周几文案（存储值 0=周一 … 6=周日，与后端 wd 表一致）
const WEEK_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const DOW = ['一', '二', '三', '四', '五', '六', '日']
const TL_TICKS = [0, 6, 12, 18, 24]
const priorityOpts = [
  { label: '🔴 紧急高危', value: 'high' },
  { label: '🟡 中等优先级', value: 'medium' },
  { label: '🟢 低优先级', value: 'low' },
]

const secondaryEnabled = computed(
  () => meta.value?.categories?.enabled_secondary !== false,
)

const primaryOpts = computed(() => {
  const list = meta.value?.categories?.primary_list || []
  return list.map((p) => ({ label: p.name, value: p.id }))
})

const secondaryOpts = computed(() => {
  const list = meta.value?.categories?.primary_list || []
  const p = list.find((x) => x.id === form.category_primary_id)
  return (p?.secondaries || []).map((s) => ({ label: s.name, value: s.id }))
})

const intervalUnit = computed(
  () => ({ daily: '天', weekly: '周', monthly: '月' })[form.periodicity] || '天',
)

const isWeeklyOrMonthly = computed(
  () =>
    form.mode === 'periodic' &&
    (form.periodicity === 'weekly' || form.periodicity === 'monthly'),
)

/** 周期模式（含编辑模板）：开始/截止的形态按周期性切换 */
const isPeriodic = computed(() => form.mode === 'periodic' || isTemplate.value)

/** 一级分类提醒时间窗；未启用则 00:00 / 23:59（时间四要素默认值来源） */
function winTimes() {
  const p = (meta.value?.categories?.primary_list || []).find(
    (x) => x.id === form.category_primary_id,
  )
  if (p?.remind_window_enabled) {
    return {
      start: p.remind_window_start || '00:00',
      end: p.remind_window_end || '23:59',
    }
  }
  return { start: '00:00', end: '23:59' }
}

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

/** 有效期合并控件：长期有效 ⇄ 派发至日期（互斥，映射 long_term/schedule_end_date） */
const validity = computed({
  get: () => (form.long_term ? 'long' : 'until'),
  set: (v) => {
    form.long_term = v === 'long'
    if (v === 'long') form.schedule_end_date = ''
  },
})

// ---- 关联插件 ----

const pluginOpts = computed(() => {
  const items = pluginItems.value || []
  return items.map((p) => ({
    label: `${p.type === 'service' ? '🔧' : '📜'} ${p.name} (${p.id})`,
    value: p.id,
  }))
})

const selectedPlugin = computed(() =>
  (pluginItems.value || []).find((p) => p.id === form.plugin_id),
)

const selectedPluginHint = computed(() =>
  selectedPlugin.value ? '关联后，插件在本任务的每个弹窗时刻自动运行' : '',
)

const canRunPlugin = computed(() => {
  const p = selectedPlugin.value
  if (!p || !pluginsEnabled.value) return false
  if (p.type === 'script' && pluginsBusy.value) return false
  return true
})

async function loadPlugins() {
  try {
    const data = await listPlugins()
    pluginsEnabled.value = Boolean(data.enabled)
    pluginItems.value = data.items || []
    pluginsBusy.value = Boolean(data.busy)
  } catch (_) {
    pluginsEnabled.value = false
    pluginItems.value = []
  }
}

function onRunPlugin() {
  if (!form.plugin_id || !canRunPlugin.value) return
  const p = selectedPlugin.value
  const name = p?.name || form.plugin_id
  Modal.confirm({
    title: '运行关联插件',
    content: `确定运行「${name}」？进度将显示在托盘顶栏。`,
    okText: '运行',
    async onOk() {
      runningPlugin.value = true
      try {
        const body = p?.type === 'service'
          ? { action: 'start' }
          : (form.id ? { task_id: form.id } : {})
        await runPlugin(form.plugin_id, body)
        Message.success(
          p?.type === 'service'
            ? '已发送服务命令'
            : '插件已开始运行，可在 设置 → 🧩 插件 → 运行历史 查看',
        )
        await loadPlugins()
      } catch (e) {
        const msg = e?.response?.data?.error || e?.message || '运行失败'
        Message.error(msg)
      } finally {
        runningPlugin.value = false
      }
    },
  })
}

function onPrimaryChange() {
  form.category_secondary_id = null
  seedSkipHolidays()
}

/** 回填清洗：任务里的分类 id 可能已随分类删建失效（无匹配 option 时
 * a-select 会把裸 uuid 当文本显示），按任务自带分类名找回，仍无则置空 */
function sanitizeCategoryIds(categoryName) {
  const list = meta.value?.categories?.primary_list || []
  const sep = meta.value?.categories?.level_separator || '-'
  const p = list.find((x) => x.id === form.category_primary_id)
  if (!p) {
    const name = String(categoryName || '').split(sep)[0]
    const hit = list.find((x) => x.name === name)
    form.category_primary_id = hit?.id ?? null
    form.category_secondary_id = null
    return
  }
  if (form.category_secondary_id && !(p.secondaries || []).some((s) => s.id === form.category_secondary_id)) {
    const subName = String(categoryName || '').includes(sep)
      ? String(categoryName).split(sep).slice(1).join(sep)
      : ''
    form.category_secondary_id = (p.secondaries || []).find((s) => s.name === subName)?.id ?? null
  }
}

/** 新建时按一级分类预设带出「跳过公休日」；编辑不动已有值 */
function seedSkipHolidays() {
  if (isEdit.value) return
  const p = (meta.value?.categories?.primary_list || []).find(
    (x) => x.id === form.category_primary_id,
  )
  form.skip_holidays = !!(p && p.skip_holidays)
}

// ============ 统一时间组件：笔刷 + 日历/周期格 + 24h 时间轴 ============

/** 当前笔刷：start=设开始点 due=设截止点 pop=加弹窗时刻（仅一次性） */
const brush = ref('start')
watch(isPeriodic, (v) => {
  if (v && brush.value === 'pop') brush.value = 'start'
})

/** 周期切换时归一化单 slot 形态（周↔月带不同点位字段） */
watch(() => form.periodicity, (p) => {
  if (!isPeriodic.value || p === 'daily') return
  const s = form.start_slots[0]
  if (!s) return
  if (p === 'weekly' && s.weekday == null) {
    form.start_slots = [{ ...s, weekday: 0, day_of_month: null }]
  } else if (p === 'monthly' && s.day_of_month == null) {
    form.start_slots = [{ ...s, weekday: null, day_of_month: 1 }]
  }
})

/** 开始单点：写入/替换唯一 slot（保留原时分，首设取提醒窗起点） */
function ensureSlot(weekday, dayOfMonth) {
  const time = form.start_slots[0]?.time_of_day || winTimes().start
  form.start_slots = [{ weekday, day_of_month: dayOfMonth, time_of_day: time }]
  form.start_enabled = true
}

// ---- 节假日数据（/api/holidays，按年缓存） ----
const holidays = ref(new Set())
const _holYearCache = {}

async function ensureHolidays(year) {
  if (_holYearCache[year]) return
  _holYearCache[year] = true
  try {
    const dates = await getHolidays(year)
    holidays.value = new Set([...holidays.value, ...dates])
  } catch (_) {
    _holYearCache[year] = false // 失败可重试
  }
}

// ---- 迷你月历（一次性） ----
const calYm = ref({ y: new Date().getFullYear(), m: new Date().getMonth() + 1 })

const calLabel = computed(
  () => `${calYm.value.y} 年 ${calYm.value.m} 月`,
)

watch(() => calYm.value.y, (y) => ensureHolidays(y), { immediate: true })

/** 起止设置变化时月历自动跳到关键月（AI 解析回填同样生效） */
watch(
  () => [form.start_date, form.deadline],
  ([s, d]) => {
    const iso = s || d
    const m = String(iso || '').match(/^(\d{4})-(\d{2})-/)
    if (m) calYm.value = { y: +m[1], m: +m[2] }
  },
)

function shiftMonth(delta) {
  let { y, m } = calYm.value
  m += delta
  if (m < 1) { m = 12; y -= 1 }
  if (m > 12) { m = 1; y += 1 }
  calYm.value = { y, m }
}

/** 一次性起止范围（ISO 日期串比较）；未设为 null */
const rangeStart = computed(() =>
  form.start_enabled && form.start_date ? form.start_date : null,
)
const rangeEnd = computed(() =>
  form.has_deadline && form.deadline ? form.deadline : null,
)

function inRange(date) {
  const s = rangeStart.value
  const e = rangeEnd.value
  return !!((s && date > s) && (e && date < e))
}

/** 弹窗限域：起止已设时，范围外不可加弹窗（边界日允许） */
function dayPopLocked(c) {
  const s = rangeStart.value
  const e = rangeEnd.value
  return !!((s && c.date < s) || (e && c.date > e))
}

function cellFor(y, m, d) {
  const date = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
  const dow = new Date(y, m - 1, d).getDay()
  const weekend = dow === 0 || dow === 6
  const pops = form.deliveries
    .map((x, i) => ({ ...x, i }))
    .filter((x) => x.date === date)
  return {
    date,
    day: d,
    isStart: rangeStart.value === date,
    isDue: rangeEnd.value === date,
    inRange: inRange(date),
    pops,
    skip: form.skip_holidays && (weekend || holidays.value.has(date)),
    today: date === todayStr(),
  }
}

function dayDiff(a, b) {
  return Math.round(
    (new Date(b) - new Date(a)) / 86400000,
  )
}

/** 月历行：周一起始；起止跨度 >3 周时，中间无关键节点的整周行折叠为省略行 */
const calRows = computed(() => {
  const { y, m } = calYm.value
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7
  const days = new Date(y, m, 0).getDate()
  const cells = []
  for (let i = 0; i < lead; i++) cells.push(null)
  for (let d = 1; d <= days; d++) cells.push(cellFor(y, m, d))
  while (cells.length % 7) cells.push(null)
  const rows = []
  for (let i = 0; i < cells.length; i += 7) rows.push({ cells: cells.slice(i, i + 7) })

  const s = rangeStart.value
  const e = rangeEnd.value
  if (!(s && e && dayDiff(s, e) > 21)) return rows

  const collapsible = (r) => {
    const real = r.cells.filter(Boolean)
    return (
      real.length === 7 &&
      real.every((c) => c.inRange && !c.isStart && !c.isDue && !c.pops.length)
    )
  }
  const out = []
  let run = []
  const flush = () => {
    if (run.length >= 2) {
      const first = run[0].cells.find(Boolean).date
      const last = run[run.length - 1].cells.filter(Boolean).pop().date
      out.push({
        ellipsis: true,
        label: `${first.slice(5)} ~ ${last.slice(5)}（无关键节点，已省略）`,
        title: '起止跨度超过三周，中间整周无开始/截止/弹窗节点，折叠显示',
      })
    } else {
      out.push(...run)
    }
    run = []
  }
  for (const r of rows) {
    if (collapsible(r)) run.push(r)
    else flush(), out.push(r)
  }
  flush()
  return out
})

function dayCls(c) {
  return {
    start: c.isStart,
    due: c.isDue,
    inrange: c.inRange,
    skip: c.skip,
    locked: brush.value === 'pop' && dayPopLocked(c),
    today: c.today,
  }
}

function dayTitle(c) {
  const parts = []
  if (c.isStart) parts.push(`开始 ${form.start_time}`)
  if (c.isDue) parts.push(`截止 ${form.due_time || '23:59'}`)
  if (c.pops.length) parts.push(`弹窗 ${c.pops.map((p) => p.time).join(' / ')}`)
  if (c.skip) parts.push('公休日（跳过中，不可选）')
  else if (brush.value === 'pop' && dayPopLocked(c)) parts.push('超出起止范围，弹窗不可设')
  else if (!parts.length && c.inRange) parts.push('起止范围内')
  return parts.join(' · ') || c.date
}

function dayLocked(c) {
  return c.skip || (brush.value === 'pop' && dayPopLocked(c))
}

const popHint = ref('')
let _popHintTimer = null

function setPopHint(msg) {
  popHint.value = msg
  clearTimeout(_popHintTimer)
  _popHintTimer = setTimeout(() => (popHint.value = ''), 3000)
}

function onDayClick(c) {
  if (dayLocked(c)) {
    if (brush.value === 'pop' && dayPopLocked(c)) setPopHint('弹窗需设在开始与截止之间')
    return
  }
  const d = c.date
  if (brush.value === 'start') {
    if (rangeStart.value === d) {
      form.start_enabled = false
      form.start_date = ''
    } else {
      if (!form.start_time) form.start_time = winTimes().start
      form.start_enabled = true
      form.start_date = d
    }
  } else if (brush.value === 'due') {
    if (rangeEnd.value === d) {
      form.has_deadline = false
      form.deadline = ''
    } else {
      if (!form.due_time) form.due_time = winTimes().end
      form.has_deadline = true
      form.deadline = d
    }
  } else {
    if (c.pops.length) {
      form.deliveries = form.deliveries.filter((x) => x.date !== d)
    } else {
      form.deliveries.push({ date: d, time: winTimes().start || '09:00', notify: true })
    }
  }
}

function onDayDbl(c) {
  if (c.isStart) openTimePop('start')
  else if (c.isDue) openTimePop('due')
  else if (c.pops.length) openTimePop('pop:' + c.pops[0].i)
}

// ---- 周期格：每周磁贴 / 每月号点 ----

function tileCls(i) {
  const s = form.start_slots[0]
  return {
    start: form.start_enabled && s?.weekday === i,
    due: form.has_deadline && form.deadline_weekday === i,
    skip: form.skip_holidays && i >= 5,
  }
}

function tileLocked(i) {
  return form.skip_holidays && i >= 5
}

function tileTitle(i) {
  const s = form.start_slots[0]
  const parts = []
  if (form.start_enabled && s?.weekday === i) parts.push(`开始 ${s.time_of_day}`)
  if (form.has_deadline && form.deadline_weekday === i) parts.push(`截止 ${form.due_time || '23:59'}`)
  if (tileLocked(i)) parts.push('公休日（跳过中，不可选）')
  return parts.join(' · ') || WEEK_LABELS[i]
}

function onTileClick(i) {
  if (tileLocked(i)) return
  if (brush.value === 'start') {
    if (form.start_enabled && form.start_slots[0]?.weekday === i) {
      form.start_enabled = false
      form.start_slots = []
    } else {
      ensureSlot(i, null)
    }
  } else if (brush.value === 'due') {
    if (form.has_deadline && form.deadline_weekday === i) {
      form.has_deadline = false
    } else {
      if (!form.due_time) form.due_time = winTimes().end
      form.has_deadline = true
      form.deadline_weekday = i
    }
  }
}

function onTileDbl(i) {
  if (form.start_enabled && form.start_slots[0]?.weekday === i) openTimePop('start')
  else if (form.has_deadline && form.deadline_weekday === i) openTimePop('due')
}

function mdayCls(d) {
  const s = form.start_slots[0]
  return {
    start: form.start_enabled && s?.day_of_month === d,
    due: form.has_deadline && form.deadline_day_of_month === d,
  }
}

function mdayTitle(d) {
  const s = form.start_slots[0]
  const parts = []
  if (form.start_enabled && s?.day_of_month === d) parts.push(`开始 ${s.time_of_day}`)
  if (form.has_deadline && form.deadline_day_of_month === d) parts.push(`截止 ${form.due_time || '23:59'}`)
  return parts.join(' · ') || `每月 ${d} 日`
}

function onMDayClick(d) {
  if (brush.value === 'start') {
    if (form.start_enabled && form.start_slots[0]?.day_of_month === d) {
      form.start_enabled = false
      form.start_slots = []
    } else {
      ensureSlot(null, d)
    }
  } else if (brush.value === 'due') {
    if (form.has_deadline && form.deadline_day_of_month === d) {
      form.has_deadline = false
    } else {
      if (!form.due_time) form.due_time = winTimes().end
      form.has_deadline = true
      form.deadline_day_of_month = d
    }
  }
}

function onMDayDbl(d) {
  if (form.start_enabled && form.start_slots[0]?.day_of_month === d) openTimePop('start')
  else if (form.has_deadline && form.deadline_day_of_month === d) openTimePop('due')
}

// ---- 24h 时间轴：标记总览 + 拖拽改时分 + 点击弹层编辑 ----

function hm2min(t) {
  const [h, m] = String(t || '09:00').split(':').map(Number)
  return Math.min(1440, Math.max(0, (h || 0) * 60 + (m || 0)))
}

function min2hm(mins) {
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function slotPointLabel() {
  const s = form.start_slots[0]
  if (!s) return ''
  if (form.periodicity === 'weekly') return `每周${(WEEK_LABELS[s.weekday] || '一').slice(1)}`
  if (form.periodicity === 'monthly') return `每月 ${s.day_of_month} 日`
  return '每天'
}

function duePointLabel() {
  if (form.periodicity === 'weekly') return `每周${(WEEK_LABELS[form.deadline_weekday] || '日').slice(1)}`
  if (form.periodicity === 'monthly') return `每月 ${form.deadline_day_of_month} 日`
  return '每天'
}

const tlMarkers = computed(() => {
  const out = []
  const pos = (t) => ((hm2min(t) / 1440) * 100).toFixed(2) + '%'
  if (!isPeriodic.value) {
    if (form.start_enabled && form.start_date) {
      out.push({ key: 'start', kind: 'start', label: '▶', time: form.start_time, left: pos(form.start_time), title: `开始 ${form.start_date} ${form.start_time}` })
    }
    if (form.has_deadline && form.deadline) {
      out.push({ key: 'due', kind: 'due', label: '⏰', time: form.due_time || '23:59', left: pos(form.due_time), title: `截止 ${form.deadline} ${form.due_time || '23:59'}` })
    }
    form.deliveries.forEach((d, i) => {
      if (d.date && d.time) {
        out.push({ key: 'pop:' + i, kind: 'pop', label: '●', time: d.time, left: pos(d.time), title: `弹窗 ${d.date} ${d.time}` })
      }
    })
    return out
  }
  if (form.periodicity === 'daily') {
    if (form.start_enabled) {
      out.push({ key: 'start', kind: 'start', label: '▶', time: form.start_time, left: pos(form.start_time), title: `每天 ${form.start_time} 开始` })
    }
  } else {
    const s = form.start_slots[0]
    if (form.start_enabled && s) {
      out.push({ key: 'start', kind: 'start', label: '▶', time: s.time_of_day, left: pos(s.time_of_day), title: `${slotPointLabel()} ${s.time_of_day} 开始` })
    }
  }
  if (form.has_deadline) {
    out.push({ key: 'due', kind: 'due', label: '⏰', time: form.due_time || '23:59', left: pos(form.due_time), title: `${duePointLabel()} ${form.due_time || '23:59'} 截止` })
  }
  return out
})

/** 标记时间写回：key = start | due | pop:<idx> */
function applyTime(key, t) {
  if (!t) return
  if (key === 'start') {
    if (!isPeriodic.value || form.periodicity === 'daily') form.start_time = t
    else if (form.start_slots[0]) form.start_slots[0].time_of_day = t
  } else if (key === 'due') {
    form.due_time = t
  } else if (key.startsWith('pop:')) {
    const i = Number(key.slice(4))
    if (form.deliveries[i]) form.deliveries[i].time = t
  }
}

const railEl = ref(null)
const timePop = ref(null)
let dragInfo = null

const timePopLeft = computed(
  () => tlMarkers.value.find((m) => m.key === timePop.value?.key)?.left || '50%',
)

function openTimePop(key) {
  const m = tlMarkers.value.find((x) => x.key === key)
  if (!m) return
  timePop.value = { key, time: m.time, del: key.startsWith('pop:') }
}

function closeTimePop() {
  timePop.value = null
}

watch(
  () => timePop.value?.time,
  (v) => {
    if (v && timePop.value) applyTime(timePop.value.key, v)
  },
)

function timePopDel() {
  const key = timePop.value?.key || ''
  if (key.startsWith('pop:')) {
    form.deliveries.splice(Number(key.slice(4)), 1)
  }
  closeTimePop()
}

function onMkDown(e, m) {
  dragInfo = { key: m.key, x0: e.clientX, moved: false }
  e.preventDefault()
}

function onWinPointerMove(e) {
  if (!dragInfo) return
  if (Math.abs(e.clientX - dragInfo.x0) > 3) dragInfo.moved = true
  if (!dragInfo.moved) return
  const r = railEl.value?.getBoundingClientRect()
  if (!r) return
  const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
  applyTime(dragInfo.key, min2hm(Math.round((f * 1440) / 15) * 15))
}

function onWinPointerUp() {
  if (!dragInfo) return
  if (dragInfo.moved) closeTimePop()
  else openTimePop(dragInfo.key)
  dragInfo = null
}

// ---- 状态句 ----

function md(iso) {
  return String(iso || '').slice(5)
}

const statusText = computed(() => {
  const parts = []
  if (!isPeriodic.value) {
    if (form.start_enabled && form.start_date) parts.push(`${md(form.start_date)} ${form.start_time} 开始`)
    if (form.has_deadline && form.deadline) parts.push(`${md(form.deadline)} ${form.due_time || '23:59'} 截止`)
    if (form.deliveries.length) parts.push(`${form.deliveries.length} 个交付弹窗`)
  } else if (form.periodicity === 'weekly') {
    const s = form.start_slots[0]
    if (form.start_enabled && s) parts.push(`${slotPointLabel()} ${s.time_of_day} 开始`)
    if (form.has_deadline) parts.push(`${duePointLabel()} ${form.due_time || '23:59'} 截止`)
  } else if (form.periodicity === 'monthly') {
    const s = form.start_slots[0]
    if (form.start_enabled && s) parts.push(`${slotPointLabel()} ${s.time_of_day} 开始`)
    if (form.has_deadline) parts.push(`${duePointLabel()} ${form.due_time || '23:59'} 截止`)
  } else {
    if (form.start_enabled) parts.push(`每天 ${form.start_time} 开始`)
    if (form.has_deadline) parts.push(`每天 ${form.due_time || '23:59'} 截止`)
  }
  if (parts.length || form.start_enabled || form.has_deadline) parts.push(form.popup_enabled ? '到期弹窗' : '不弹窗')
  if (form.skip_holidays) parts.push('跳过公休日')
  return parts.join(' · ') || '未设时间：保存后创建/派发即进入轮播'
})

// ---- AI 场景能力：文本解析 + 图片识别（开关来自 meta.ai_features，默认关）----

const PRI_LABEL = { high: '高', medium: '中', low: '低' }
const aiParseOn = computed(() => !!meta.value?.ai_features?.smart_parse)
const aiOcrOn = computed(() => !!meta.value?.ai_features?.image_ocr)
const aiParsing = ref(false)
const aiOcrLoading = ref(false)
const showAiPreview = ref(false)
const previewDraft = ref(null)
const showOcrPick = ref(false)
const ocrDrafts = ref([])
const fileRef = ref(null)
const dragOver = ref(false)
const ocrPreview = ref('')
const ocrFileName = ref('')

function clearOcrFile() {
  if (ocrPreview.value) URL.revokeObjectURL(ocrPreview.value)
  ocrPreview.value = ''
  ocrFileName.value = ''
}

/** 草稿 category（名称，可能带二级「工作/开发」）→ 已有分类 id；匹配不上返回 null */
const categoryMatch = computed(() => {
  const d = previewDraft.value
  if (!d?.category) return null
  const cats = meta.value?.categories
  const sep = cats?.level_separator || '-'
  const list = cats?.primary_list || []
  const name = d.category.trim()
  for (const p of list) {
    if (name === p.name) return { primary: p.id, secondary: null, name: p.name }
    if (name.startsWith(p.name + sep)) {
      const rest = name.slice((p.name + sep).length)
      const sec = (p.secondaries || []).find((s) => s.name === rest)
      return { primary: p.id, secondary: sec?.id || null, name: sec ? `${p.name}${sep}${sec.name}` : p.name }
    }
  }
  // 模糊：互相包含的一级
  for (const p of list) {
    if (name.includes(p.name) || p.name.includes(name)) return { primary: p.id, secondary: null, name: p.name }
  }
  return null
})

async function onAiParse() {
  const text = [form.title, form.details].filter((x) => x && x.trim()).join('\n')
  if (!text) {
    Message.warning('先填写标题或详情，再让 AI 解析')
    return
  }
  aiParsing.value = true
  try {
    previewDraft.value = await aiParse(text)
    showAiPreview.value = true
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || 'AI 解析失败')
  } finally {
    aiParsing.value = false
  }
}

function pickImage() {
  if (!aiOcrLoading.value) fileRef.value?.click()
}

async function onFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (f) await runOcr(f)
}

/** 拖放：取首个图片文件，非图片提示 */
function onDrop(e) {
  dragOver.value = false
  const f = Array.from(e.dataTransfer?.files || []).find((x) => x.type.startsWith('image/'))
  if (!f) {
    Message.warning('仅支持图片文件')
    return
  }
  runOcr(f)
}

async function runOcr(file) {
  if (aiOcrLoading.value) return
  clearOcrFile()
  if (file.size > 9 * 1024 * 1024) {
    Message.warning('图片过大（>9MB），请压缩后重试')
    return
  }
  ocrFileName.value = file.name || '剪贴板图片'
  ocrPreview.value = URL.createObjectURL(file)
  aiOcrLoading.value = true
  try {
    const dataUrl = await new Promise((res, rej) => {
      const r = new FileReader()
      r.onload = () => res(r.result)
      r.onerror = rej
      r.readAsDataURL(file)
    })
    const drafts = await aiOcr(dataUrl)
    if (!drafts.length) {
      Message.info('图片中未识别到待办线索')
      return
    }
    if (drafts.length === 1) {
      previewDraft.value = drafts[0]
      showAiPreview.value = true
    } else {
      ocrDrafts.value = drafts
      showOcrPick.value = true
    }
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '图片识别失败')
  } finally {
    aiOcrLoading.value = false
  }
}

/** 直接 Ctrl+V 粘贴截图进表单页 */
async function onPaste(e) {
  if (!aiOcrOn.value) return
  const item = Array.from(e.clipboardData?.items || []).find((i) => i.type.startsWith('image/'))
  if (!item) return
  const f = item.getAsFile()
  if (f) {
    e.preventDefault()
    await runOcr(f)
  }
}

function chooseOcrDraft(d) {
  showOcrPick.value = false
  previewDraft.value = d
  showAiPreview.value = true
}

/** 应用草稿到表单：分类按名称匹配（匹配不上不动）；子任务追加去重 */
function applyDraft() {
  const d = previewDraft.value
  if (!d?.title) return
  form.title = d.title
  if (d.priority) form.priority = d.priority
  const m = categoryMatch.value
  if (m) {
    form.category_primary_id = m.primary
    form.category_secondary_id = m.secondary
  }
  if (d.deadline && form.mode !== 'periodic' && !isTemplate.value) {
    form.has_deadline = true
    form.deadline = d.deadline
    if (!form.due_time) form.due_time = winTimes().end
  }
  if (d.details) form.details = d.details
  if (d.subtasks?.length) {
    const exist = new Set(form.subtasks.map((s) => (s.title || '').trim()))
    for (const t of d.subtasks) {
      if (!exist.has(t)) form.subtasks.push({ id: null, title: t, status: 'active' })
    }
  }
  showAiPreview.value = false
  Message.success('已应用 AI 解析结果')
}

function primaryName() {
  const o = primaryOpts.value.find((x) => x.value === form.category_primary_id)
  return o?.label || '工作'
}

// ---- 子任务 / 附件 ----

const editSub = ref(-1)

function addSub() {
  form.subtasks.push({ id: null, title: '', status: 'active' })
  editSub.value = form.subtasks.length - 1
}

function removeSub(idx) {
  form.subtasks.splice(idx, 1)
  if (editSub.value === idx) editSub.value = -1
}

// ---- 附件/链接（存字符串：http(s)=链接，其余=本地路径） ----
const picking = ref(false)
const newLink = ref('')

async function addAttachmentFile() {
  picking.value = true
  try {
    const r = await pickPath('file', { title: '选择附件', filter: '所有文件 (*)' })
    if (r?.path && !form.attachments.includes(r.path)) form.attachments.push(r.path)
  } finally {
    picking.value = false
  }
}

function addAttachmentLink() {
  const v = newLink.value.trim()
  if (!v) return
  if (!/^https?:\/\//i.test(v)) {
    Message.warning('链接需以 http:// 或 https:// 开头')
    return
  }
  if (!form.attachments.includes(v)) form.attachments.push(v)
  newLink.value = ''
}

function buildPayload() {
  // 额外弹窗时间：加进列表即弹（notify 恒 true），排序后随 payload 下发
  const deliveries = (form.deliveries || [])
    .filter((d) => d.date && d.time)
    .map((d) => ({ at: `${d.date}T${d.time}`, notify: true }))
    .sort((a, b) => a.at.localeCompare(b.at))
  const base = {
    title: form.title.trim(),
    category: primaryName(),
    category_primary_id: form.category_primary_id,
    category_secondary_id: form.category_secondary_id,
    priority: form.priority,
    details: form.details || '',
    reminder: null, // 旧弹窗提醒机制停用；编辑保存即清除旧任务的弹窗提醒
    skip_holidays: !!form.skip_holidays,
    auto_abandon_on_overdue: form.auto_abandon_on_overdue,
    attachments: (form.attachments || []).slice(),
    subtasks: (form.subtasks || [])
      .filter((s) => (s.title || '').trim())
      .map((s) => ({ id: s.id, title: s.title.trim(), status: s.status || 'active' })),
    plugin_id: form.plugin_id || null,
  }

  if (form.mode === 'periodic' || isTemplate.value) {
    // 开始单点：日=仅时分；周/月=唯一点位 slot（UI 保证 ≤1）
    const slots = !form.start_enabled
      ? []
      : isWeeklyOrMonthly.value
        ? (form.start_slots || []).slice(0, 1).map((s) => {
            if (form.periodicity === 'weekly') {
              return {
                time_of_day: s.time_of_day || '09:00',
                weekday: Math.max(0, Math.min(6, Number(s.weekday) || 0)),
                day_of_month: null,
              }
            }
            return {
              time_of_day: s.time_of_day || '09:00',
              weekday: null,
              day_of_month: Math.max(1, Math.min(31, Number(s.day_of_month) || 1)),
            }
          })
        : [{ time_of_day: form.start_time || '09:00', weekday: null, day_of_month: null }]
    return {
      ...base,
      task_type: 'periodic',
      periodicity: form.periodicity,
      interval: form.interval || 1,
      long_term: form.long_term,
      schedule_end_date: form.long_term ? null : form.schedule_end_date || null,
      remind_start_slots: slots,
      due_time: form.has_deadline ? form.due_time : null,
      popup_at_due: !!form.popup_enabled,
      deadline_weekday:
        form.has_deadline && form.periodicity === 'weekly'
          ? Math.max(0, Math.min(6, Number(form.deadline_weekday) || 0))
          : null,
      deadline_day_of_month:
        form.has_deadline && form.periodicity === 'monthly'
          ? Math.max(1, Math.min(31, Number(form.deadline_day_of_month) || 1))
          : null,
    }
  }

  return {
    ...base,
    task_type: form.task_type || 'one-time',
    template_id: form.template_id,
    deadline: form.has_deadline ? form.deadline || '' : '',
    due_time: form.has_deadline ? form.due_time : null,
    popup_at_due: !!form.popup_enabled,
    remind_start: form.start_enabled && form.start_date ? `${form.start_date}T${form.start_time}` : null,
    deliveries,
  }
}

async function onAddSecondary() {
  const name = newSecName.value.trim()
  if (!name || !form.category_primary_id) {
    Message.warning('请填写名称并选择一级分类')
    return
  }
  addingSec.value = true
  try {
    const data = await addSecondaryCategory(form.category_primary_id, name)
    if (data.categories) {
      meta.value = { ...(meta.value || {}), categories: data.categories }
    }
    if (data.secondary?.id) {
      form.category_secondary_id = data.secondary.id
    }
    Message.success('已添加二级分类')
    showAddSec.value = false
    newSecName.value = ''
  } catch (e) {
    Message.error(e?.message || '添加失败')
  } finally {
    addingSec.value = false
  }
}

async function onSave() {
  if (!form.title.trim()) {
    Message.warning('请输入标题')
    return
  }
  if (!form.category_primary_id) {
    Message.warning('请选择一级分类')
    return
  }
  const payload = buildPayload()

  saving.value = true
  try {
    if (isEdit.value) {
      if (isTemplate.value) {
        await updateTemplate(taskId.value, payload)
      } else {
        await updateTask(taskId.value, payload)
      }
    } else if (form.mode === 'periodic') {
      await createTemplate(payload)
    } else {
      await createTask(payload)
    }
    Message.success('已保存')
    handleExit({ action: 'saved' })
  } catch (e) {
    Message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    meta.value = await getMeta()
    if (!form.category_primary_id && primaryOpts.value.length) {
      form.category_primary_id = primaryOpts.value[0].value
    }
    if (route.query.mode === 'periodic') {
      form.mode = 'periodic'
    }
    if (!taskId.value) seedSkipHolidays()
    if (taskId.value) {
      if (route.query.template === '1') {
        const t = await getTemplate(taskId.value)
        isTemplate.value = true
        form.mode = 'periodic'
        form.title = t.base_title || t.title || ''
        form.priority = t.priority || 'medium'
        form.details = t.details || ''
        form.category_primary_id = t.category_primary_id
        form.category_secondary_id = t.category_secondary_id
        sanitizeCategoryIds(t.category)
        form.periodicity = t.periodicity || 'daily'
        form.interval = t.interval || 1
        form.long_term = t.long_term !== false
        form.schedule_end_date = t.schedule_end_date || ''
        form.auto_abandon_on_overdue = !!t.auto_abandon_on_overdue
        form.subtasks = (t.subtasks || []).map((s) => ({ ...s }))
        form.plugin_id = t.plugin_id || null
        form.skip_holidays = !!t.skip_holidays
        // 截止：due_time 或周几/几号规则任一存在即视为已设置
        form.has_deadline = !!(
          t.due_time ||
          t.deadline_weekday != null ||
          t.deadline_day_of_month != null
        )
        form.due_time = t.due_time || winTimes().end
        form.deadline_weekday =
          t.deadline_weekday != null ? Number(t.deadline_weekday) : 6
        form.deadline_day_of_month =
          t.deadline_day_of_month != null ? Number(t.deadline_day_of_month) : 31
        form.popup_enabled = !!t.popup_at_due
        // 开始单点：兼容旧弹窗提醒槽，多点模板只取首个（保存时收敛为单点）
        const rawSlots =
          (t.remind_start_slots?.length ? t.remind_start_slots : t.reminder?.slots) || []
        const s0 = rawSlots[0]
        form.start_enabled = rawSlots.length > 0
        if (form.periodicity === 'daily') {
          form.start_time = s0?.time_of_day || winTimes().start
        } else if (s0) {
          form.start_slots = [{
            weekday: s0.weekday != null ? Number(s0.weekday) : 0,
            day_of_month: s0.day_of_month != null ? Number(s0.day_of_month) : 1,
            time_of_day: s0.time_of_day || winTimes().start,
          }]
        }
      } else {
        const t = await getTask(taskId.value)
        form.title = t.title
        form.priority = t.priority || 'medium'
        form.details = t.details || ''
        form.category_primary_id = t.category_primary_id
        form.category_secondary_id = t.category_secondary_id
        sanitizeCategoryIds(t.category)
        form.has_deadline = Boolean(t.deadline)
        form.deadline = t.deadline || ''
        form.due_time = t.due_time || '23:59'
        form.popup_enabled = !!t.popup_at_due
        form.auto_abandon_on_overdue = !!t.auto_abandon_on_overdue
        form.task_type = t.task_type || 'one-time'
        form.template_id = t.template_id
        form.mode = 'one-time'
        form.attachments = Array.isArray(t.attachments) ? t.attachments.slice() : []
        form.subtasks = (t.subtasks || []).map((s) => ({ ...s }))
        form.plugin_id = t.plugin_id || null
        form.skip_holidays = !!t.skip_holidays
        form.start_enabled = !!t.remind_start
        if (t.remind_start) {
          form.start_date = String(t.remind_start).slice(0, 10)
          form.start_time = String(t.remind_start).slice(11, 16) || '09:00'
        }
        form.deliveries = (t.deliveries || []).map((d) => ({
          date: String(d.at || '').slice(0, 10),
          time: String(d.at || '').slice(11, 16) || '09:00',
          notify: true,
        }))
      }
    }
    // 月历初始定位：开始月 → 截止月 → 当前月
    const anchor = form.start_date || form.deadline || ''
    const m = String(anchor).match(/^(\d{4})-(\d{2})-/)
    if (m && !isPeriodic.value) calYm.value = { y: +m[1], m: +m[2] }
    loadPlugins()
  } finally {
    loading.value = false
  }
})

onMounted(() => window.addEventListener('paste', onPaste))
onMounted(() => {
  window.addEventListener('pointermove', onWinPointerMove)
  window.addEventListener('pointerup', onWinPointerUp)
})
onUnmounted(() => {
  window.removeEventListener('paste', onPaste)
  window.removeEventListener('pointermove', onWinPointerMove)
  window.removeEventListener('pointerup', onWinPointerUp)
  clearTimeout(_popHintTimer)
  clearOcrFile()
})
</script>

<style scoped>
/* ---- 固定窗一屏不滚（960×620）：页体禁滚，网格双栏 + 通栏详情 ---- */
.tf-body {
  overflow: hidden;
  padding-bottom: 0;
}
.tf-body :deep(.arco-spin) {
  height: 100%;
}
.tf-grid {
  height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 350px;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 12px;
}
.tf-grid > section {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 10px 14px;
}
.tf-grid > section:nth-of-type(1) {
  grid-area: 1 / 1;
}
.tf-grid > section:nth-of-type(2) {
  grid-area: 1 / 2;
}
.tf-grid > section:nth-of-type(3) {
  grid-column: 1 / -1;
  grid-row: 2;
}
.tf-fields {
  flex: 1;
}
.tf-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.tf-ctl {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tf-unit {
  font-size: var(--zt-note);
  color: var(--color-text-muted);
}
.tf-note {
  margin: 0 0 0 100px; /* 与 88px 行键 + 12px 间距对齐 */
}

/* ---- 笔刷选择器 ---- */
.tf-time-head {
  margin-bottom: 4px;
}
.tf-brushes {
  display: inline-flex;
  gap: 4px;
}
.tf-brushes button {
  height: 22px;
  padding: 0 10px;
  border-radius: var(--zt-radius-pill);
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  font-size: 11px;
  cursor: pointer;
}
.tf-brushes button.on {
  font-weight: 600;
}
.tf-brushes button.b-start.on {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}
.tf-brushes button.b-due.on {
  color: var(--color-danger);
  border-color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
}
.tf-brushes button.b-pop.on {
  color: var(--color-warning);
  border-color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
}

/* ---- 月历 / 周期格区域 ---- */
.tf-calwrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}
.tf-calbar {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tf-nav {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  line-height: 1;
  flex: none;
}
.tf-nav:hover {
  border-color: var(--color-primary-hover);
  color: var(--color-primary-hover);
}
.tf-calmon {
  font-size: var(--zt-note);
  color: var(--color-text-2);
  flex: 1;
}
.tf-legend {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-size: 10.5px;
  color: var(--color-text-muted);
}
.tf-legend i {
  width: 8px;
  height: 8px;
  border-radius: 99px;
  display: inline-block;
  margin-right: 3px;
  vertical-align: -1px;
}
.tf-legend .c-start {
  background: var(--color-primary);
}
.tf-legend .c-due {
  background: var(--color-danger);
}
.tf-legend .c-pop {
  background: var(--color-warning);
}
.tf-cal {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  /* minmax(0,1fr)：行可随容器收缩，杜绝整格溢出压住时间轴（v0.7.16 重叠根因） */
  grid-auto-rows: minmax(0, 1fr);
  gap: 3px;
}
.tf-dowrow {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
  height: 14px;
  flex: none;
}
.tf-dow {
  text-align: center;
  font-size: 10px;
  line-height: 14px;
  color: var(--color-text-subdued);
}
.tf-day {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-2);
  font-size: 11.5px;
  cursor: pointer;
  padding: 0;
  min-height: 0;
  font-variant-numeric: tabular-nums;
}
.tf-day:hover:not(:disabled) {
  border-color: var(--color-primary-hover);
}
.tf-day.blank {
  border: none;
  cursor: default;
}
.tf-day.today {
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
}
.tf-day.inrange {
  background: color-mix(in srgb, var(--color-primary) 10%, transparent);
  border-color: transparent;
}
.tf-day.start {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
  font-weight: 650;
}
.tf-day.due {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: #fff;
  font-weight: 650;
}
.tf-day.skip {
  opacity: 0.38;
  text-decoration: line-through;
  cursor: not-allowed;
}
.tf-day.locked {
  opacity: 0.35;
}
.tf-day:disabled {
  cursor: not-allowed;
}
.tf-dot {
  position: absolute;
  right: 3px;
  top: 3px;
  width: 5px;
  height: 5px;
  border-radius: 99px;
  background: var(--color-warning);
}
.tf-day.start .tf-dot,
.tf-day.due .tf-dot {
  background: #fff;
}
.tf-ell {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10.5px;
  color: var(--color-text-subdued);
  border: 1px dashed var(--color-border);
  border-radius: 7px;
  min-height: 18px;
}
.tf-usenote {
  margin: 0;
  flex: none;
}
.tf-tiles {
  display: flex;
  gap: 4px;
}
.tf-tile {
  flex: 1;
  height: 42px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-2);
  cursor: pointer;
  font-size: 12px;
}
.tf-tile:hover:not(:disabled) {
  border-color: var(--color-primary-hover);
}
.tf-tile.start {
  background: color-mix(in srgb, var(--color-primary) 16%, transparent);
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 650;
}
.tf-tile.due {
  background: color-mix(in srgb, var(--color-danger) 13%, transparent);
  border-color: var(--color-danger);
  color: var(--color-danger);
  font-weight: 650;
}
.tf-tile.skip {
  opacity: 0.38;
  text-decoration: line-through;
  cursor: not-allowed;
}
.tf-tile:disabled {
  cursor: not-allowed;
}
.tf-mgrid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
}
.tf-mday {
  height: 26px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
  padding: 0;
}
.tf-mday:hover {
  border-color: var(--color-primary-hover);
}
.tf-mday.start {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
  font-weight: 650;
}
.tf-mday.due {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: #fff;
  font-weight: 650;
}

/* ---- 24h 时间轴 ---- */
.tf-tl {
  position: relative;
  height: 42px;
  flex: none;
  margin: 2px 6px 0;
}
.tf-rail {
  position: absolute;
  left: 0;
  right: 0;
  top: 22px;
  height: 6px;
  border-radius: 99px;
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
}
.tf-tick {
  position: absolute;
  top: 30px;
  transform: translateX(-50%);
  font-size: 9px;
  color: var(--color-text-subdued);
  font-variant-numeric: tabular-nums;
}
.tf-mk {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  background: transparent;
  border: none;
  cursor: grab;
  padding: 0;
}
.tf-mk:active {
  cursor: grabbing;
}
.tf-mk .lab {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.tf-mk .pin {
  width: 11px;
  height: 11px;
  border-radius: 99px;
  border: 2px solid var(--color-surface);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}
.tf-mk.start .lab {
  color: var(--color-primary);
  font-weight: 600;
}
.tf-mk.start .pin {
  background: var(--color-primary);
}
.tf-mk.due .lab {
  color: var(--color-danger);
  font-weight: 600;
}
.tf-mk.due .pin {
  background: var(--color-danger);
}
.tf-mk.due.nopop .pin {
  background: var(--color-surface);
  box-shadow: inset 0 0 0 2px var(--color-danger);
}
.tf-mk.pop .lab {
  color: var(--color-warning);
}
.tf-mk.pop .pin {
  background: var(--color-warning);
}
.tf-mkpop {
  position: absolute;
  z-index: 6;
  top: 36px;
  transform: translateX(-50%);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-md);
  box-shadow: var(--zt-shadow-card);
  padding: 4px 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tf-del {
  border: none;
  background: transparent;
  color: var(--color-danger);
  cursor: pointer;
  font-size: 11px;
  height: 20px;
}

/* ---- 开关行 + 状态句 ---- */
.tf-toggles {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 0;
  flex: none;
}
.tf-tg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--zt-t3);
  color: var(--color-text-2);
  cursor: pointer;
}
.tf-tip {
  cursor: help;
  color: var(--color-text-subdued);
  font-size: 11px;
}
.tf-status {
  margin: 2px 0 0;
  flex: none;
}
.tf-status.warn {
  color: var(--color-warning);
}

/* ---- 详情通栏 ---- */
.tf-detail-rows {
  gap: 4px;
}
.tf-detail-rows .field-line {
  min-height: 28px;
}
.tf-chips {
  flex-wrap: wrap;
  row-gap: 4px;
  max-height: 60px;
  overflow-y: auto;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: var(--color-surface-hover);
  padding: 2px 8px;
  font-size: var(--zt-note);
  color: var(--color-text-2);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip.editable {
  cursor: pointer;
}
.chip.editable:hover {
  border-color: var(--color-primary-hover);
}
.tf-x {
  border: none;
  background: transparent;
  color: var(--color-text-subdued);
  cursor: pointer;
  font-size: 10px;
  padding: 0 2px;
}
.tf-x:hover {
  color: var(--color-danger);
}

/* AI 解析预览 */
.ai-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ai-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.ai-k {
  flex: none;
  width: 64px;
  font-size: 12px;
  color: var(--color-text-3);
}
.ai-v {
  font-size: 13px;
  word-break: break-word;
}
.ai-v.pre {
  white-space: pre-line;
}
.ai-v.strong,
.strong {
  font-weight: 600;
}
.ai-ok {
  color: rgb(var(--success-6));
  font-style: normal;
  font-size: 12px;
  margin-left: 4px;
}
.ai-warn {
  color: rgb(var(--warning-6));
  font-style: normal;
  font-size: 12px;
  margin-left: 4px;
}
.ai-subs {
  margin: 0;
  padding-left: 16px;
  font-size: 13px;
}
.ocr-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-md, 12px);
  cursor: pointer;
  margin-bottom: 8px;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}
.ocr-item:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-glow);
}

/* ---- 图片识别细条（点击/拖拽/粘贴三合一） ---- */
.ocr-thin {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  padding: 5px 12px;
  border: 1.5px dashed var(--color-border);
  border-radius: var(--zt-radius-md, 12px);
  cursor: pointer;
  transition: border-color var(--zt-dur-fast, 120ms) ease,
    background-color var(--zt-dur-fast, 120ms) ease;
}
.ocr-thin:hover {
  border-color: var(--color-primary-hover);
  background: var(--color-surface-hover);
}
.ocr-thin.is-drag {
  border-color: var(--color-primary);
  background: var(--color-surface-hover);
  box-shadow: 0 0 0 1.5px var(--color-primary-glow);
}
.ocr-thin.is-busy {
  cursor: default;
}
.ocr-thin-text {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ocr-thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  flex: none;
  border-radius: var(--zt-radius-md, 12px);
  border: 1px solid var(--color-border);
}
.ocr-file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.ocr-file-name {
  font-size: 12px;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ocr-status {
  font-size: 12px;
  color: var(--color-primary);
  animation: ocr-blink 1.2s ease-in-out infinite;
}
@keyframes ocr-blink {
  50% {
    opacity: 0.45;
  }
}
</style>
