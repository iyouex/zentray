<template>
  <div class="quick-add-page" data-drag="true">
    <div class="quick-add-box" ref="boxRef">
      <div class="qa-row">
        <a-input
          ref="inputRef"
          v-model="title"
          size="large"
          allow-clear
          placeholder="⚡ 闪电录入待办，按回车立即入库（ESC 取消）"
          @press-enter="onEnter"
          @keydown.esc="onEsc"
        />
        <div class="qa-actions">
          <a-button
            v-if="aiOn"
            class="qa-ai-btn"
            size="small"
            :loading="aiLoading"
            aria-label="AI 智能解析"
            title="AI 智能解析：自动补分类/优先级/截止/子任务"
            @click="onAiParse"
          >
            <template #icon><PhSparkle :size="16" /></template>
          </a-button>
          <a-button
            class="qa-new-btn"
            size="small"
            aria-label="新建任务"
            title="新建任务：打开完整表单（分类/提醒/子任务/附件）"
            @click="onNewTask"
          >
            <template #icon><PhPlus :size="16" /></template>
          </a-button>
        </div>
      </div>

      <!-- AI 解析预览：字段 chips + 子任务，确认后带完整字段入库 -->
      <div v-if="aiDraft" class="qa-preview">
        <p class="qa-preview-title">{{ aiDraft.title }}</p>
        <div class="qa-chips">
          <span v-if="aiDraft.category" class="qa-chip">分类 · {{ aiDraft.category }}</span>
          <span class="qa-chip">优先级 · {{ PRI_LABEL[aiDraft.priority] || '中' }}</span>
          <span v-if="aiDraft.deadline" class="qa-chip">截止 · {{ aiDraft.deadline }}</span>
          <span v-if="aiDraft.reminder_time" class="qa-chip">提醒 · {{ aiDraft.reminder_time }}</span>
          <span v-if="aiDraft.subtasks?.length" class="qa-chip">子任务 × {{ aiDraft.subtasks.length }}</span>
        </div>
        <ul v-if="aiDraft.subtasks?.length" class="qa-subs">
          <li v-for="s in aiDraft.subtasks.slice(0, 4)" :key="s">{{ s }}</li>
          <li v-if="aiDraft.subtasks.length > 4" class="qa-more">…共 {{ aiDraft.subtasks.length }} 条</li>
        </ul>
        <p v-if="aiDraft.details" class="qa-details">{{ aiDraft.details }}</p>
        <div class="qa-preview-actions">
          <a-button type="primary" status="success" @click="confirmAi">确认添加</a-button>
          <a-button type="secondary" @click="resetAi">重新输入</a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { PhPlus, PhSparkle } from '@phosphor-icons/vue'
import {
  aiParse,
  cancelHost,
  closeHost,
  createTask,
  getMeta,
  reportHostHeight,
} from '@/api/client'
import { gsap, EASE, motionOff, isReduced } from '@/motion'

const title = ref('')
const inputRef = ref(null)
const defaults = ref({ category: '工作', priority: 'medium' })
const aiOn = ref(false)
const aiLoading = ref(false)
const aiDraft = ref(null)

const PRI_LABEL = { high: '高', medium: '中', low: '低' }

/** 回车阶梯：预览开着 = 确认预览；否则走原有闪电直入库（肌肉记忆不变） */
function onEnter() {
  if (aiDraft.value) {
    confirmAi()
    return
  }
  onSave()
}

/** ESC 阶梯：先收预览，再关窗 */
function onEsc() {
  if (aiDraft.value) {
    resetAi()
    return
  }
  onCancel()
}

async function onSave() {
  const t = title.value.trim()
  if (!t) {
    onCancel()
    return
  }
  try {
    await createTask({
      title: t,
      category: defaults.value.category || '工作',
      priority: defaults.value.priority || 'medium',
    })
    closeHost({ action: 'added' })
  } catch (e) {
    Message.error(e?.message || '添加失败')
  }
}

async function onAiParse() {
  const t = title.value.trim()
  if (!t) {
    Message.warning('先输入内容，再让 AI 解析')
    return
  }
  aiLoading.value = true
  try {
    aiDraft.value = await aiParse(t)
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || 'AI 解析失败')
  } finally {
    aiLoading.value = false
  }
}

function resetAi() {
  aiDraft.value = null
  inputRef.value?.focus?.()
}

/** 草稿 → 完整任务：分类缺省回落 quick_add 默认；提醒时间转 reminder 结构 */
async function confirmAi() {
  const d = aiDraft.value
  if (!d) return
  try {
    await createTask({
      title: d.title || title.value.trim(),
      category: d.category || defaults.value.category || '工作',
      priority: d.priority || defaults.value.priority || 'medium',
      deadline: d.deadline || undefined,
      details: d.details || undefined,
      subtasks: d.subtasks?.length ? d.subtasks : undefined,
      reminder: d.reminder_time ? { enabled: true, time_of_day: d.reminder_time } : undefined,
    })
    closeHost({ action: 'added', ai: true })
  } catch (e) {
    Message.error(e?.message || '添加失败')
  }
}

function onCancel() {
  cancelHost()
}

/** 跳转完整表单：关浮层，宿主链式开 /tasks/new（同 Glance→quick_add 范式） */
function onNewTask() {
  closeHost({ action: 'open_new_task' })
}

onMounted(async () => {
  try {
    const meta = await getMeta()
    if (meta?.quick_add) {
      defaults.value.category = meta.quick_add.default_category || '工作'
      defaults.value.priority = meta.quick_add.default_priority || 'medium'
    }
    aiOn.value = !!meta?.ai_features?.smart_parse
  } catch (_) {}
  await nextTick()
  inputRef.value?.focus?.()
})

/** 窗口高度随内容自适应：AI 预览展开/收起时上报内容高度，宿主同步调窗。
 * 不取 doc scrollHeight——它含视口高度，窗口调大后会自我放大到顶；
 * 盒高（offsetHeight，不受 gsap 缩放影响）+页面内边距与视口无关，收展皆可回落 */
let lastReportedH = 0
const resizeObserver = new ResizeObserver(() => {
  const box = boxRef.value
  if (!box) return
  const cs = getComputedStyle(box.parentElement)
  const h = Math.ceil(box.offsetHeight + parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom))
  if (h > 0 && h !== lastReportedH) {
    lastReportedH = h
    reportHostHeight(h)
  }
})
onMounted(() => {
  if (boxRef.value) resizeObserver.observe(boxRef.value)
})
onBeforeUnmount(() => resizeObserver.disconnect())

/** ESC 兜底：焦点不在输入框时（如刚点过 AI 按钮）@keydown.esc 收不到，
 * 窗口级监听走同一阶梯；目标是自己输入框则让组件处理器独占，避免双触发破阶梯 */
function onGlobalKeydown(e) {
  if (e.key !== 'Escape') return
  const inp = inputRef.value?.$el?.querySelector('input')
  if (e.target === inp) return
  onEsc()
}
onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown))

/** 聚焦弹性绽放（spec §3.5）：聚焦时输入盒轻微放大，失焦回落；亮环仍由 CSS :focus-within 负责 */
const boxRef = ref(null)
onMounted(() => {
  const box = boxRef.value
  const input = inputRef.value?.$el?.querySelector('input') || inputRef.value?.$el
  input?.addEventListener('focus', () => {
    if (motionOff() || isReduced()) return
    gsap.to(box, { scale: 1.012, duration: 0.3, ease: EASE.spring, overwrite: 'auto' })
  })
  input?.addEventListener('blur', () => {
    if (motionOff() || isReduced()) return
    gsap.to(box, { scale: 1, duration: 0.28, ease: EASE.out, overwrite: 'auto' })
  })
})
</script>

<style scoped>
.qa-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
/* 按钮栈与输入框并排；两钮均 small 防栈高撑爆紧凑行 */
.qa-actions {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.qa-preview {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-card, 12px);
  background: var(--color-fill-1, rgba(148, 163, 184, 0.08));
}
.qa-preview-title {
  margin: 0 0 8px;
  font-weight: 600;
  font-size: 14px;
}
.qa-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.qa-chip {
  font-size: 12px;
  color: var(--color-text-2);
  border: 1px solid var(--color-border-2);
  border-radius: var(--zt-radius-pill, 999px);
  padding: 2px 10px;
}
.qa-subs {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--color-text-3);
}
.qa-more {
  list-style: none;
}
.qa-details {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--color-text-3);
  white-space: pre-line;
}
.qa-preview-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
