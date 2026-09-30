<template>
  <a-drawer
    :visible="visible"
    :width="520"
    unmount-on-close
    :footer="false"
    @cancel="$emit('update:visible', false)"
  >
    <template #title>
      📖 {{ p?.name }} · 使用说明
    </template>
    <div v-if="p" class="pdd">
      <p v-if="p.description" class="pdd-desc">{{ p.description }}</p>
      <a-descriptions :column="2" size="small" bordered class="pdd-meta">
        <a-descriptions-item label="类型">
          <a-tag size="small" :color="p.type === 'service' ? 'orangered' : 'green'">
            {{ p.type === 'service' ? '服务' : '脚本' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="版本">v{{ p.version }}</a-descriptions-item>
        <a-descriptions-item v-if="p.category" label="分类">{{ p.category }}</a-descriptions-item>
        <a-descriptions-item label="入口"><code>{{ p.entry }}</code></a-descriptions-item>
        <a-descriptions-item v-if="p.updated_at" label="更新时间" :span="2">
          {{ p.updated_at.replace('T', ' ') }}
        </a-descriptions-item>
        <a-descriptions-item v-if="trigText" label="自动触发" :span="2">{{ trigText }}</a-descriptions-item>
      </a-descriptions>

      <div v-if="p.params?.length" class="pdd-sec">
        <div class="pdd-k">参数</div>
        <table class="pdd-table">
          <tr v-for="prm in p.params" :key="prm.name">
            <td><code>{{ prm.name }}</code></td>
            <td>{{ prm.description || '—' }}</td>
            <td class="pdd-mut">缺省 {{ prm.default || '空' }}</td>
          </tr>
        </table>
      </div>

      <div class="pdd-sec">
        <div class="pdd-k">使用说明</div>
        <!-- README 为本机插件自带文件，渲染前已整体 HTML 转义 -->
        <div v-if="p.readme" class="pdd-md" v-html="mdHtml"></div>
        <p v-else class="pdd-mut">该插件未提供 README.md，以上方清单信息为准。</p>
      </div>
    </div>
  </a-drawer>
</template>

<script setup>
import { computed } from 'vue'
import { renderMd } from '@/utils/md'

const props = defineProps({
  visible: Boolean,
  plugin: { type: Object, default: null },
})
defineEmits(['update:visible'])

const p = computed(() => props.plugin)
const trigText = computed(() => (p.value?.triggers || []).join('；') || '')

const mdHtml = computed(() => (p.value?.readme ? renderMd(p.value.readme) : ''))
</script>

<style scoped>
.pdd-desc {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-2);
}
.pdd-sec {
  margin-top: 14px;
}
.pdd-k {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-text-2);
  margin-bottom: 6px;
}
.pdd-mut {
  margin: 0;
  font-size: 12.5px;
  color: var(--color-text-3);
}
.pdd-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.pdd-table th,
.pdd-table td {
  border: 1px solid var(--color-border-2);
  padding: 4px 8px;
  text-align: left;
  vertical-align: top;
}
.pdd-md {
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}
.pdd-md :deep(h1),
.pdd-md :deep(h2),
.pdd-md :deep(h3),
.pdd-md :deep(h4) {
  margin: 14px 0 6px;
  font-size: 14.5px;
}
.pdd-md :deep(h1:first-child),
.pdd-md :deep(h2:first-child) {
  margin-top: 0;
}
.pdd-md :deep(p) {
  margin: 6px 0;
}
.pdd-md :deep(ul),
.pdd-md :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}
.pdd-md :deep(pre) {
  margin: 8px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-fill-1, rgba(148, 163, 184, 0.08));
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: var(--font-family-mono, ui-monospace, Menlo, monospace);
}
.pdd-md :deep(code) {
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--color-fill-2, rgba(148, 163, 184, 0.14));
  font-family: var(--font-family-mono, ui-monospace, Menlo, monospace);
}
.pdd-md :deep(pre code) {
  padding: 0;
  background: none;
}
.pdd-md :deep(table) {
  margin: 8px 0;
}
.pdd-md :deep(a) {
  color: rgb(var(--primary-6));
}
</style>
