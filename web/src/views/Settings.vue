<template>
  <div class="page settings-page">
    <div class="page-header">
      <h2>⚙️ 应用设置</h2>
    </div>

    <div class="page-body settings-page-body">
    <a-spin :loading="loading" class="settings-spin">
      <div class="settings-layout">
        <a-menu
          class="nav-main"
          :selected-keys="[mainKey]"
          @menu-item-click="onMainNav"
        >
          <a-menu-item key="ai_hub">AI 与通知</a-menu-item>
          <a-menu-item key="polling">任务轮播</a-menu-item>
          <a-menu-item key="pomodoro">番茄钟</a-menu-item>
          <a-menu-item key="categories">分类</a-menu-item>
          <a-menu-item key="system">系统</a-menu-item>
          <a-menu-item key="history">📜 历史</a-menu-item>
        </a-menu>

        <div class="settings-body" :class="{ 'is-ai': mainKey === 'ai_hub', 'is-history': mainKey === 'history' }">
          <template v-if="mainKey === 'ai_hub'">
            <a-tabs class="ai-tabs" type="rounded" v-model:active-key="aiTab">
              <!-- 模型接入：折叠行 + 当前配置可编辑 -->
              <a-tab-pane key="api" title="模型接入">
                <section class="section">
                  <p class="hint">
                    可配置多个 API（名称区分），<b>同时只能启用一个</b>。折叠时各占一行，展开可编辑。
                  </p>
                  <a-space style="margin-bottom: 12px">
                    <a-button type="primary" size="small" @click="addApiProfile">➕ 添加 API</a-button>
                  </a-space>

                  <a-collapse
                    v-model:active-key="apiExpandKeys"
                    :bordered="true"
                    expand-icon-position="right"
                  >
                    <a-collapse-item
                      v-for="p in form.ai.api_profiles"
                      :key="p.id"
                      :name="p.id"
                    >
                      <template #header>
                        <div class="api-row-header" @click.stop>
                          <a-tag
                            v-if="form.ai.active_api_id === p.id"
                            color="arcoblue"
                            size="small"
                          >
                            使用中
                          </a-tag>
                          <a-tag v-else color="gray" size="small">未启用</a-tag>
                          <span class="api-name">{{ p.name || '未命名' }}</span>
                          <span class="api-meta">{{ p.model || '—' }} · {{ shortKey(p.api_key) }}</span>
                          <a-button
                            v-if="form.ai.active_api_id !== p.id"
                            size="mini"
                            type="outline"
                            @click.stop="form.ai.active_api_id = p.id"
                          >
                            启用
                          </a-button>
                          <a-button
                            v-else
                            size="mini"
                            type="primary"
                            disabled
                          >
                            当前
                          </a-button>
                        </div>
                      </template>

                      <a-form layout="vertical" size="small" class="api-edit-form">
                        <a-form-item label="名称">
                          <a-input v-model="p.name" placeholder="配置名称" />
                        </a-form-item>
                        <a-form-item label="API Key">
                          <a-input-password v-model="p.api_key" placeholder="sk-..." />
                        </a-form-item>
                        <a-form-item label="Base URL">
                          <a-input v-model="p.base_url" placeholder="https://api.openai.com/v1" />
                        </a-form-item>
                        <a-form-item label="模型">
                          <a-input v-model="p.model" placeholder="gpt-4o" />
                        </a-form-item>
                        <a-space>
                          <a-button
                            v-if="form.ai.active_api_id !== p.id"
                            size="small"
                            type="primary"
                            @click="form.ai.active_api_id = p.id"
                          >
                            设为当前使用
                          </a-button>
                          <a-button
                            size="small"
                            status="danger"
                            :disabled="form.ai.api_profiles.length <= 1"
                            @click="removeApiProfile(p.id)"
                          >
                            删除此配置
                          </a-button>
                        </a-space>
                      </a-form>
                    </a-collapse-item>
                  </a-collapse>
                </section>
              </a-tab-pane>

              <a-tab-pane key="plan" title="每日计划">
                <JobEditor v-model="form.ai.plan" kind-label="每日计划" />
              </a-tab-pane>

              <a-tab-pane key="review" title="每日复盘">
                <JobEditor v-model="form.ai.review" kind-label="每日复盘" />
              </a-tab-pane>

              <!-- 通知：固定渠道，不可增删，可折叠 -->
              <a-tab-pane key="notify" title="通知渠道">
                <section class="section">
                  <p class="hint">
                    内置渠道（不可增删），可同时开启。点击行展开配置。
                  </p>
                  <a-collapse
                    v-model:active-key="notifyExpandKeys"
                    :bordered="true"
                    expand-icon-position="right"
                  >
                    <a-collapse-item
                      v-for="ch in fixedChannels"
                      :key="ch.id"
                      :name="ch.id"
                    >
                      <template #header>
                        <div class="ch-row-header" @click.stop>
                          <span class="ch-title">{{ ch.name }}</span>
                          <a-tag size="small" :color="ch.enabled ? 'green' : 'gray'">
                            {{ ch.enabled ? '已开启' : '已关闭' }}
                          </a-tag>
                          <a-switch
                            v-model="ch.enabled"
                            size="small"
                            checked-text="开"
                            unchecked-text="关"
                            @click.stop
                          />
                        </div>
                      </template>

                      <div v-if="ch.type === 'app_popup'" class="ch-body">
                        <a-alert type="info">
                          开启后，计划/复盘完成时会通过<strong>托盘系统通知</strong>弹出提醒。
                        </a-alert>
                      </div>
                      <a-form v-else layout="vertical" size="small" class="ch-body">
                        <a-form-item label="App Token">
                          <a-input
                            v-model="ch.wxpusher_app_token"
                            placeholder="AT_..."
                            :disabled="!ch.enabled"
                          />
                        </a-form-item>
                        <a-form-item label="UID">
                          <a-input
                            v-model="ch.wxpusher_uid"
                            placeholder="UID_..."
                            :disabled="!ch.enabled"
                          />
                        </a-form-item>
                      </a-form>
                    </a-collapse-item>
                  </a-collapse>
                </section>
              </a-tab-pane>
            </a-tabs>
          </template>

          <template v-else-if="mainKey === 'polling'">
            <div class="compact-page">
              <section class="compact-block">
                <div class="compact-head">轮播设置</div>
                <div class="field-table">
                  <div class="field-line">
                    <span class="field-k">🔴 高优先停留</span>
                    <NumberSpinner v-model="form.polling.high_priority_seconds" :min="1" :max="120" suffix="秒" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">🟡 中优先停留</span>
                    <NumberSpinner v-model="form.polling.medium_priority_seconds" :min="1" :max="120" suffix="秒" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">🟢 低优先停留</span>
                    <NumberSpinner v-model="form.polling.low_priority_seconds" :min="1" :max="120" suffix="秒" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">轮播模式</span>
                    <a-select
                      v-model="form.polling.rotation_mode"
                      size="small"
                      style="width: 168px"
                      :options="[
                        { label: '随机加权', value: 'random' },
                        { label: '高优先优先', value: 'priority_high_first' },
                        { label: '低优先优先', value: 'priority_low_first' },
                      ]"
                    />
                  </div>
                </div>
              </section>

              <div class="compact-sep" />

              <section class="compact-block">
                <div class="compact-head">逾期设置</div>
                <div class="field-table">
                  <div class="field-line">
                    <span class="field-k">逾期优先轮播</span>
                    <a-switch v-model="form.polling.enable_overdue_rotation" size="small" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">逾期前缀</span>
                    <a-input
                      v-model="form.polling.overdue_prefix"
                      size="small"
                      :disabled="!form.polling.enable_overdue_rotation"
                      placeholder="【已逾期】"
                      style="width: 168px"
                    />
                  </div>
                </div>
              </section>
            </div>
          </template>

          <template v-else-if="mainKey === 'pomodoro'">
            <div class="compact-page">
              <section class="compact-block">
                <div class="compact-head">时长</div>
                <div class="field-table">
                  <div class="field-line">
                    <span class="field-k">专注时长</span>
                    <NumberSpinner v-model="form.pomodoro.duration_minutes" :min="1" :max="120" suffix="分" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">延长步长</span>
                    <NumberSpinner v-model="form.pomodoro.extend_minutes" :min="1" :max="60" suffix="分" />
                  </div>
                </div>
              </section>

              <div class="compact-sep" />

              <section class="compact-block">
                <div class="compact-head">托盘显示</div>
                <p class="hint-sm">左侧固定番茄饼图；右侧可选倒计时或文案。</p>
                <div class="field-table">
                  <div class="field-line">
                    <span class="field-k">右侧文字</span>
                    <a-radio-group v-model="form.pomodoro.tray_display" size="small" type="button">
                      <a-radio value="countdown">倒计时</a-radio>
                      <a-radio value="text">文案</a-radio>
                    </a-radio-group>
                  </div>
                  <div v-if="form.pomodoro.tray_display === 'text'" class="field-line">
                    <span class="field-k">文案</span>
                    <a-input
                      v-model="form.pomodoro.tray_text"
                      size="small"
                      placeholder="专注中"
                      :max-length="24"
                      style="width: 168px"
                    />
                  </div>
                </div>
              </section>
            </div>
          </template>

          <template v-else-if="mainKey === 'categories'">
            <div class="cat-page">
              <section class="poll-block">
                <h3 class="block-title">标题格式</h3>
                <a-form layout="vertical" style="max-width: 480px">
                  <a-form-item label="标题括号（成对选择）">
                    <a-radio-group
                      :model-value="wrapPresetKey"
                      type="button"
                      @change="onWrapPreset"
                    >
                      <a-radio
                        v-for="w in WRAP_PRESETS"
                        :key="w.key"
                        :value="w.key"
                      >
                        {{ w.label }} 示例 {{ w.left }}工作-需求{{ w.right }}
                      </a-radio>
                    </a-radio-group>
                  </a-form-item>
                  <a-form-item label="一二级分隔符">
                    <a-input v-model="form.categories.level_separator" style="width: 80px" />
                  </a-form-item>
                  <a-form-item label="启用二级分类">
                    <a-switch v-model="form.categories.enabled_secondary" />
                  </a-form-item>
                </a-form>
              </section>

              <a-divider />

              <section class="poll-block">
                <div class="cat-head">
                  <h3 class="block-title" style="margin: 0">一级分类</h3>
                  <a-button type="primary" size="small" @click="addPrimary">➕ 添加一级</a-button>
                </div>
                <p class="hint">可编辑名称；开启二级后，可在各级下添加/删除二级分类。</p>

                <a-collapse
                  v-if="form.categories.primary_list?.length"
                  :bordered="true"
                  expand-icon-position="right"
                >
                  <a-collapse-item
                    v-for="p in form.categories.primary_list"
                    :key="p.id"
                    :name="p.id"
                  >
                    <template #header>
                      <div class="cat-row-header" @click.stop>
                        <a-input
                          v-model="p.name"
                          size="small"
                          style="width: 160px"
                          @click.stop
                        />
                        <span class="muted">
                          {{ form.categories.enabled_secondary
                            ? `二级 ${(p.secondaries || []).length} 个`
                            : '仅一级' }}
                        </span>
                        <a-button
                          size="mini"
                          status="danger"
                          @click.stop="removePrimary(p.id)"
                        >
                          删除
                        </a-button>
                      </div>
                    </template>

                    <div v-if="form.categories.enabled_secondary" class="sec-block">
                      <a-space style="margin-bottom: 8px">
                        <a-button size="mini" type="outline" @click="addSecondary(p)">
                          ➕ 添加二级
                        </a-button>
                      </a-space>
                      <div
                        v-for="s in p.secondaries || []"
                        :key="s.id"
                        class="sec-row"
                      >
                        <a-input v-model="s.name" size="small" placeholder="二级名称" />
                        <a-button size="mini" status="danger" @click="removeSecondary(p, s.id)">
                          删除
                        </a-button>
                      </div>
                      <a-empty
                        v-if="!(p.secondaries || []).length"
                        description="暂无二级分类"
                      />
                    </div>
                    <a-alert v-else type="info">
                      开启「启用二级分类」后，可在此添加二级。
                    </a-alert>
                  </a-collapse-item>
                </a-collapse>
                <a-empty v-else description="暂无一级分类，请点击添加" />
              </section>
            </div>
          </template>

          <template v-else-if="mainKey === 'system'">
            <div class="system-settings">
              <a-card class="sys-card" :bordered="false" title="外观">
                <a-form layout="vertical" style="max-width: 420px">
                  <a-form-item label="主题">
                    <a-radio-group v-model="form.appearance.theme" @change="onThemePreview">
                      <a-radio value="system">跟随系统</a-radio>
                      <a-radio value="light">浅色</a-radio>
                      <a-radio value="dark">深色</a-radio>
                    </a-radio-group>
                  </a-form-item>
                  <a-form-item label="界面皮肤">
                    <a-radio-group v-model="form.appearance.skin" @change="onAppearancePreview">
                      <a-radio value="neo">Neo</a-radio>
                      <a-radio value="aurora">Aurora</a-radio>
                    </a-radio-group>
                  </a-form-item>
                  <a-form-item label="界面动效">
                    <a-switch
                      v-model="form.appearance.motion"
                      checked-value="full"
                      unchecked-value="off"
                      checked-text="开"
                      unchecked-text="关"
                      @change="onAppearancePreview"
                    />
                  </a-form-item>
                  <a-form-item label="形状风格">
                    <a-radio-group v-model="form.appearance.shape" @change="onAppearancePreview">
                      <a-radio value="round">圆润</a-radio>
                      <a-radio value="crisp">利落</a-radio>
                    </a-radio-group>
                  </a-form-item>
                  <a-alert type="info">主题预览立即生效；点底部「保存设置」写入配置。</a-alert>
                </a-form>
              </a-card>

              <a-card class="sys-card" :bordered="false" title="启动">
                <div class="sys-row">
                  <div>
                    <div class="sys-title">开机自启</div>
                    <div class="sys-desc">
                      开启后登录系统时自动启动 ZenTray。开关立即生效，无需点保存。
                    </div>
                    <div v-if="autostartHint" class="sys-hint muted">{{ autostartHint }}</div>
                  </div>
                  <a-switch
                    :model-value="autostartEnabled"
                    :loading="autostartLoading"
                    @change="onAutostartChange"
                  />
                </div>
              </a-card>

              <a-card class="sys-card" :bordered="false" title="数据迁移">
                <p class="sys-desc" style="margin-bottom: 12px">
                  导出任务、配置、历史与归档，便于跨设备迁移。导入为<strong>替换</strong>模式，导入前会自动生成本地安全备份。
                </p>

                <div class="sys-section-label">导出内容</div>
                <a-checkbox-group v-model="exportInclude" direction="vertical" class="export-checks">
                  <a-checkbox
                    v-for="opt in includeOptions"
                    :key="opt.key"
                    :value="opt.key"
                  >
                    {{ opt.label }}
                    <a-tag v-if="opt.sensitive" size="small" color="orangered" style="margin-left: 6px">
                      含密钥
                    </a-tag>
                  </a-checkbox>
                </a-checkbox-group>

                <a-space style="margin-top: 12px" wrap>
                  <a-button type="primary" :loading="exportLoading" @click="onExportBackup">
                    导出备份
                  </a-button>
                  <a-button :loading="archivePackLoading" @click="onPackArchive">
                    打包归档
                  </a-button>
                </a-space>
                <p v-if="lastExportPath" class="sys-path">
                  最近导出：<code>{{ lastExportPath }}</code>
                </p>

                <a-divider />

                <div class="sys-section-label">导入备份（替换）</div>
                <div class="sys-import-row">
                  <a-input
                    v-model="importPath"
                    placeholder="本机 zip 绝对路径，例如 /home/you/.../zentray-backup-....zip"
                    allow-clear
                  />
                  <a-button
                    type="primary"
                    status="warning"
                    :loading="importLoading"
                    @click="onImportBackup"
                  >
                    导入
                  </a-button>
                </div>
                <a-alert type="warning" style="margin-top: 10px">
                  导入将覆盖所选类别的本地数据；操作前会自动写入安全备份到 exports 目录。
                </a-alert>
                <p v-if="lastImportMsg" class="sys-path">{{ lastImportMsg }}</p>
              </a-card>
            </div>
          </template>

          <!-- 历史：只读单页（日期侧栏 + 合并时间轴 + 详情），无保存动作 -->
          <template v-else-if="mainKey === 'history'">
            <HistoryPanel />
          </template>
        </div>
      </div>
    </a-spin>
    </div>

    <div class="page-footer">
      <a-button @click="cancelHost">取消</a-button>
      <a-button v-if="mainKey !== 'history'" type="primary" :loading="saving" @click="onSave">💾 保存设置</a-button>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  cancelHost,
  closeHost,
  exportBackup,
  getSettings,
  getSystemStatus,
  importBackup,
  packArchive,
  saveSettings,
  setAutostart,
} from '@/api/client'
import { applyAppearance, applyTheme } from '@/theme'
import JobEditor from '@/components/JobEditor.vue'
import HistoryPanel from '@/components/HistoryPanel.vue'
import NumberSpinner from '@/components/NumberSpinner.vue'

const setThemeMode = inject('setThemeMode', null)
const loading = ref(false)
const saving = ref(false)
const mainKey = ref('ai_hub')
const aiTab = ref('api')
const apiExpandKeys = ref([])
const notifyExpandKeys = ref([])

// —— 系统页 ——
const autostartEnabled = ref(false)
const autostartLoading = ref(false)
const autostartHint = ref('')
const includeOptions = ref([])
const exportInclude = ref([])
const exportLoading = ref(false)
const archivePackLoading = ref(false)
const lastExportPath = ref('')
const importPath = ref('')
const importLoading = ref(false)
const lastImportMsg = ref('')

const form = reactive(emptyForm())

/** 固定两条渠道，不允许增删 */
const fixedChannels = computed(() => ensureFixedChannels(form.notification))

function emptyForm() {
  return {
    polling: {
      high_priority_seconds: 4,
      medium_priority_seconds: 2,
      low_priority_seconds: 2,
      rotation_mode: 'random',
      enable_overdue_rotation: true,
      overdue_prefix: '【已逾期】',
    },
    pomodoro: {
      duration_minutes: 25,
      extend_minutes: 10,
      tray_display: 'countdown',
      tray_text: '专注中',
    },
    nightly: {},
    notification: {
      channels: defaultChannels(),
      enabled: true,
      wxpusher_app_token: '',
      wxpusher_uid: '',
    },
    ai: {
      api_profiles: [
        {
          id: 'default',
          name: '默认',
          api_key: '',
          base_url: 'https://api.openai.com/v1',
          model: 'gpt-4o',
        },
      ],
      active_api_id: 'default',
      plan: emptyJob(8, 0),
      review: emptyJob(23, 30),
    },
    categories: {
      enabled_secondary: true,
      wrap_left: '[',
      wrap_right: ']',
      level_separator: '-',
      primary_list: [],
    },
    quick_add: { default_category: '工作', default_priority: 'medium' },
    appearance: { theme: 'system', autostart: false, motion: 'full', shape: 'round', skin: 'neo' },
  }
}

/** 成对括号预设（不可拆开自定义） */
const WRAP_PRESETS = [
  { key: '[]', label: '[]', left: '[', right: ']' },
  { key: '【】', label: '【】', left: '【', right: '】' },
  { key: '<>', label: '<>', left: '<', right: '>' },
  { key: '（）', label: '（）', left: '（', right: '）' },
]

const wrapPresetKey = computed(() => {
  const l = form.categories?.wrap_left || '['
  const r = form.categories?.wrap_right || ']'
  const hit = WRAP_PRESETS.find((w) => w.left === l && w.right === r)
  return hit?.key || '[]'
})

function onWrapPreset(key) {
  const w = WRAP_PRESETS.find((x) => x.key === key) || WRAP_PRESETS[0]
  form.categories.wrap_left = w.left
  form.categories.wrap_right = w.right
}

function addPrimary() {
  if (!form.categories.primary_list) form.categories.primary_list = []
  form.categories.primary_list.push({
    id: uid(),
    name: '新分类',
    secondaries: [],
  })
}

function removePrimary(id) {
  form.categories.primary_list = (form.categories.primary_list || []).filter(
    (p) => p.id !== id,
  )
}

function addSecondary(primary) {
  if (!primary.secondaries) primary.secondaries = []
  primary.secondaries.push({ id: uid(), name: '新二级' })
}

function removeSecondary(primary, sid) {
  primary.secondaries = (primary.secondaries || []).filter((s) => s.id !== sid)
}

function defaultChannels() {
  return [
    {
      id: 'ch_app_popup',
      type: 'app_popup',
      name: '应用弹窗',
      enabled: true,
      wxpusher_app_token: '',
      wxpusher_uid: '',
    },
    {
      id: 'ch_wxpusher',
      type: 'wxpusher',
      name: 'WxPusher',
      enabled: false,
      wxpusher_app_token: '',
      wxpusher_uid: '',
    },
  ]
}

/**
 * 始终只保留 app_popup + wxpusher 各一条（合并旧数据）
 */
function ensureFixedChannels(notification) {
  const list = notification?.channels || []
  const app =
    list.find((c) => c.type === 'app_popup') ||
    defaultChannels().find((c) => c.type === 'app_popup')
  let wx = list.find((c) => c.type === 'wxpusher')
  if (!wx) {
    wx = defaultChannels().find((c) => c.type === 'wxpusher')
    // 兼容旧字段
    if (notification?.wxpusher_app_token) {
      wx = {
        ...wx,
        wxpusher_app_token: notification.wxpusher_app_token,
        wxpusher_uid: notification.wxpusher_uid || '',
        enabled: !!(notification.wxpusher_app_token && notification.wxpusher_uid),
      }
    }
  }
  app.id = app.id || 'ch_app_popup'
  app.name = '应用弹窗'
  app.type = 'app_popup'
  wx.id = wx.id || 'ch_wxpusher'
  wx.name = 'WxPusher'
  wx.type = 'wxpusher'
  // 写回 form，保证引用一致
  notification.channels = [app, wx]
  return notification.channels
}

function emptyJob(h, m) {
  return {
    enabled: false,
    trigger_hour: h,
    trigger_minute: m,
    active_style_id: 'toxic',
    styles: [],
    skip_weekends: false,
    skip_holidays: false,
    save_local: true,
  }
}

function uid() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

function shortKey(k) {
  if (!k) return '未填 Key'
  if (k.length <= 8) return '••••'
  return k.slice(0, 3) + '…' + k.slice(-4)
}

function onMainNav(key) {
  mainKey.value = key
}

function onThemePreview() {
  const mode = form.appearance?.theme || 'system'
  if (setThemeMode) setThemeMode(mode)
  else applyTheme(mode)
}

function onAppearancePreview() {
  applyAppearance(form.appearance)
}

async function loadSystemStatus() {
  try {
    const data = await getSystemStatus()
    autostartEnabled.value = !!data?.autostart?.enabled
    form.appearance.autostart = !!data?.autostart?.preference
    const target = data?.autostart?.launch_target
    autostartHint.value = target ? `启动目标：${target}` : ''
    const opts = data?.include_options || []
    includeOptions.value = opts
    if (!exportInclude.value.length) {
      exportInclude.value = opts.filter((o) => o.default).map((o) => o.key)
    }
  } catch (e) {
    // 系统 API 不可用时不影响其它设置
    autostartHint.value = e?.message || '无法读取系统状态'
  }
}

async function onAutostartChange(val) {
  autostartLoading.value = true
  try {
    const data = await setAutostart(!!val)
    if (!data?.ok) {
      Message.error(data?.error || '自启设置失败')
      return
    }
    autostartEnabled.value = !!data.enabled
    form.appearance.autostart = !!data.preference
    Message.success(data.message || (val ? '已开启开机自启' : '已关闭开机自启'))
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '自启设置失败')
  } finally {
    autostartLoading.value = false
    await loadSystemStatus()
  }
}

async function onExportBackup() {
  if (!exportInclude.value.length) {
    Message.warning('请至少选择一项导出内容')
    return
  }
  if (exportInclude.value.includes('env')) {
    const ok = await new Promise((resolve) => {
      Modal.confirm({
        draggable: true,
        title: '包含密钥',
        content: '导出内容包含 .env（API Key 等）。请妥善保管备份文件，确认继续？',
        okText: '继续导出',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!ok) return
  }
  exportLoading.value = true
  try {
    const data = await exportBackup(exportInclude.value)
    if (!data?.ok) {
      Message.error(data?.message || '导出失败')
      return
    }
    lastExportPath.value = data.path || ''
    Message.success(`导出成功${data.path ? `：${data.path}` : ''}`)
  } catch (e) {
    Message.error(e?.response?.data?.message || e?.message || '导出失败')
  } finally {
    exportLoading.value = false
  }
}

async function onPackArchive() {
  archivePackLoading.value = true
  try {
    const data = await packArchive()
    if (!data?.ok) {
      Message.error(data?.message || '打包失败')
      return
    }
    lastExportPath.value = data.path || ''
    Message.success(`归档已打包${data.path ? `：${data.path}` : ''}`)
  } catch (e) {
    Message.error(e?.response?.data?.message || e?.message || '打包失败')
  } finally {
    archivePackLoading.value = false
  }
}

async function onImportBackup() {
  const path = (importPath.value || '').trim()
  if (!path) {
    Message.warning('请填写本机备份 zip 路径')
    return
  }
  const ok = await new Promise((resolve) => {
    Modal.confirm({
      draggable: true,
      title: '确认导入（替换）',
      content:
        '将用备份覆盖本地对应数据，并先自动生成安全备份。导入后建议刷新任务或重启应用。是否继续？',
      okText: '导入',
      okButtonProps: { status: 'warning' },
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
  if (!ok) return
  importLoading.value = true
  lastImportMsg.value = ''
  try {
    const data = await importBackup(path, {
      include: exportInclude.value.length ? exportInclude.value : undefined,
      safety_backup: true,
    })
    if (!data?.ok) {
      Message.error(data?.message || data?.error || '导入失败')
      lastImportMsg.value = data?.message || data?.error || ''
      return
    }
    lastImportMsg.value = [
      data.message,
      data.safety_backup ? `安全备份：${data.safety_backup}` : '',
    ]
      .filter(Boolean)
      .join(' ')
    Message.success(data.message || '导入成功')
    // 重新加载设置
    const s = await getSettings()
    normalizeLoaded(s)
    onThemePreview()
    await loadSystemStatus()
  } catch (e) {
    Message.error(e?.response?.data?.message || e?.response?.data?.error || e?.message || '导入失败')
  } finally {
    importLoading.value = false
  }
}

function addApiProfile() {
  const id = uid()
  form.ai.api_profiles.push({
    id,
    name: `配置${form.ai.api_profiles.length + 1}`,
    api_key: '',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4o',
  })
  if (!form.ai.active_api_id) form.ai.active_api_id = id
  // 展开新建项
  apiExpandKeys.value = [...(apiExpandKeys.value || []), id]
}

function removeApiProfile(id) {
  if (form.ai.api_profiles.length <= 1) return
  form.ai.api_profiles = form.ai.api_profiles.filter((p) => p.id !== id)
  if (form.ai.active_api_id === id) {
    form.ai.active_api_id = form.ai.api_profiles[0].id
  }
  apiExpandKeys.value = (apiExpandKeys.value || []).filter((k) => k !== id)
}

function normalizeLoaded(s) {
  Object.assign(form, emptyForm(), s)
  if (!form.ai) form.ai = emptyForm().ai
  if (!form.ai.api_profiles?.length) {
    form.ai.api_profiles = emptyForm().ai.api_profiles
    form.ai.active_api_id = form.ai.api_profiles[0].id
  }
  if (!form.ai.plan) form.ai.plan = emptyJob(8, 0)
  if (!form.ai.review) form.ai.review = emptyJob(23, 30)
  // 公休日：若仅一侧开启，展开为两边一致（以「都开」为准显示）
  for (const job of [form.ai.plan, form.ai.review]) {
    if (job.skip_weekends || job.skip_holidays) {
      // 保持各自值；UI 用 AND 显示，用户开公休日会两边都开
    }
  }
  if (!form.notification) form.notification = emptyForm().notification
  ensureFixedChannels(form.notification)
  if (!form.appearance) form.appearance = { theme: 'system', autostart: false }
  if (form.appearance.autostart == null) form.appearance.autostart = false
  if (form.appearance.motion == null) form.appearance.motion = 'full'
  if (form.appearance.shape == null) form.appearance.shape = 'round'
  if (form.appearance.skin !== 'neo' && form.appearance.skin !== 'aurora') form.appearance.skin = 'neo'
  if (!form.categories) form.categories = emptyForm().categories
  if (!Array.isArray(form.categories.primary_list)) form.categories.primary_list = []
  // 括号强制成对
  if (!WRAP_PRESETS.some(
    (w) => w.left === form.categories.wrap_left && w.right === form.categories.wrap_right,
  )) {
    form.categories.wrap_left = '['
    form.categories.wrap_right = ']'
  }
  if (!form.quick_add) form.quick_add = emptyForm().quick_add
  if (!form.polling) form.polling = emptyForm().polling
  if (!form.pomodoro) form.pomodoro = emptyForm().pomodoro
  if (!form.pomodoro.tray_display) form.pomodoro.tray_display = 'countdown'
  if (!form.pomodoro.tray_text) form.pomodoro.tray_text = '专注中'

  // 默认展开当前使用的 API
  if (form.ai.active_api_id) {
    apiExpandKeys.value = [form.ai.active_api_id]
  }
}

async function onSave() {
  ensureFixedChannels(form.notification)
  if (!form.ai.api_profiles.find((p) => p.id === form.ai.active_api_id)) {
    form.ai.active_api_id = form.ai.api_profiles[0]?.id || ''
  }
  form.nightly = {
    trigger_hour: form.ai.review.trigger_hour,
    trigger_minute: form.ai.review.trigger_minute,
    save_local: form.ai.review.save_local,
    skip_weekends: form.ai.review.skip_weekends,
    skip_holidays: form.ai.review.skip_holidays,
  }
  // 同步旧 notification 字段
  const wx = form.notification.channels.find((c) => c.type === 'wxpusher')
  if (wx) {
    form.notification.wxpusher_app_token = wx.wxpusher_app_token || ''
    form.notification.wxpusher_uid = wx.wxpusher_uid || ''
  }
  form.notification.enabled = form.notification.channels.some((c) => c.enabled)

  saving.value = true
  try {
    await saveSettings(form)
    onThemePreview()
    Message.success('设置已保存')
    closeHost({ action: 'settings_saved' })
  } catch (e) {
    Message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const s = await getSettings()
    normalizeLoaded(s)
    onThemePreview()
    await loadSystemStatus()
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
/* 整页不滚：仅右侧内容区滚动，左侧导航与 AI 标签固定 */
.settings-page {
  overflow: hidden;
}
.settings-page-body {
  overflow: hidden !important;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.settings-spin {
  width: 100%;
  height: 100%;
  min-height: 0;
  flex: 1;
  display: block;
}
.settings-spin :deep(.arco-spin) {
  width: 100%;
  height: 100%;
  display: block;
}
.settings-spin :deep(.arco-spin-children),
.settings-spin :deep(.arco-spin > div:last-child) {
  height: 100%;
  min-height: 0;
}
.settings-layout {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 16px;
  height: 100%;
  min-height: 0;
  align-items: stretch;
}
.nav-main {
  border-radius: var(--zt-radius-card);
  border: 1px solid var(--color-border-2);
  height: fit-content;
  max-height: 100%;
  align-self: start;
  position: sticky;
  top: 0;
  overflow: auto;
}
/* ---- 皮肤变体（body.zt-skin-* 门控） ---- */
/* Aurora：导航玻璃 + 激活项极光渐变拖尾 */
body.zt-skin-aurora .nav-main {
  border: 1px solid color-mix(in srgb, var(--color-text-primary) 9%, transparent);
  background: color-mix(in srgb, var(--color-surface) 55%, transparent);
  backdrop-filter: blur(18px) saturate(1.5);
  -webkit-backdrop-filter: blur(18px) saturate(1.5);
  box-shadow: 0 8px 32px rgba(2, 6, 23, 0.35),
    inset 0 1px 0 color-mix(in srgb, #ffffff 6%, transparent);
}
body.zt-skin-aurora .nav-main :deep(.arco-menu-selected) {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-primary) 22%, transparent),
    transparent
  );
}
/* Neo：设置页容器去描边纯阴影 */
body.zt-skin-neo .settings-page-body :deep(.arco-card) {
  border: none;
}
body.zt-skin-neo .settings-page-body :deep(.arco-collapse) {
  border: none;
  border-radius: var(--zt-radius-card);
  background: var(--color-surface);
  box-shadow: var(--zt-shadow-card);
}
body.zt-skin-neo .nav-main {
  border: none;
  box-shadow: var(--zt-shadow-card);
  background: var(--color-surface);
}
.settings-body {
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: auto;
}
/* 历史页：面板内部自滚动 */
.settings-body.is-history {
  overflow: hidden;
}
/* AI 页：标签栏固定，仅 pane 内容滚动 */
.settings-body.is-ai {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.settings-body.is-ai :deep(.ai-tabs),
.settings-body.is-ai :deep(.arco-tabs) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.settings-body.is-ai :deep(.arco-tabs-nav) {
  flex-shrink: 0;
  margin-bottom: 8px;
}
.settings-body.is-ai :deep(.arco-tabs-content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-top: 0;
}
.settings-body.is-ai :deep(.arco-tabs-content-list) {
  height: auto;
}
.section {
  max-width: 900px;
}
.hint {
  color: var(--color-text-3);
  font-size: 13px;
  margin: 0 0 12px;
}
.api-row-header,
.ch-row-header {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  flex-wrap: wrap;
  padding-right: 8px;
}
.api-name,
.ch-title {
  font-weight: 600;
  min-width: 72px;
}
.api-meta {
  color: var(--color-text-3);
  font-size: 12px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.api-edit-form,
.ch-body {
  max-width: 520px;
  padding-top: 4px;
}
.muted {
  color: var(--color-text-3);
  margin-left: 8px;
  font-size: 12px;
}
/* 紧凑设置页：标签左、控件右，一行一条 */
.compact-page {
  max-width: 420px;
}
.compact-block {
  margin: 0;
}
.compact-head {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--color-text-1);
}
.compact-sep {
  height: 1px;
  background: var(--color-border-2);
  margin: 14px 0;
}
.field-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.field-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
}
.field-k {
  font-size: 13px;
  color: var(--color-text-2);
  flex-shrink: 0;
}
.hint-sm {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--color-text-3);
  line-height: 1.4;
}
/* 分类页仍用 poll-block 类名 */
.poll-block {
  margin-bottom: 8px;
}
.block-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
}
.cat-page {
  max-width: 640px;
}
.cat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.cat-row-header {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  flex-wrap: wrap;
}
.sec-block {
  padding-top: 4px;
}
.sec-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.sec-row .arco-input-wrapper {
  flex: 1;
  max-width: 280px;
}
@media (max-width: 720px) {
  .settings-layout {
    grid-template-columns: 1fr;
  }
  .nav-main {
    position: static;
    max-height: none;
  }
}

/* 系统页 */
.system-settings {
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.sys-card :deep(.arco-card-body) {
  padding-top: 12px;
}
.sys-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.sys-title {
  font-weight: 600;
  font-size: 14px;
}
.sys-desc {
  margin-top: 4px;
  font-size: 13px;
  color: var(--color-text-3);
  line-height: 1.5;
}
.sys-hint {
  margin-top: 6px;
  font-size: 12px;
  word-break: break-all;
}
.sys-section-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.export-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  max-height: 220px;
  overflow-y: auto;
  padding-right: 8px;
  align-items: flex-start;
}

/* 让每个选项占最小宽度，避免过长 */
.export-checks .arco-checkbox-wrapper {
  flex: 0 0 auto;
  min-width: 140px;
}

/* 标签在右侧 */
.export-checks .arco-tag {
  margin-left: auto;
}
.sys-import-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.sys-import-row .arco-input-wrapper {
  flex: 1;
}
.sys-path {
  margin-top: 10px;
  font-size: 12px;
  color: var(--color-text-3);
  word-break: break-all;
}
.muted {
  color: var(--color-text-3);
}
</style>
