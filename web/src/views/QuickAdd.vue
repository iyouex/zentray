<template>
  <div class="quick-add-page" data-drag="true">
    <div class="quick-add-box" ref="boxRef">
      <a-input
        ref="inputRef"
        v-model="title"
        size="large"
        allow-clear
        placeholder="⚡ 闪电录入待办，按回车立即入库（ESC 取消）"
        @press-enter="onSave"
        @keydown.esc="onCancel"
      />
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { cancelHost, closeHost, createTask, getMeta } from '@/api/client'
import { gsap, EASE, dur, motionOff } from '@/motion'

const title = ref('')
const inputRef = ref(null)
const defaults = ref({ category: '工作', priority: 'medium' })

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

function onCancel() {
  cancelHost()
}

onMounted(async () => {
  try {
    const meta = await getMeta()
    if (meta?.quick_add) {
      defaults.value.category = meta.quick_add.default_category || '工作'
      defaults.value.priority = meta.quick_add.default_priority || 'medium'
    }
  } catch (_) {}
  await nextTick()
  inputRef.value?.focus?.()
})

/** 聚焦弹性绽放（spec §3.5）：聚焦时输入盒轻微放大，失焦回落；亮环仍由 CSS :focus-within 负责 */
const boxRef = ref(null)
onMounted(() => {
  const box = boxRef.value
  const input = inputRef.value?.$el?.querySelector('input') || inputRef.value?.$el
  input?.addEventListener('focus', () => {
    if (motionOff()) return
    gsap.to(box, { scale: 1.012, duration: 0.3, ease: EASE.spring, overwrite: 'auto' })
  })
  input?.addEventListener('blur', () => {
    if (motionOff()) return
    gsap.to(box, { scale: 1, duration: 0.28, ease: EASE.out, overwrite: 'auto' })
  })
})
</script>
