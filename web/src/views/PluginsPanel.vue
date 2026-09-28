<template>
  <div class="page pp-page">
    <div class="page-header pp-header">
      <h2>🧩 插件</h2>
      <a-space size="mini">
        <a-tag v-if="busy" size="small" color="orange">脚本运行中</a-tag>
        <a-button size="mini" type="text" :loading="loading" @click="refresh">刷新</a-button>
      </a-space>
    </div>

    <div class="page-body pp-body">
      <a-spin :loading="loading" style="width: 100%">
        <a-alert v-if="!enabled" type="warning">
          插件功能未启用。可在 设置 → 🧩 插件 中开启并导入。
        </a-alert>

        <template v-else>
          <div v-if="items.length" class="pp-list">
            <div v-for="p in items" :key="p.id" class="pp-card" :class="{ open: expanded === p.id }">
              <div class="pp-card-head" @click="onCardClick(p)">
                <span class="pp-name">{{ p.name }}</span>
                <a-tag size="small" :color="p.type === 'service' ? 'orangered' : 'green'">
                  {{ p.type === 'service' ? '服务' : '脚本' }}
                </a-tag>
                <a-tag v-if="p.category" size="small" color="cyan">{{ p.category }}</a-tag>
                <span class="pp-spacer" />
                <span v-if="p.type !== 'service'" class="pp-hint">
                  {{ expanded === p.id ? '收起' : (p.params?.length ? '设参数运行' : '运行') }}
                </span>
              </div>
              <div v-if="p.description" class="pp-desc">{{ p.description }}</div>

              <!-- 服务：三按钮直接放卡片上 -->
              <div v-if="p.type === 'service'" class="pp-actions">
                <a-button size="mini" :disabled="busy" :loading="acting === p.id" @click="serviceCmd(p, 'start')">▶ 启动</a-button>
                <a-button size="mini" :disabled="busy" :loading="acting === p.id" @click="serviceCmd(p, 'stop')">⏹ 停止</a-button>
                <a-button size="mini" :loading="acting === p.id" @click="serviceCmd(p, 'status')">ℹ 状态</a-button>
              </div>

              <!-- 脚本：同窗展开 确认卡 / 参数表单 -->
              <div v-else-if="expanded === p.id" class="pp-expand">
                <template v-if="p.params?.length">
                  <div v-for="prm in p.params" :key="prm.name" class="pp-param">
                    <span class="pp-param-k" :title="prm.description || prm.name">
                      {{ prm.description || prm.name }}
                    </span>
                    <a-input
                      v-model="drafts[p.id][prm.name]"
                      size="small"
                      :placeholder="`缺省 ${prm.default || '空'}`"
                      @press-enter="runScript(p)"
                    />
                  </div>
                </template>
                <p v-else class="pp-confirm">确定运行？进度显示在托盘顶栏，结果可在 设置 → 插件 → 运行历史 查看。</p>
                <div class="pp-actions">
                  <a-button size="small" type="primary" :loading="acting === p.id" @click="runScript(p)">
                    ▶ 运行
                  </a-button>
                  <a-button size="small" @click="expanded = ''">收起</a-button>
                </div>
              </div>
            </div>
          </div>
          <a-empty v-else description="暂无已加载插件，可在 设置 → 🧩 插件 导入" />

          <div v-if="failures.length" class="pp-fail">
            <div class="pp-fail-title">校验失败（未加载）</div>
            <div v-for="(f, i) in failures" :key="i" class="pp-fail-item">
              <code>{{ f.path }}</code>
            </div>
          </div>
        </template>
      </a-spin>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getSettings, listPlugins, runPlugin } from '@/api/client'

const loading = ref(true)
const enabled = ref(false)
const busy = ref(false)
const items = ref([])
const failures = ref([])
const expanded = ref('') // 当前展开的脚本卡 id
const acting = ref('') // 运行/服务命令进行中的插件 id
const drafts = reactive({}) // pid -> {param_name: value}

function applyList(data) {
  enabled.value = !!data.enabled
  busy.value = !!data.busy
  items.value = data.items || []
  failures.value = data.failures || []
  // 预填基线：参数预设 → manifest default
  for (const p of items.value) {
    drafts[p.id] = {}
    for (const prm of p.params || []) {
      drafts[p.id][prm.name] = prm.default ?? ''
    }
  }
}

async function refresh() {
  loading.value = true
  try {
    applyList(await listPlugins())
    if (enabled.value) {
      const s = await getSettings()
      const presets = s?.ops?.param_presets || {}
      for (const p of items.value) {
        const saved = presets[p.id] || {}
        for (const prm of p.params || []) {
          if (saved[prm.name] != null) drafts[p.id][prm.name] = saved[prm.name]
        }
      }
    }
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '加载插件列表失败')
  } finally {
    loading.value = false
  }
}

function onCardClick(p) {
  if (p.type === 'service') return
  expanded.value = expanded.value === p.id ? '' : p.id
}

async function runScript(p) {
  acting.value = p.id
  try {
    const body = p.params?.length ? { params: { ...(drafts[p.id] || {}) } } : {}
    await runPlugin(p.id, body)
    Message.success('已开始运行，完成后可在运行历史查看')
    expanded.value = ''
    const d = await listPlugins()
    busy.value = !!d.busy
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '运行失败')
  } finally {
    acting.value = ''
  }
}

async function serviceCmd(p, action) {
  acting.value = p.id
  try {
    const data = await runPlugin(p.id, { action })
    Message.info(`${p.name}：${data.detail ?? action}`)
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '服务命令失败')
  } finally {
    acting.value = ''
  }
}

onMounted(refresh)
</script>

<style scoped>
.pp-page {
  min-height: 100%;
}
.pp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pp-header h2 {
  margin: 0;
}
.pp-body {
  padding-top: 0;
}
.pp-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pp-card {
  padding: 12px 14px;
  border: 1px solid var(--color-border-2);
  border-radius: var(--zt-radius-card, 12px);
  background: var(--color-fill-1, rgba(148, 163, 184, 0.06));
  transition: border-color 0.2s ease;
}
.pp-card.open {
  border-color: var(--color-primary);
  background: var(--color-primary-glow, var(--color-fill-1));
}
.pp-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-wrap: wrap;
}
.pp-name {
  font-weight: 600;
  font-size: 14px;
}
.pp-spacer {
  flex: 1;
}
.pp-hint {
  font-size: 12px;
  color: var(--color-text-3);
}
.pp-desc {
  margin: 6px 0 0;
  font-size: 12.5px;
  color: var(--color-text-3);
  line-height: 1.45;
  cursor: pointer;
}
.pp-expand {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border-2);
}
.pp-param {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.pp-param-k {
  min-width: 96px;
  font-size: 12.5px;
  color: var(--color-text-2);
}
.pp-param .arco-input-wrapper {
  flex: 1;
}
.pp-confirm {
  margin: 0 0 8px;
  font-size: 12.5px;
  color: var(--color-text-2);
  line-height: 1.5;
}
.pp-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.pp-fail {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-danger-light-1, #ffece8);
  font-size: 12px;
}
.pp-fail-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.pp-fail-item code {
  font-size: 11px;
  word-break: break-all;
}
</style>
