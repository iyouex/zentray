<template>
  <div class="page">
    <div class="page-header">
      <h2>⏰ 任务提醒</h2>
    </div>

    <a-spin :loading="loading" style="width: 100%">
      <template v-if="task">
        <h3 class="task-title">「{{ task.title }}」</h3>
        <p class="meta">
          分类: {{ task.category }}　优先级: {{ task.priority }}　进度:
          {{ task.progress || 0 }}%
        </p>
        <p v-if="task.details" class="details">{{ task.details }}</p>
        <p class="hint">到点提醒 — 请选择操作：</p>
        <a-space wrap size="medium">
          <a-button type="primary" @click="finish('update')">📊 更新状态</a-button>
          <a-button status="success" @click="finish('done')">✅ 完成</a-button>
          <a-button @click="finish('snooze')">😴 忽略 10 分钟</a-button>
          <a-button type="outline" @click="finish('dismiss')">关闭本次</a-button>
        </a-space>
      </template>
      <a-empty v-else description="任务不存在或已完成" />
    </a-spin>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { closeHost, getTask } from '@/api/client'

const route = useRoute()
const loading = ref(true)
const task = ref(null)

function finish(action) {
  closeHost({
    action,
    task_id: route.params.id,
    fire_key: route.query.fire_key || '',
    snooze_minutes: 10,
  })
}

onMounted(async () => {
  try {
    task.value = await getTask(route.params.id)
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.task-title {
  margin: 0 0 8px;
  font-size: 18px;
}
.meta {
  color: var(--color-text-3);
  margin: 0 0 8px;
}
.details {
  margin: 0 0 12px;
  white-space: pre-wrap;
}
.hint {
  margin: 16px 0 12px;
}
</style>
