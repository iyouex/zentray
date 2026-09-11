<template>
  <div class="page">
    <div class="page-header">
      <h2>{{ isEdit ? '修改任务' : '新建任务' }}</h2>
    </div>

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
              <a-form-item label="任务详情">
                <a-textarea
                  v-model="form.details"
                  :auto-size="{ minRows: 3, maxRows: 6 }"
                  placeholder="选填"
                />
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
  </div>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import {
  addSecondaryCategory,
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
</style>
