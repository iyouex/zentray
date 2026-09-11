<template>
  <!-- 横向紧凑：− 输入 + ，可输入也可点调 -->
  <div class="num-spinner" :class="{ disabled }">
    <button
      type="button"
      class="spin-btn"
      :disabled="disabled"
      title="-1"
      @click="nudge(-1)"
    >
      −
    </button>
    <a-input
      class="num-input"
      v-model="text"
      :disabled="disabled"
      :placeholder="String(min)"
      @blur="commit"
      @press-enter="commit"
    />
    <button
      type="button"
      class="spin-btn"
      :disabled="disabled"
      title="+1"
      @click="nudge(1)"
    >
      +
    </button>
    <span v-if="suffix" class="suffix">{{ suffix }}</span>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const model = defineModel({ type: Number, required: true })
const props = defineProps({
  min: { type: Number, default: 1 },
  max: { type: Number, default: 120 },
  step: { type: Number, default: 1 },
  suffix: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

const text = ref(String(model.value ?? props.min))

watch(
  () => model.value,
  (v) => {
    text.value = String(v ?? props.min)
  },
)

function clamp(n) {
  let x = Number(n)
  if (Number.isNaN(x)) x = props.min
  x = Math.round(x / props.step) * props.step
  return Math.max(props.min, Math.min(props.max, x))
}

function commit() {
  const v = clamp(parseInt(String(text.value).replace(/[^\d-]/g, ''), 10))
  model.value = v
  text.value = String(v)
}

function nudge(dir) {
  model.value = clamp((model.value ?? props.min) + dir * props.step)
  text.value = String(model.value)
}
</script>

<style scoped>
.num-spinner {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  gap: 0;
  height: 28px;
  border: 1px solid var(--color-border-2, #e5e6eb);
  border-radius: var(--zt-radius-md);
  background: var(--color-bg-2, #fff);
  overflow: hidden;
}
.num-spinner.disabled {
  opacity: 0.55;
}
.num-input {
  width: 48px;
}
.num-input :deep(.arco-input-wrapper) {
  border: none !important;
  background: transparent !important;
  border-radius: 0;
  height: 26px;
}
.num-input :deep(.arco-input) {
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 0 2px;
  height: 26px;
  line-height: 26px;
}
.spin-btn {
  width: 26px;
  height: 26px;
  border: none;
  background: var(--color-fill-1, #f2f3f5);
  color: var(--color-text-2);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0;
  flex-shrink: 0;
}
.spin-btn:hover:not(:disabled) {
  background: var(--color-fill-2, #e5e6eb);
  color: var(--color-text-1);
}
.spin-btn:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}
.suffix {
  font-size: 12px;
  color: var(--color-text-3);
  padding: 0 8px 0 4px;
  white-space: nowrap;
}
</style>
