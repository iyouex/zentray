<template>
  <div class="page progress-page">
    <div class="page-header">
      <h2>📊 更新进度</h2>
    </div>

    <div class="page-body progress-body">
      <a-spin :loading="loading" style="width: 100%">
        <div v-if="task" class="task-title">{{ task.title }}</div>

        <div class="pct-row">
          <span class="pct-label">{{ percent }}%</span>
          <a-slider
            class="theme-slider"
            v-model="percent"
            :min="0"
            :max="100"
            :step="10"
            :style="{ flex: 1 }"
          />
        </div>

        <a-input
          v-model="note"
          placeholder="本次进展描述（选填）"
          allow-clear
          style="margin: 10px 0 12px"
        />

        <div class="action-row">
          <a-button type="primary" status="success" size="small" @click="onDone">完成</a-button>
          <a-button status="danger" size="small" @click="onAbandon">废弃</a-button>
        </div>

        <div v-if="logs.length" class="recent">
          <div class="recent-head">最近进展</div>
          <div v-for="(log, i) in recentLogs" :key="i" class="recent-item">
            <span>{{ log.percent }}%</span>
            <span class="note">{{ formatTime(log.time) }} · {{ log.note || '无备注' }}</span>
          </div>
        </div>
      </a-spin>
    </div>

    <div class="page-footer">
      <a-button @click="onCancel">取消</a-button>
      <a-button type="primary" :loading="saving" @click="onSave">💾 保存</a-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import {
  abandonTask,
  cancelHost,
  closeHost,
  getTask,
  markDone,
  updateProgress,
} from '@/api/client'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()

function handleExit(payload = {}) {
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
const taskId = computed(() => props.id || route.params.id)

const loading = ref(false)
const saving = ref(false)
const task = ref(null)
const percent = ref(0)
const note = ref('')

const logs = computed(() => task.value?.progress_logs || [])
const recentLogs = computed(() => [...logs.value].slice(-4).reverse())

function snap10(v) {
  const n = Math.max(0, Math.min(100, Number(v) || 0))
  return Math.round(n / 10) * 10
}

function formatTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 19)
}

async function onSave() {
  saving.value = true
  try {
    await updateProgress(taskId.value, snap10(percent.value), note.value)
    Message.success('已保存')
    handleExit({ action: 'progress', percent: snap10(percent.value) })
  } catch (e) {
    Message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDone() {
  await markDone(taskId.value)
  Message.success('已完成')
  handleExit({ action: 'done' })
}

function onAbandon() {
  Modal.confirm({
    draggable: true,
    title: '确认废弃',
    content: '确定废弃此任务？',
    onOk: async () => {
      await abandonTask(taskId.value)
      handleExit({ action: 'abandon' })
    },
  })
}

onMounted(async () => {
  loading.value = true
  try {
    task.value = await getTask(taskId.value)
    percent.value = snap10(task.value?.progress || 0)
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
/* 精简布局：禁止出现横向/纵向滚动条 */
.progress-page {
  overflow: hidden;
  height: 100%;
}
.progress-body {
  overflow: hidden !important;
  padding-bottom: 0 !important;
}
.progress-page,
.progress-body {
  scrollbar-width: none;
}
.progress-page::-webkit-scrollbar,
.progress-body::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}
.task-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.3;
  margin: 0 0 10px;
  color: var(--color-text-1);
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.pct-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pct-label {
  font-size: 22px;
  font-weight: 700;
  min-width: 56px;
  color: rgb(var(--primary-6));
}
.action-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.recent-head {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 6px;
}
.recent-item {
  display: flex;
  gap: 10px;
  font-size: 12px;
  padding: 3px 0;
  border-top: 1px solid var(--color-border-2);
}
.note {
  color: var(--color-text-3);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.theme-slider :deep(.arco-slider-bar) {
  background: rgb(var(--primary-6));
}
.theme-slider :deep(.arco-slider-btn::after) {
  border-color: rgb(var(--primary-6));
}
</style>
