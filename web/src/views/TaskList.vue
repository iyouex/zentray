<template>
  <div class="page">
    <div class="page-header">
      <h2>任务列表</h2>
      <a-space>
        <a-button type="primary" @click="$router.push({ path: '/tasks/new', query: { from: 'list' } })">
          <template #icon><PhPlus :size="16" /></template>
          新建
        </a-button>
        <a-button @click="$router.push({ path: '/periodic', query: { from: 'list' } })">
          <template #icon><PhRepeat :size="16" /></template>
          周期任务
        </a-button>
        <a-button type="secondary" @click="cancelHost" aria-label="关闭窗口">
          <template #icon><PhX :size="16" /></template>
          关闭
        </a-button>
      </a-space>
    </div>

    <div class="two-col">
      <a-card title="活跃任务" :bordered="true">
        <a-spin :loading="loading" style="width: 100%">
          <div v-if="tasks.length" class="task-card-list">
            <div
              v-for="item in tasks"
              :key="item.id"
              class="task-card-item"
              :class="{ active: item.id === selectedId }"
              @click="selectedId = item.id"
            >
              <div class="task-card-main">
                <span class="task-card-title">{{ item.title }}</span>
                <div class="task-card-meta">
                  <a-tag size="small" color="arcoblue" v-if="item.category">{{ item.category }}</a-tag>
                  <span class="task-card-sub">优先级: {{ item.priority }} · 进度: {{ item.progress || 0 }}%</span>
                </div>
              </div>
              <PhCheckCircle
                v-if="item.progress === 100"
                class="icon-check-animated"
                :size="22"
                weight="fill"
              />
            </div>
          </div>
          <a-empty v-else-if="!loading" description="暂无活跃任务" />
        </a-spin>
      </a-card>

      <a-card title="任务详情与操作" :bordered="true">
        <template v-if="current">
          <p class="title">{{ current.title }}</p>
          <p class="meta">
            分类: {{ current.category }}　优先级: {{ current.priority }}　进度: {{ current.progress || 0 }}%
            <br v-if="current.deadline" />
            <span v-if="current.deadline">截止: {{ current.deadline }}</span>
          </p>
          <a-space direction="vertical" fill style="width: 100%">
            <a-button long type="outline" @click="onSelect">
              <template #icon><PhArrowsCounterClockwise :size="16" /></template>
              切换到此任务
            </a-button>
            <a-button long type="outline" @click="goProgress">
              <template #icon><PhPencil :size="16" /></template>
              更新进度
            </a-button>
            <a-button long type="outline" @click="goEdit">
              <template #icon><PhPencil :size="16" /></template>
              编辑查看
            </a-button>
            <a-space fill style="width: 100%">
              <a-button type="primary" status="success" style="flex: 1" @click="onDone">
                <template #icon><PhCheck :size="16" /></template>
                完成
              </a-button>
              <a-button status="danger" style="flex: 1" @click="onAbandon">
                <template #icon><PhTrash :size="16" /></template>
                废弃
              </a-button>
            </a-space>
          </a-space>
        </template>
        <a-empty v-else description="请选择左侧任务" />
      </a-card>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { PhPlus, PhRepeat, PhX, PhArrowsCounterClockwise, PhPencil, PhCheck, PhTrash, PhCheckCircle } from '@phosphor-icons/vue'
import {
  abandonTask,
  cancelHost,
  closeHost,
  listTasks,
  markDone,
  selectTask,
} from '@/api/client'

const route = useRoute()
const router = useRouter()
const loading = ref(false)

watch(() => route.path, (newPath) => {
  if (newPath === '/tasks') {
    reload()
  }
})
const tasks = ref([])
const selectedId = ref(null)

const current = computed(() => tasks.value.find((t) => t.id === selectedId.value) || null)

async function reload() {
  loading.value = true
  try {
    tasks.value = await listTasks()
    if (!selectedId.value && tasks.value.length) {
      selectedId.value = tasks.value[0].id
    }
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onSelect() {
  if (!current.value) return
  await selectTask(current.value.id)
  Message.success('已切换')
  closeHost({ action: 'select', id: current.value.id })
}

function goProgress() {
  if (!current.value) return
  router.push({ path: `/tasks/${current.value.id}/progress`, query: { from: 'list' } })
}

function goEdit() {
  if (!current.value) return
  router.push({ path: `/tasks/${current.value.id}/edit`, query: { from: 'list' } })
}

async function onDone() {
  if (!current.value) return
  await markDone(current.value.id)
  Message.success('已完成')
  closeHost({ action: 'done', id: current.value.id })
}

function onAbandon() {
  if (!current.value) return
  Modal.confirm({
    draggable: true,
    title: '确认废弃',
    content: `确定废弃「${current.value.title}」？`,
    onOk: async () => {
      await abandonTask(current.value.id)
      Message.success('已废弃')
      closeHost({ action: 'abandon', id: current.value.id })
    },
  })
}

onMounted(reload)
</script>

<style scoped>
.task-card-list {
  display: flex;
  flex-direction: column;
}
.task-card-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.task-card-title {
  font-weight: 600;
  font-size: 14px;
}
.task-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
.task-card-sub {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
}
.task-card-item.active {
  border-color: var(--color-primary, #0d9488);
  background: var(--color-surface-hover, rgba(20, 184, 166, 0.08));
}
.title {
  font-weight: 600;
  font-size: 16px;
  margin: 0 0 8px;
}
.meta {
  color: var(--color-text-muted, #94a3b8);
  font-size: 13px;
  margin: 0 0 16px;
}
</style>
