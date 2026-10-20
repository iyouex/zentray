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

    <div class="page-body">
      <a-spin :loading="loading" style="width: 100%">
        <div class="two-col">
          <section class="zt-block">
            <div class="zt-block-head"><h3 class="zt-h3">基本信息</h3></div>
            <a-form :model="form" layout="vertical">
              <a-form-item v-if="!isEdit || isTemplate" label="任务模式">
                <a-radio-group v-model="form.mode" :disabled="isTemplate">
                  <a-radio value="one-time" :disabled="isTemplate">一次性</a-radio>
                  <a-radio value="periodic">周期</a-radio>
                </a-radio-group>
                <a-select
                  v-if="form.mode === 'periodic'"
                  v-model="form.periodicity"
                  style="width: 140px; margin-left: 12px"
                  :options="periodOpts"
                />
              </a-form-item>

              <a-form-item label="标题" required>
                <a-input
                  v-model="form.title"
                  :max-length="100"
                  show-word-limit
                  placeholder="用一句话描述待办"
                />
              </a-form-item>

              <a-row :gutter="12">
                <a-col :span="12">
                  <a-form-item label="一级分类（仅可选已有）">
                    <a-select
                      v-model="form.category_primary_id"
                      :options="primaryOpts"
                      placeholder="请选择"
                      allow-search
                      @change="onPrimaryChange"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="优先级">
                    <a-select v-model="form.priority" :options="priorityOpts" />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item v-if="secondaryEnabled" label="二级分类">
                <div class="sec-line">
                  <a-select
                    v-model="form.category_secondary_id"
                    allow-clear
                    allow-search
                    :options="secondaryOpts"
                    placeholder="可选"
                    style="flex: 1"
                  />
                  <a-button
                    type="outline"
                    :disabled="!form.category_primary_id"
                    @click="showAddSec = true"
                  >
                    ➕ 添加二级
                  </a-button>
                </div>
              </a-form-item>

              <template v-if="form.mode !== 'periodic'">
                <a-form-item>
                  <a-checkbox v-model="form.auto_abandon_on_overdue">
                    逾期自动废弃
                  </a-checkbox>
                </a-form-item>
              </template>

              <template v-else>
                <a-form-item label="调度间隔">
                  <NumberSpinner v-model="form.interval" :min="1" :max="365" />
                  <span style="margin-left: 8px">{{ intervalUnit }}</span>
                </a-form-item>
                <a-form-item>
                  <a-checkbox v-model="form.long_term">长期有效</a-checkbox>
                  <a-checkbox
                    v-model="form.auto_abandon_on_overdue"
                    style="margin-left: 12px"
                  >
                    逾期废弃
                  </a-checkbox>
                </a-form-item>
                <a-form-item v-if="!form.long_term" label="停止派发日">
                  <a-input v-model="form.schedule_end_date" placeholder="YYYY-MM-DD" />
                </a-form-item>
                <a-form-item label="日历未来日程">
                  <a-checkbox v-model="form.calendar_enabled">
                    生成未来日程到系统日历
                  </a-checkbox>
                </a-form-item>
                <a-form-item v-if="form.calendar_enabled" label="投影范围">
                  <a-space>
                    <a-select v-model="form.calendar_horizon_mode" style="width: 110px" @change="onHorizonModeChange">
                      <a-option value="count">未来几次</a-option>
                      <a-option value="days">未来几天</a-option>
                    </a-select>
                    <NumberSpinner
                      v-model="form.calendar_horizon_value"
                      :min="form.calendar_horizon_mode === 'days' ? 7 : 1"
                      :max="form.calendar_horizon_mode === 'days' ? 365 : 60"
                    />
                    <span>{{ form.calendar_horizon_mode === 'days' ? '天' : '次' }}</span>
                  </a-space>
                  <p class="muted" style="margin: 6px 0 0">
                    需在 设置 → 任务 开启「系统日历」后写入日历源文件；已派发的真实实例不重复投影。
                  </p>
                </a-form-item>
              </template>

              <a-form-item label="关联插件">
                <div class="plugin-row">
                  <a-select
                    v-model="form.plugin_id"
                    allow-clear
                    allow-search
                    :options="pluginOpts"
                    :disabled="!pluginsEnabled"
                    :placeholder="
                      pluginsEnabled
                        ? '可选：关联插件'
                        : '请先在设置中启用「插件」'
                    "
                    style="flex: 1"
                  />
                  <a-button
                    v-if="isEdit && form.plugin_id"
                    type="outline"
                    :loading="runningPlugin"
                    :disabled="!canRunPlugin"
                    @click="onRunPlugin"
                  >
                    ▶ 运行
                  </a-button>
                </div>
                <p v-if="selectedPluginHint" class="muted plugin-hint">
                  {{ selectedPluginHint }}
                </p>
              </a-form-item>
            </a-form>
          </section>

          <section class="zt-block">
            <div class="zt-block-head"><h3 class="zt-h3">⏰ 时间与提醒</h3></div>
            <a-form :model="form" layout="vertical">
              <!-- ① 开始时间：未勾选=创建/派发后立即开始 -->
              <a-form-item>
                <a-checkbox v-model="form.start_enabled" @change="onStartCheck">
                  开始时间
                </a-checkbox>
                <div
                  v-if="form.start_enabled && !isPeriodic"
                  class="slot-row"
                  style="margin-top: 8px"
                >
                  <a-date-picker
                    v-model="form.start_date"
                    style="width: 150px"
                    value-format="YYYY-MM-DD"
                  />
                  <TimeSpinner v-model="form.start_time" />
                </div>
                <!-- 日周期：仅时分 -->
                <div
                  v-else-if="form.start_enabled && form.periodicity === 'daily'"
                  class="slot-row"
                  style="margin-top: 8px"
                >
                  <span class="slot-label">每天</span>
                  <TimeSpinner v-model="form.start_time" />
                </div>
                <!-- 周/月周期：提醒点（周几/几号+时分，可多个） -->
                <div v-else-if="form.start_enabled" class="slots-box" style="margin-top: 8px">
                  <div v-for="(slot, idx) in form.start_slots" :key="idx" class="slot-row">
                    <template v-if="form.periodicity === 'weekly'">
                      <a-select v-model="slot.weekday" size="mini" class="slot-weekday">
                        <a-option v-for="(w, i) in WEEK_LABELS" :key="i" :value="i">
                          {{ w }}
                        </a-option>
                      </a-select>
                    </template>
                    <template v-else>
                      <span class="slot-label">每月</span>
                      <NumberSpinner v-model="slot.day_of_month" :min="1" :max="31" />
                      <span class="slot-hint">日</span>
                    </template>
                    <TimeSpinner v-model="slot.time_of_day" />
                    <a-button size="mini" status="danger" @click="removeSlot(idx)">
                      删
                    </a-button>
                  </div>
                  <a-button size="small" type="outline" @click="addSlot">
                    ➕ 添加提醒点
                  </a-button>
                </div>
                <p v-if="form.start_enabled" class="muted" style="margin: 6px 0 0">
                  到点前不轮播不弹窗；周期内多个提醒点取最早，已过视为立即。
                </p>
              </a-form-item>

              <!-- ② 截止时间：未勾选=无截止、永不逾期 -->
              <a-form-item>
                <a-checkbox v-model="form.has_deadline" @change="onDeadlineCheck">
                  截止时间
                </a-checkbox>
                <div v-if="form.has_deadline" class="slot-row" style="margin-top: 8px">
                  <template v-if="!isPeriodic">
                    <a-date-picker
                      v-model="form.deadline"
                      style="width: 150px"
                      value-format="YYYY-MM-DD"
                    />
                  </template>
                  <template v-else-if="form.periodicity === 'weekly'">
                    <span class="slot-label">每周</span>
                    <a-select v-model="form.deadline_weekday" class="slot-weekday">
                      <a-option v-for="(w, i) in WEEK_LABELS" :key="i" :value="i">
                        {{ w }}
                      </a-option>
                    </a-select>
                  </template>
                  <template v-else-if="form.periodicity === 'monthly'">
                    <span class="slot-label">每月</span>
                    <NumberSpinner v-model="form.deadline_day_of_month" :min="1" :max="31" />
                    <span class="slot-hint">日</span>
                  </template>
                  <template v-else>
                    <span class="slot-label">每天</span>
                  </template>
                  <TimeSpinner v-model="form.due_time" />
                </div>
                <p v-if="form.has_deadline" class="muted" style="margin: 6px 0 0">
                  逾期按截止时分分钟级判定，未设时分按 23:59。
                </p>
              </a-form-item>

              <!-- ③ 弹窗提醒：截止时刻弹一次 + 可另加多个弹窗时间 -->
              <a-form-item>
                <a-checkbox v-model="form.popup_enabled">弹窗提醒</a-checkbox>
                <p v-if="form.popup_enabled" class="muted" style="margin: 6px 0 0">
                  {{
                    form.has_deadline
                      ? '截止时刻自动弹窗一次，改截止即改弹窗时刻；可另加弹窗时间：'
                      : '未设截止时间：仅下方自添的弹窗时间会提醒。'
                  }}
                </p>
                <!-- 存量弹窗时间行即使未勾选也展示（仍会到点弹），可删可改 -->
                <div
                  v-if="!isPeriodic && form.deliveries.length"
                  class="slots-box"
                  style="margin-top: 8px"
                >
                  <div v-for="(d, idx) in form.deliveries" :key="idx" class="slot-row">
                    <a-date-picker
                      v-model="d.date"
                      size="small"
                      style="width: 140px"
                      value-format="YYYY-MM-DD"
                    />
                    <TimeSpinner v-model="d.time" />
                    <a-button size="mini" status="danger" @click="removeDelivery(idx)">
                      删
                    </a-button>
                  </div>
                </div>
                <a-button
                  v-if="form.popup_enabled && !isPeriodic"
                  size="small"
                  type="outline"
                  style="margin-top: 8px"
                  @click="addDelivery"
                >
                  ➕ 添加弹窗时间
                </a-button>
              </a-form-item>

              <!-- ④ 跳过公休日 -->
              <a-form-item>
                <a-checkbox v-model="form.skip_holidays">跳过公休日</a-checkbox>
                <span class="slot-hint">周末与法定节假日整体静默；新建按分类预设带出</span>
              </a-form-item>
            </a-form>
          </section>

          <section class="zt-block">
            <div class="zt-block-head"><h3 class="zt-h3">详情</h3></div>
            <a-form :model="form" layout="vertical">
              <a-form-item v-if="aiOcrOn">
                <div
                  class="ocr-drop"
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
                    <PhCamera :size="22" class="ocr-drop-icon" />
                    <div class="ocr-drop-text">
                      <span>点击选择、拖入或 Ctrl+V 粘贴图片</span>
                      <span class="muted">识别为任务草稿，确认后填入表单（≤9MB）</span>
                    </div>
                  </template>
                  <template v-else>
                    <img class="ocr-thumb" :src="ocrPreview" alt="" />
                    <div class="ocr-file-info">
                      <span class="ocr-file-name">{{ ocrFileName }}</span>
                      <span v-if="aiOcrLoading" class="ocr-status">识别中…</span>
                      <span v-else class="muted">点击可重新选择</span>
                    </div>
                    <a-button
                      v-if="!aiOcrLoading"
                      size="mini"
                      status="danger"
                      @click.stop="clearOcrFile"
                    >
                      移除
                    </a-button>
                  </template>
                </div>
              </a-form-item>
              <a-form-item label="任务详情">
                <a-textarea
                  v-model="form.details"
                  :auto-size="{ minRows: 3, maxRows: 6 }"
                  placeholder="选填"
                />
              </a-form-item>
              <a-form-item :label="isTemplate || form.mode === 'periodic' ? '预设子任务（派发时复制到实例）' : '子任务'">
                <div class="slots-box">
                  <div v-for="(sub, idx) in form.subtasks" :key="idx" class="slot-row">
                    <a-input
                      v-model="sub.title"
                      :max-length="100"
                      placeholder="子任务标题"
                      style="flex: 1"
                    />
                    <a-button size="mini" status="danger" @click="removeSub(idx)">删</a-button>
                  </div>
                  <a-button size="small" type="outline" @click="addSub">➕ 添加子任务</a-button>
                </div>
              </a-form-item>
              <!-- 附件/链接：仅一次性任务（模板无此字段）；详情页缩略/跳转打开 -->
              <a-form-item v-if="!isTemplate && form.mode !== 'periodic'" label="附件 / 链接">
                <div class="slots-box">
                  <div v-for="(a, idx) in form.attachments" :key="idx" class="slot-row">
                    <span class="att-chip" :title="a">{{ attIcon(a) }} {{ attLabel(a) }}</span>
                    <a-button size="mini" status="danger" @click="form.attachments.splice(idx, 1)">删</a-button>
                  </div>
                  <div class="slot-row">
                    <a-button size="small" type="outline" :loading="picking" @click="addAttachmentFile">
                      📎 添加文件
                    </a-button>
                    <a-input-search
                      v-model="newLink"
                      size="small"
                      placeholder="粘贴 https:// 链接，回车添加"
                      style="flex: 1"
                      search-button
                      @search="addAttachmentLink"
                    />
                  </div>
                </div>
              </a-form-item>
            </a-form>
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
        <p class="muted" style="margin-top: 8px">
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
      <p class="muted">选择一条填入表单：</p>
      <div v-for="(d, i) in ocrDrafts" :key="i" class="ocr-item" @click="chooseOcrDraft(d)">
        <span class="strong">{{ d.title }}</span>
        <span class="muted">{{ [d.category, PRI_LABEL[d.priority], d.deadline].filter(Boolean).join(' · ') }}</span>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
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
  calendar_enabled: false,
  calendar_horizon_mode: 'count',
  calendar_horizon_value: 4,
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
// 周几下拉文案（存储值 0=周一 … 6=周日，与后端 wd 表一致）
const WEEK_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
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

/** 投影范围模式切换时回填该模式默认值（count=4 次 / days=30 天） */
function onHorizonModeChange(mode) {
  form.calendar_horizon_value = mode === 'days' ? 30 : 4
}

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

/** 勾选「开始时间」瞬间预填默认值：一次性=当天；日=仅时分；周=周一；月=1 号 */
function onStartCheck(checked) {
  if (!checked) return
  const w = winTimes()
  form.start_time = w.start
  if (!isPeriodic.value) {
    if (!form.start_date) form.start_date = todayStr()
  } else if (isWeeklyOrMonthly.value && !form.start_slots.length) {
    addSlot(w.start)
  }
}

/** 勾选「截止时间」瞬间预填：一次性=当天；周=周日；月=31 号；时分=窗口终点 */
function onDeadlineCheck(checked) {
  if (!checked) return
  form.due_time = winTimes().end
  if (!isPeriodic.value) {
    if (!form.deadline) form.deadline = todayStr()
  }
}

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

/** 新建时按一级分类预设带出「跳过公休日」；编辑不动已有值 */
function seedSkipHolidays() {
  if (isEdit.value) return
  const p = (meta.value?.categories?.primary_list || []).find(
    (x) => x.id === form.category_primary_id,
  )
  form.skip_holidays = !!(p && p.skip_holidays)
}

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

onMounted(() => window.addEventListener('paste', onPaste))
onUnmounted(() => {
  window.removeEventListener('paste', onPaste)
  clearOcrFile()
})

function primaryName() {
  const o = primaryOpts.value.find((x) => x.value === form.category_primary_id)
  return o?.label || '工作'
}

function addSlot(time = '09:00') {
  if (form.periodicity === 'weekly') {
    form.start_slots.push({ weekday: 0, day_of_month: null, time_of_day: time })
  } else {
    form.start_slots.push({ weekday: null, day_of_month: 1, time_of_day: time })
  }
}

function removeSlot(idx) {
  form.start_slots.splice(idx, 1)
}

function addDelivery() {
  form.deliveries.push({
    date: (form.has_deadline && form.deadline) || todayStr(),
    time: form.due_time || '23:59',
    notify: true,
  })
}

function removeDelivery(idx) {
  form.deliveries.splice(idx, 1)
}

function addSub() {
  form.subtasks.push({ id: null, title: '', status: 'active' })
}

function removeSub(idx) {
  form.subtasks.splice(idx, 1)
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

/** 编辑回填：旧任务/模板的旧弹窗提醒槽兼容展示（模板→开始提醒点） */
function loadStartSlots(rawSlots, fallbackTime) {
  form.start_slots = (rawSlots || []).map((s) => ({
    weekday: s.weekday != null ? Number(s.weekday) : 0,
    day_of_month: s.day_of_month != null ? Number(s.day_of_month) : 1,
    time_of_day: s.time_of_day || fallbackTime || '09:00',
  }))
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
    // 日模板：仅时分单 slot；周/月：周几/几号 + 时分（可多个）
    const slots = !form.start_enabled
      ? []
      : isWeeklyOrMonthly.value
        ? (form.start_slots || []).map((s) => {
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
      calendar_enabled: form.calendar_enabled,
      calendar_horizon_mode: form.calendar_horizon_mode || 'count',
      calendar_horizon_value: form.calendar_horizon_value || 4,
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

// ---- 弹窗提醒同时刻参考：随旧弹窗提醒 UI 移除（交付点弹窗无同时刻聚合需求）----

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
        form.periodicity = t.periodicity || 'daily'
        form.interval = t.interval || 1
        form.long_term = t.long_term !== false
        form.schedule_end_date = t.schedule_end_date || ''
        form.calendar_enabled = !!t.calendar_enabled
        form.calendar_horizon_mode = t.calendar_horizon_mode || 'count'
        form.calendar_horizon_value = t.calendar_horizon_value || 4
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
        // 兼容旧模板：无开始提醒点时把旧弹窗提醒槽展示为开始提醒点
        const slots =
          (t.remind_start_slots?.length ? t.remind_start_slots : t.reminder?.slots) || []
        form.start_enabled = slots.length > 0
        if (form.periodicity === 'daily') {
          form.start_time = slots[0]?.time_of_day || winTimes().start
        } else {
          loadStartSlots(slots, t.reminder?.time_of_day)
        }
      } else {
        const t = await getTask(taskId.value)
        form.title = t.title
        form.priority = t.priority || 'medium'
        form.details = t.details || ''
        form.category_primary_id = t.category_primary_id
        form.category_secondary_id = t.category_secondary_id
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
    loadPlugins()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.plugin-row {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}
.plugin-hint {
  margin: 6px 0 0;
}
.sec-line {
  display: flex;
  gap: 8px;
  align-items: center;
}
.slots-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.slot-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.att-chip {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--color-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slot-label {
  font-size: 13px;
  color: var(--color-text-2);
}
.slot-hint {
  font-size: 12px;
  color: var(--color-text-3);
}
.slot-weekday {
  width: 96px;
}
.muted {
  color: var(--color-text-3);
  font-size: 12px;
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
.ai-v.strong {
  font-weight: 600;
}
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
  border-radius: var(--zt-radius-card, 12px);
  cursor: pointer;
  margin-bottom: 8px;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}
.ocr-item:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-glow);
}

/* ---- 图片识别上传区（点击/拖拽/粘贴三合一） ---- */
.ocr-drop {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1.5px dashed var(--color-border);
  border-radius: var(--zt-radius-md, 12px);
  cursor: pointer;
  transition: border-color var(--zt-dur-fast, 120ms) ease,
    background-color var(--zt-dur-fast, 120ms) ease,
    box-shadow var(--zt-dur-fast, 120ms) ease;
}
.ocr-drop:hover {
  border-color: var(--color-primary-hover);
  background: var(--color-surface-hover);
}
.ocr-drop.is-drag {
  border-color: var(--color-primary);
  background: var(--color-surface-hover);
  box-shadow: 0 0 0 1.5px var(--color-primary-glow);
}
.ocr-drop.is-drag > * {
  pointer-events: none;
}
.ocr-drop.is-busy {
  cursor: default;
}
.ocr-drop-icon {
  color: var(--color-text-subdued);
  flex: none;
}
.ocr-drop-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: var(--color-text-primary);
}
.ocr-thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  flex: none;
  border-radius: var(--zt-radius-md, 12px);
  border: 1px solid var(--color-border);
}
.ocr-file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.ocr-file-name {
  font-size: 13px;
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
