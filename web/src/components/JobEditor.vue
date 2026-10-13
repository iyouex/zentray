<template>
  <div class="job-editor">
    <a-form layout="vertical" style="max-width: 720px">
      <a-form-item :label="`启用${kindLabel}`">
        <a-switch v-model="model.enabled" />
        <span class="muted" style="margin-left: 10px">
          关闭时下方设置不可改；开启后才可配置
        </span>
      </a-form-item>

      <fieldset class="job-fields" :disabled="!model.enabled">
        <a-form-item label="调度时间">
          <!-- 单一时间控件：可输入 HH:mm，也可用上下调节 -->
          <div class="time-fused" :class="{ disabled: !model.enabled }">
            <button
              type="button"
              class="spin-btn"
              :disabled="!model.enabled"
              title="小时 +1"
              @click="nudgeHour(1)"
            >
              ▲
            </button>
            <button
              type="button"
              class="spin-btn spin-min"
              :disabled="!model.enabled"
              title="分钟 +1"
              @click="nudgeMinute(1)"
            >
              ▲
            </button>
            <a-input
              class="time-input"
              v-model="timeText"
              :disabled="!model.enabled"
              placeholder="HH:mm"
              allow-clear
              @blur="commitTime"
              @press-enter="commitTime"
            />
            <button
              type="button"
              class="spin-btn"
              :disabled="!model.enabled"
              title="小时 -1"
              @click="nudgeHour(-1)"
            >
              ▼
            </button>
            <button
              type="button"
              class="spin-btn spin-min"
              :disabled="!model.enabled"
              title="分钟 -1"
              @click="nudgeMinute(-1)"
            >
              ▼
            </button>
          </div>
          <div class="muted tiny">格式 08:30；左侧调小时、右侧调分钟，也可直接输入</div>
        </a-form-item>

        <a-form-item label="跳过公休日">
          <a-switch
            :model-value="skipPublicRest"
            :disabled="!model.enabled"
            @change="onSkipPublicRest"
          />
          <span class="muted" style="margin-left: 10px">
            含周末与法定节假日（自动调度跳过；手动触发不受影响）
          </span>
        </a-form-item>

        <a-form-item label="保存到本地 reviews/">
          <a-switch v-model="model.save_local" :disabled="!model.enabled" />
        </a-form-item>

        <a-form-item label="完成通知渠道">
          <a-checkbox-group v-model="model.notify_channels" :disabled="!model.enabled" @change="onChannelsChange">
            <a-checkbox value="app_popup">应用弹窗</a-checkbox>
            <a-checkbox value="wxpusher">WxPusher</a-checkbox>
            <a-checkbox value="feishu_bot">飞书机器人</a-checkbox>
          </a-checkbox-group>
          <div class="muted tiny">可多选，至少保留一项；WxPusher / 飞书机器人需在 设置 → 🔔 通知 中启用才实际推送</div>
        </a-form-item>

        <a-form-item label="报告托盘轮播">
          <a-space size="small">
            <a-switch v-model="model.report_tray_enabled" :disabled="!model.enabled" />
            <a-input-number
              v-model="model.report_tray_minutes"
              :disabled="!model.enabled || !model.report_tray_enabled"
              :min="1"
              :max="1440"
              :step="5"
              size="small"
              style="width: 104px"
            />
            <span class="muted">分钟</span>
          </a-space>
          <div class="muted tiny">
            完成通知未点击查看时，报告提示进入顶栏任务轮播，到期自动退出
          </div>
        </a-form-item>

        <a-divider>风格（毒舌 / 温柔 / 干练 + 自定义）</a-divider>
        <p class="muted">内置三套默认风格，提示词均可改；也可新增自定义风格。</p>

        <a-form-item label="当前使用风格">
          <a-select
            v-model="model.active_style_id"
            :options="styleOptions"
            :disabled="!model.enabled"
            style="width: 240px"
          />
        </a-form-item>

        <a-space style="margin-bottom: 8px">
          <a-button
            size="small"
            type="outline"
            :disabled="!model.enabled"
            @click="addCustomStyle"
          >
            ➕ 自定义风格
          </a-button>
        </a-space>

        <a-collapse :default-active-key="[model.active_style_id]">
          <a-collapse-item
            v-for="s in model.styles"
            :key="s.id"
            :header="`${s.name}${s.is_builtin ? '（内置）' : '（自定义）'}${s.id === model.active_style_id ? ' · 使用中' : ''}`"
            :disabled="!model.enabled"
          >
            <a-form layout="vertical" size="small">
              <a-form-item label="名称">
                <a-input v-model="s.name" :disabled="!model.enabled" />
              </a-form-item>
              <a-form-item label="系统提示词（可自定义）">
                <a-textarea
                  v-model="s.system_prompt"
                  :disabled="!model.enabled"
                  :auto-size="{ minRows: 4, maxRows: 10 }"
                  placeholder="System prompt"
                />
              </a-form-item>
              <a-button
                v-if="!s.is_builtin"
                size="mini"
                status="danger"
                :disabled="!model.enabled"
                @click="removeStyle(s.id)"
              >
                删除风格
              </a-button>
            </a-form>
          </a-collapse-item>
        </a-collapse>
      </fieldset>
    </a-form>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const model = defineModel({ type: Object, required: true })
defineProps({
  kindLabel: { type: String, default: '任务' },
  defaultTime: { type: String, default: '08:00' },
})

const timeText = ref('08:00')

const styleOptions = computed(() =>
  (model.value.styles || []).map((s) => ({
    label: s.name + (s.is_builtin ? '' : ' · 自定义'),
    value: s.id,
  })),
)

/** 公休日 = 周末 + 节假日 联动开关 */
const skipPublicRest = computed(
  () => !!(model.value.skip_weekends && model.value.skip_holidays),
)

function onSkipPublicRest(v) {
  const on = !!v
  model.value.skip_weekends = on
  model.value.skip_holidays = on
}

function pad2(n) {
  return String(Math.max(0, n)).padStart(2, '0')
}

function syncTextFromModel() {
  const h = model.value?.trigger_hour ?? 0
  const m = model.value?.trigger_minute ?? 0
  timeText.value = `${pad2(h)}:${pad2(m)}`
}

function parseTime(v) {
  const s = String(v || '').trim()
  const m = s.match(/^(\d{1,2})\s*[:：]\s*(\d{1,2})$/)
  if (!m) {
    syncTextFromModel()
    return
  }
  let hh = Math.max(0, Math.min(23, parseInt(m[1], 10)))
  let mm = Math.max(0, Math.min(59, parseInt(m[2], 10)))
  model.value.trigger_hour = hh
  model.value.trigger_minute = mm
  timeText.value = `${pad2(hh)}:${pad2(mm)}`
}

function commitTime() {
  parseTime(timeText.value)
}

function nudgeHour(delta) {
  let h = (model.value.trigger_hour ?? 0) + delta
  if (h > 23) h = 0
  if (h < 0) h = 23
  model.value.trigger_hour = h
  syncTextFromModel()
}

function nudgeMinute(delta) {
  let m = (model.value.trigger_minute ?? 0) + delta
  if (m > 59) m = 0
  if (m < 0) m = 59
  model.value.trigger_minute = m
  syncTextFromModel()
}

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
    // 空 = 跟随全局（后端语义）；界面上物化为全选，避免看着像「不通知」
    if (v && !Array.isArray(v.notify_channels)) v.notify_channels = ['app_popup', 'wxpusher', 'feishu_bot']
    syncTextFromModel()
  },
  { immediate: true, deep: true },
)

/** 至少保留一个渠道 */
function onChannelsChange(v) {
  if (!v || !v.length) model.value.notify_channels = ['app_popup']
}

watch(
  () => [model.value?.trigger_hour, model.value?.trigger_minute],
  () => syncTextFromModel(),
)

// 输入完整 HH:mm 时即时写回 model，避免未失焦点保存导致仍是旧时刻
watch(timeText, (v) => {
  const s = String(v || '').trim()
  if (/^\d{1,2}\s*[:：]\s*\d{1,2}$/.test(s)) {
    parseTime(s)
  }
})
</script>

<style scoped>
.job-fields {
  border: none;
  margin: 0;
  padding: 0;
  min-inline-size: 0;
}
.job-fields:disabled {
  opacity: 0.55;
  pointer-events: none;
}
.time-fused {
  display: inline-grid;
  grid-template-columns: 28px 28px 1fr 28px 28px;
  grid-template-rows: 22px 36px 22px;
  gap: 2px 4px;
  width: 200px;
  align-items: center;
  padding: 4px;
  border: 1px solid var(--color-border-2, #e5e6eb);
  border-radius: var(--zt-radius-md);
  background: var(--color-fill-1, #f7f8fa);
}
.time-fused.disabled {
  opacity: 0.7;
}
.time-fused .time-input {
  grid-column: 1 / -1;
  grid-row: 2;
}
.time-fused .time-input :deep(.arco-input) {
  text-align: center;
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
}
.spin-btn {
  grid-row: 1;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--color-text-2);
  cursor: pointer;
  line-height: 1;
  font-size: 10px;
  padding: 0;
  border-radius: 4px;
}
.spin-btn:hover:not(:disabled) {
  background: var(--color-fill-2, #e5e6eb);
  color: var(--color-text-1);
}
.spin-btn:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}
.spin-btn:nth-of-type(1) {
  grid-column: 1;
  grid-row: 1;
}
.spin-btn:nth-of-type(2) {
  grid-column: 5;
  grid-row: 1;
}
.spin-btn:nth-of-type(3) {
  grid-column: 1;
  grid-row: 3;
}
.spin-btn:nth-of-type(4) {
  grid-column: 5;
  grid-row: 3;
}
.muted {
  color: var(--color-text-3);
  font-size: 12px;
}
.tiny {
  margin-top: 6px;
}
</style>
