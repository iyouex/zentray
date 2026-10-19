<template>
  <div class="job-editor">
    <!-- 风格（毒舌/温柔/干练 + 自定义）：默认收起；调度参数已迁移至插件（朝闻/暮省）参数预设 -->
    <a-collapse class="style-collapse" :bordered="false">
      <a-collapse-item key="styles" header="风格（毒舌 / 温柔 / 干练 + 自定义）">
        <p class="muted">内置三套默认风格，提示词均可改；也可新增自定义风格。</p>

        <div class="field-line">
          <span class="field-k">当前使用风格</span>
          <span class="field-v">
            <a-select
              v-model="model.active_style_id"
              :options="styleOptions"
              style="width: 240px"
            />
          </span>
        </div>

        <a-button
          size="small"
          type="outline"
          style="margin: 8px 0"
          @click="addCustomStyle"
        >
          ➕ 自定义风格
        </a-button>

        <a-collapse :default-active-key="[model.active_style_id]">
          <a-collapse-item
            v-for="s in model.styles"
            :key="s.id"
            :header="`${s.name}${s.is_builtin ? '（内置）' : '（自定义）'}${s.id === model.active_style_id ? ' · 使用中' : ''}`"
          >
            <a-form layout="vertical" size="small">
              <a-form-item label="名称">
                <a-input v-model="s.name" />
              </a-form-item>
              <a-form-item label="系统提示词（可自定义）">
                <a-textarea
                  v-model="s.system_prompt"
                  :auto-size="{ minRows: 4, maxRows: 10 }"
                  placeholder="System prompt"
                />
              </a-form-item>
              <a-button
                v-if="!s.is_builtin"
                size="mini"
                status="danger"
                @click="removeStyle(s.id)"
              >
                删除风格
              </a-button>
            </a-form>
          </a-collapse-item>
        </a-collapse>
      </a-collapse-item>
    </a-collapse>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'

const model = defineModel({ type: Object, required: true })

const styleOptions = computed(() =>
  (model.value.styles || []).map((s) => ({
    label: s.name + (s.is_builtin ? '' : ' · 自定义'),
    value: s.id,
  })),
)

function uid() {
  return 'custom_' + Math.random().toString(36).slice(2, 9)
}

function addCustomStyle() {
  if (!model.value.styles) model.value.styles = []
  const id = uid()
  model.value.styles.push({
    id,
    name: '自定义风格',
    system_prompt: '',
    is_builtin: false,
  })
  model.value.active_style_id = id
}

function removeStyle(id) {
  model.value.styles = (model.value.styles || []).filter((s) => s.id !== id)
  if (model.value.active_style_id === id) {
    model.value.active_style_id = model.value.styles[0]?.id || 'toxic'
  }
}

watch(
  () => model.value,
  (v) => {
    if (v && !Array.isArray(v.styles)) v.styles = []
  },
  { immediate: true, deep: true },
)
</script>

<style scoped>
/* field-line 行式（与 Settings 页 zt 体系同构：标签左、控件右） */
.field-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
}
.field-k {
  font-size: var(--zt-t3);
  color: var(--color-text-2);
  flex-shrink: 0;
}
.field-v {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.style-collapse :deep(.arco-collapse-item) {
  border: none;
}
.muted {
  color: var(--color-text-3);
  font-size: 12px;
}
</style>
