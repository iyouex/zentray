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
          <a-card title="基本信息" :bordered="false">
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
                  <a-checkbox v-model="form.has_deadline">设置截止日期</a-checkbox>
                  <a-checkbox
                    v-model="form.auto_abandon_on_overdue"
                    style="margin-left: 12px"
                  >
                    逾期自动废弃
                  </a-checkbox>
                </a-form-item>
                <a-form-item v-if="form.has_deadline" label="截止日期">
                  <a-date-picker
                    v-model="form.deadline"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
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
              </template>
            </a-form>
          </a-card>

          <a-card title="详情与提醒" :bordered="false">
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
              <a-form-item>
                <a-checkbox v-model="form.reminder_enabled">弹窗提醒</a-checkbox>
              </a-form-item>

              <!-- 日/一次性：默认时间 -->
              <a-form-item
                v-if="form.reminder_enabled && !isWeeklyOrMonthly"
                label="提醒时间"
              >
                <TimeSpinner v-model="form.reminder_time" />
              </a-form-item>

              <!-- 周/月：多提醒点 -->
              <template v-if="form.reminder_enabled && isWeeklyOrMonthly">
                <a-form-item :label="form.periodicity === 'weekly' ? '提醒点（周几 + 时间）' : '提醒点（日期 + 时间）'">
                  <div class="slots-box">
                    <div v-for="(slot, idx) in form.reminder_slots" :key="idx" class="slot-row">
                      <template v-if="form.periodicity === 'weekly'">
                        <span class="slot-label">周</span>
                        <NumberSpinner
                          v-model="slot.weekday"
                          :min="0"
                          :max="6"
                        />
                        <span class="slot-hint">0=一 … 6=日</span>
                      </template>
                      <template v-else>
                        <span class="slot-label">每月</span>
                        <NumberSpinner
                          v-model="slot.day_of_month"
                          :min="1"
                          :max="31"
                        />
                        <span class="slot-hint">日</span>
                      </template>
                      <TimeSpinner v-model="slot.time_of_day" />
                      <a-button
                        size="mini"
                        status="danger"
                        @click="removeSlot(idx)"
                      >
                        删
                      </a-button>
                    </div>
                    <a-button size="small" type="outline" @click="addSlot">
                      ➕ 添加提醒点
                    </a-button>
                  </div>
                </a-form-item>
              </template>
            </a-form>
          </a-card>
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
import { computed, h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { PhCamera, PhSparkle } from '@phosphor-icons/vue'
import {
  addSecondaryCategory,
  aiOcr,
  aiParse,
  cancelHost,
  checkReminderConflicts,
  closeHost,
  createTask,
  createTemplate,
  getMeta,
  getTask,
  getTemplate,
  updateTask,
  updateTemplate,
} from '@/api/client'
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

const form = reactive({
  mode: 'one-time',
  title: '',
  category_primary_id: null,
  category_secondary_id: null,
  priority: 'medium',
  has_deadline: true,
  deadline: '',
  details: '',
  auto_abandon_on_overdue: false,
  periodicity: 'daily',
  interval: 1,
  long_term: true,
  schedule_end_date: '',
  reminder_enabled: false,
  reminder_time: '17:00',
  reminder_slots: [],
  subtasks: [],
  task_type: 'one-time',
  template_id: null,
})

const periodOpts = [
  { label: '每天', value: 'daily' },
  { label: '每周', value: 'weekly' },
  { label: '每月', value: 'monthly' },
]
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

function onPrimaryChange() {
  form.category_secondary_id = null
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
  if (d.reminder_time) {
    form.reminder_enabled = true
    form.reminder_time = d.reminder_time
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

function addSlot() {
  if (form.periodicity === 'weekly') {
    form.reminder_slots.push({ weekday: 0, time_of_day: '17:00' })
  } else {
    form.reminder_slots.push({ day_of_month: 1, time_of_day: '17:00' })
  }
}

function removeSlot(idx) {
  form.reminder_slots.splice(idx, 1)
}

function addSub() {
  form.subtasks.push({ id: null, title: '', status: 'active' })
}

function removeSub(idx) {
  form.subtasks.splice(idx, 1)
}

function loadReminder(rem) {
  if (!rem?.enabled) {
    form.reminder_enabled = false
    form.reminder_slots = []
    form.reminder_time = '17:00'
    return
  }
  form.reminder_enabled = true
  form.reminder_time = rem.time_of_day || '17:00'
  const slots = rem.slots || []
  if (slots.length) {
    form.reminder_slots = slots.map((s) => ({
      weekday: s.weekday != null ? Number(s.weekday) : 0,
      day_of_month: s.day_of_month != null ? Number(s.day_of_month) : 1,
      time_of_day: s.time_of_day || rem.time_of_day || '17:00',
    }))
  } else {
    form.reminder_slots = []
  }
}

function buildReminder() {
  if (!form.reminder_enabled) {
    return { enabled: false, time_of_day: '17:00', slots: [] }
  }
  if (isWeeklyOrMonthly.value) {
    const slots = (form.reminder_slots || []).map((s) => {
      if (form.periodicity === 'weekly') {
        return {
          time_of_day: s.time_of_day || '17:00',
          weekday: Math.max(0, Math.min(6, Number(s.weekday) || 0)),
          day_of_month: null,
        }
      }
      return {
        time_of_day: s.time_of_day || '17:00',
        weekday: null,
        day_of_month: Math.max(1, Math.min(31, Number(s.day_of_month) || 1)),
      }
    })
    const first = slots[0]?.time_of_day || form.reminder_time || '17:00'
    return { enabled: true, time_of_day: first, slots }
  }
  return {
    enabled: true,
    time_of_day: form.reminder_time || '17:00',
    slots: [],
  }
}

function buildPayload() {
  const reminder = buildReminder()
  const base = {
    title: form.title.trim(),
    category: primaryName(),
    category_primary_id: form.category_primary_id,
    category_secondary_id: form.category_secondary_id,
    priority: form.priority,
    details: form.details || '',
    reminder,
    auto_abandon_on_overdue: form.auto_abandon_on_overdue,
    attachments: [],
    subtasks: (form.subtasks || [])
      .filter((s) => (s.title || '').trim())
      .map((s) => ({ id: s.id, title: s.title.trim(), status: s.status || 'active' })),
  }

  if (form.mode === 'periodic' || isTemplate.value) {
    return {
      ...base,
      task_type: 'periodic',
      periodicity: form.periodicity,
      interval: form.interval || 1,
      long_term: form.long_term,
      schedule_end_date: form.long_term ? null : form.schedule_end_date || null,
    }
  }

  return {
    ...base,
    task_type: form.task_type || 'one-time',
    template_id: form.template_id,
    deadline: form.has_deadline ? form.deadline || '' : '',
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

function formatConflictList(conflicts) {
  if (!conflicts?.length) return ''
  return conflicts
    .map((c, i) => {
      const kindLabel =
        {
          task: '任务',
          template: '周期模板',
          ai_plan: 'AI 计划',
          ai_review: 'AI 复盘',
        }[c.kind] || c.kind
      return `${i + 1}. [${kindLabel}] ${c.title} — ${c.detail || c.time}`
    })
    .join('\n')
}

/**
 * 弹窗提醒开启时检查与其它任务/模板/计划复盘调度是否同钟点冲突。
 * 有冲突则弹确认；用户确认后继续保存。
 */
async function confirmReminderConflictsIfNeeded(payload) {
  const rem = payload?.reminder
  if (!rem?.enabled) return true
  try {
    const body = {
      reminder: rem,
      exclude_task_id:
        isEdit.value && !isTemplate.value ? taskId.value : undefined,
      exclude_template_id:
        isEdit.value && isTemplate.value ? taskId.value : undefined,
    }
    const data = await checkReminderConflicts(body)
    if (!data?.has_conflict || !data.conflicts?.length) return true
    const list = formatConflictList(data.conflicts)
    return await new Promise((resolve) => {
      Modal.confirm({
        draggable: true,
        title: '提醒时间冲突',
        content: () =>
          h(
            'div',
            {
              style: {
                whiteSpace: 'pre-line',
                maxHeight: '260px',
                overflow: 'auto',
                fontSize: '13px',
                lineHeight: '1.5',
              },
            },
            `以下已有弹窗/调度与当前提醒时间冲突：\n\n${list}\n\n仍要保存吗？`,
          ),
        okText: '仍要保存',
        cancelText: '返回修改',
        simple: false,
        width: 480,
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  } catch (e) {
    Message.warning(e?.message || '冲突检查失败，将直接保存')
    return true
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
  if (
    form.reminder_enabled &&
    isWeeklyOrMonthly.value &&
    !(form.reminder_slots || []).length
  ) {
    Message.warning('请至少添加一个提醒点')
    return
  }
  const payload = buildPayload()
  const ok = await confirmReminderConflictsIfNeeded(payload)
  if (!ok) return

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
    if (!form.deadline) {
      const d = new Date()
      d.setDate(d.getDate() + 1)
      form.deadline = d.toISOString().slice(0, 10)
    }
    if (route.query.mode === 'periodic') {
      form.mode = 'periodic'
    }
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
        form.auto_abandon_on_overdue = !!t.auto_abandon_on_overdue
        form.subtasks = (t.subtasks || []).map((s) => ({ ...s }))
        loadReminder(t.reminder)
      } else {
        const t = await getTask(taskId.value)
        form.title = t.title
        form.priority = t.priority || 'medium'
        form.details = t.details || ''
        form.category_primary_id = t.category_primary_id
        form.category_secondary_id = t.category_secondary_id
        form.has_deadline = Boolean(t.deadline)
        form.deadline = t.deadline || form.deadline
        form.auto_abandon_on_overdue = !!t.auto_abandon_on_overdue
        form.task_type = t.task_type || 'one-time'
        form.template_id = t.template_id
        form.mode = 'one-time'
        form.subtasks = (t.subtasks || []).map((s) => ({ ...s }))
        loadReminder(t.reminder)
      }
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
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
.slot-label {
  font-size: 13px;
  color: var(--color-text-2);
}
.slot-hint {
  font-size: 12px;
  color: var(--color-text-3);
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
