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
          <!-- 导航三组（UI 重构 P2）：日常 / 集成与通知 / 应用与数据 -->
          <a-menu-item-group title="日常工作">
            <a-menu-item key="polling">📋 任务</a-menu-item>
            <a-menu-item key="pomodoro">🍅 番茄钟</a-menu-item>
          </a-menu-item-group>
          <a-menu-item-group title="集成与通知">
            <a-menu-item key="ai">✨ AI 能力</a-menu-item>
            <a-menu-item key="notify">🔔 通知</a-menu-item>
            <a-menu-item key="ops">🧩 插件</a-menu-item>
          </a-menu-item-group>
          <a-menu-item-group title="应用与数据">
            <a-menu-item key="system">🖥️ 系统</a-menu-item>
            <a-menu-item key="backup">💾 备份</a-menu-item>
            <a-menu-item key="history">📜 历史</a-menu-item>
          </a-menu-item-group>
        </a-menu>

        <div class="settings-body" :class="{ 'is-history': mainKey === 'history' }">
          <template v-if="mainKey === 'ai'">
            <!-- ① 模型接入（前置条件，首块） -->
            <section class="zt-block">
              <div class="zt-block-head">
                <h3 class="zt-h3">模型接入</h3>
                <a-button
                  v-if="form.ai.api_profiles.length"
                  type="primary"
                  size="small"
                  @click="addApiProfile"
                >
                  ➕ 添加 API
                </a-button>
              </div>
              <p class="hint">
                可配置多个 API（名称区分），<b>同时只能启用一个</b>。点击行展开编辑。
              </p>

              <template v-if="form.ai.api_profiles.length">
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
                        <span
                          class="api-dot"
                          :class="{ on: form.ai.active_api_id === p.id }"
                          :title="form.ai.active_api_id === p.id ? '使用中' : '未启用'"
                        />
                        <span class="zt-h4">{{ p.name || '未命名' }}</span>
                        <span class="api-meta">{{ p.model || '—' }} · {{ shortKey(p.api_key) }}</span>
                        <a-button
                          v-if="form.ai.active_api_id !== p.id"
                          size="mini"
                          type="outline"
                          @click.stop="form.ai.active_api_id = p.id"
                        >
                          启用
                        </a-button>
                        <span v-else class="muted">当前</span>
                      </div>
                    </template>

                    <a-form layout="vertical" size="small" class="api-edit-form api-edit-grid">
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
                      <div class="api-edit-actions">
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
                      </div>
                    </a-form>
                  </a-collapse-item>
                </a-collapse>
              </template>
              <div v-else class="api-empty">
                <p class="hint">尚未配置模型 API——AI 功能需先在此接入一个可用 API。</p>
                <a-button type="primary" size="small" @click="addApiProfile">➕ 添加 API</a-button>
              </div>
            </section>

            <!-- ② 场景能力开关：卡片网格，默认全关 -->
            <section class="zt-block">
              <div class="zt-h3">场景能力</div>
              <div class="feat-grid">
                <div
                  v-for="f in AI_FEATURES"
                  :key="f.key"
                  class="feat-card"
                  :class="{ on: form.ai.features[f.key] }"
                >
                  <span class="feat-icon">{{ f.icon }}</span>
                  <div class="feat-info">
                    <span class="zt-h4">{{ f.name }}</span>
                    <span class="feat-desc">{{ f.desc }}</span>
                  </div>
                  <a-switch v-model="form.ai.features[f.key]" size="small" />
                </div>
              </div>
              <p class="hint">
                场景能力默认关闭；开启后立即出现在对应入口，模型调用复用上方「模型接入」中的当前 API。
              </p>
            </section>

            <!-- ③ 计划 / 复盘风格（调度已迁移为插件朝闻/暮省） -->
            <section class="zt-block">
              <div class="zt-h3">每日计划与复盘</div>
              <p class="hint">
                调度已迁移为插件：执行周期（日/周/月）、触发时间、跳过公休日等在
                设置 → 插件 → 已安装插件 →「朝闻 / 暮省」的参数预设中设置；此处维护各自的 AI 风格提示词。
              </p>
              <div class="ai-jobs">
                <div class="ai-job-col">
                  <div class="ai-job-head">
                    <span class="zt-h4">📋 朝闻 · 计划风格</span>
                  </div>
                  <JobEditor v-model="form.ai.plan" />
                </div>
                <div class="ai-job-col">
                  <div class="ai-job-head">
                    <span class="zt-h4">📝 暮省 · 复盘风格</span>
                  </div>
                  <JobEditor v-model="form.ai.review" />
                </div>
              </div>
            </section>
          </template>

          <!-- 通知：从 AI 页拆出的独立页（固定渠道，不可增删，可折叠） -->
          <template v-else-if="mainKey === 'notify'">
            <section class="zt-block" style="max-width: 900px">
              <div class="zt-h3">通知渠道</div>
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
                      <span class="zt-h4">{{ ch.name }}</span>
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
                  <a-form
                    v-else-if="ch.type === 'feishu_bot'"
                    layout="vertical"
                    size="small"
                    class="ch-body"
                  >
                    <a-form-item label="Webhook">
                      <a-input
                        v-model="ch.feishu_webhook"
                        placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                        :disabled="!ch.enabled"
                      />
                    </a-form-item>
                    <a-form-item label="签名密钥">
                      <a-input
                        v-model="ch.feishu_secret"
                        placeholder="签名密钥（未开启签名校验可留空）"
                        :disabled="!ch.enabled"
                      />
                    </a-form-item>
                    <a-alert type="info">
                      需在<strong>飞书群内</strong>接收（群设置-群机器人-添加自定义机器人获取
                      Webhook）；建议在飞书侧开启签名校验并填入密钥。
                    </a-alert>
                  </a-form>
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

            <!-- 插件报告通知格式 + 预览 -->
            <section class="zt-block" style="max-width: 900px">
              <div class="zt-h3">插件通知格式</div>
              <p class="hint">
                脚本运行完成通知的标题/正文模板。可用占位符：<code>{name}</code> 插件名 ·
                <code>{status}</code> 执行状态 · <code>{summary}</code> 摘要 ·
                <code>{result}</code> 结果正文（空时回退状态）。随「保存设置」生效。
              </p>
              <div class="field-table">
                <div class="field-line">
                  <span class="field-k">标题模板</span>
                  <a-input
                    v-model="form.notification.plugin_title_template"
                    size="small"
                    style="width: 360px"
                    placeholder="脚本: {name}"
                  />
                </div>
                <div class="field-line" style="align-items: flex-start">
                  <span class="field-k">正文模板</span>
                  <a-textarea
                    v-model="form.notification.plugin_body_template"
                    :auto-size="{ minRows: 2, maxRows: 5 }"
                    style="width: 360px"
                    placeholder="{result}"
                  />
                </div>
              </div>
              <div class="zt-h4" style="margin-top: 12px">预览</div>
              <div
                style="
                  margin-top: 6px;
                  padding: 10px 12px;
                  border: 1px solid var(--color-border-2);
                  border-radius: 8px;
                  background: var(--color-fill-1);
                  max-width: 420px;
                "
              >
                <div class="zt-h4">{{ notifyPreviewTitle }}</div>
                <pre class="hint" style="margin: 4px 0 0; white-space: pre-wrap; font-family: inherit">{{ notifyPreviewBody }}</pre>
              </div>
            </section>
          </template>

          <template v-else-if="mainKey === 'polling'">
            <div class="zt-stack">
            <!-- 页内分组（UI 重构 P2）：录入 / 集成 / 托盘与分类 -->
            <div class="zt-group">
              <h3 class="zt-h3">录入</h3>
              <section class="zt-block">
              <div class="zt-h3">新建任务</div>
              <div class="field-table">
                <div class="field-line">
                  <span class="field-k">打开新建任务表单</span>
                  <a-button type="primary" size="small" @click="goNewTask">＋ 新建任务</a-button>
                </div>
              </div>
            </section>

              <section class="zt-block">
              <div class="zt-h3">闪电添加</div>
              <div class="field-table">
                <div class="field-line">
                  <span class="field-k">启用全局快捷键</span>
                  <a-switch v-model="form.quick_add.enabled" />
                </div>
                <template v-if="form.quick_add.enabled">
                  <div class="field-line">
                    <span class="field-k">快捷键</span>
                    <a-input v-model="form.quick_add.hotkey" placeholder="<ctrl>+<alt>+t（留空 = 默认）" style="max-width: 220px" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">默认分类</span>
                    <a-input v-model="form.quick_add.default_category" style="max-width: 220px" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">默认优先级</span>
                    <a-select v-model="form.quick_add.default_priority" style="width: 120px">
                      <a-option value="high">高</a-option>
                      <a-option value="medium">中</a-option>
                      <a-option value="low">低</a-option>
                    </a-select>
                  </div>
                </template>
              </div>
              <span class="hint">快捷键格式如 &lt;ctrl&gt;+&lt;alt&gt;+t（macOS 如 &lt;alt&gt;+&lt;space&gt;）；随「保存设置」生效；与系统/输入法同键位冲突时换组合。</span>
            </section>

            </div>
            <div class="zt-group">
              <h3 class="zt-h3">集成</h3>
              <section class="zt-block">
              <div class="zt-h3">飞书同步</div>
              <div class="field-table">
                <div class="field-line">
                  <span class="field-k">启用飞书同步</span>
                  <a-switch v-model="form.feishu_sync.enabled" />
                </div>
                <span class="hint">
                  把任务单向推送到飞书「ZenTray」日历与任务清单（完成/删除自动撤下，不回读）；
                  需飞书开放平台自建应用，<a class="doc-link" @click.prevent="openFeishuDoc">配置步骤见文档</a>。
                  改动随「保存设置」生效。
                </span>
                <template v-if="form.feishu_sync.enabled">
                  <div class="field-line">
                    <span class="field-k">App ID</span>
                    <a-input v-model="form.feishu_sync.app_id" placeholder="cli_a…（自建应用凭证）" style="max-width: 220px" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">App Secret</span>
                    <a-input-password v-model="form.feishu_sync.app_secret" placeholder="自建应用密钥" style="max-width: 220px" allow-clear />
                  </div>
                  <div class="field-line">
                    <span class="field-k">同步日程到日历</span>
                    <a-switch v-model="form.feishu_sync.sync_calendar" size="small" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">同步任务到清单</span>
                    <a-switch v-model="form.feishu_sync.sync_tasks" size="small" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">接收人 Open ID</span>
                    <a-input v-model="form.feishu_sync.feishu_user_id" placeholder="可选，用于日历共享/任务指派" style="max-width: 220px" allow-clear />
                  </div>
                  <div class="field-line">
                    <span class="field-k">连接与同步</span>
                    <a-space size="small">
                      <a-button size="small" :loading="feishuTesting" :disabled="!form.feishu_sync.app_id || !form.feishu_sync.app_secret" @click="onFeishuTest">
                        测试连接
                      </a-button>
                      <a-button size="small" :loading="feishuResyncing" @click="onFeishuResync">
                        全量重同步
                      </a-button>
                    </a-space>
                  </div>
                  <div v-if="feishuStatusText" class="field-line">
                    <span class="field-k">同步状态</span>
                    <span class="hint" :style="form.feishu_sync.last_error ? 'color: #f53f3f' : ''">{{ feishuStatusText }}</span>
                  </div>
                </template>
              </div>
              <span v-if="form.feishu_sync.enabled" class="hint">「测试连接 / 全量重同步」会先保存本卡片配置再执行；全量重同步不清远端旧对象，需要干净重来时先在飞书侧清空 ZenTray 日历/清单。</span>
            </section>

              <section class="zt-block">
              <div class="zt-h3">系统日历</div>
              <div class="field-table">
                <div class="field-line">
                  <span class="field-k">自动同步到系统日历</span>
                  <a-switch v-model="form.calendar.enabled" />
                </div>
                <span class="hint">
                  开启后任务增删改与周期模板变更自动重写日历源文件，日历应用订阅该文件即保持同步
                  （Linux Evolution/KOrganizer 订阅本地文件、macOS 日历「新建日历订阅」粘贴链接）；
                  Windows Outlook 不支持文件订阅，用「导出一次」手动导入。改动随「保存设置」生效。
                </span>
                <template v-if="form.calendar.enabled">
                  <div class="field-line">
                    <span class="field-k">源文件</span>
                    <span class="hint" style="word-break: break-all">{{ calendarFeedPath || '…' }}</span>
                  </div>
                  <div class="field-line">
                    <span class="field-k">订阅与导出</span>
                    <a-space size="small">
                      <a-button size="small" @click="onCalendarOpenFolder">打开所在文件夹</a-button>
                      <a-button size="small" @click="onCalendarCopyLink">复制订阅链接</a-button>
                      <a-button size="small" :loading="calendarExporting" @click="onCalendarExport">导出一次</a-button>
                    </a-space>
                  </div>
                </template>
              </div>
            </section>

            </div>
            <div class="zt-group">
              <h3 class="zt-h3">托盘与分类</h3>
              <div class="zt-stack" style="max-width: 420px">
              <section class="zt-block">
                <div class="zt-h3">轮播设置</div>
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

              <section class="zt-block">
                <div class="zt-h3">逾期设置</div>
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

              <div class="zt-stack" style="max-width: 640px">
              <section class="zt-block">
                <h3 class="zt-h3">标题格式</h3>
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


              <section class="zt-block">
                <div class="cat-head">
                  <h3 class="zt-h3" style="margin: 0">一级分类</h3>
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
            </div>
            </div>
          </template>

          <template v-else-if="mainKey === 'pomodoro'">
            <div class="pomo-grid">
              <section class="zt-block is-wide">
                <div class="zt-block-head">
                  <h3 class="zt-h3">专注节奏</h3>
                  <a-space size="mini">
                    <a-tag
                      v-for="preset in POMO_PRESETS"
                      :key="preset.key"
                      class="pomo-preset"
                      :class="{ on: activePreset === preset.key }"
                      size="small"
                      @click="applyPomodoroPreset(preset.focus, preset.short, preset.long)"
                    >
                      {{ preset.label }}
                    </a-tag>
                  </a-space>
                </div>
                <div class="pomo-dials">
                  <div class="pomo-dial">
                    <NumberSpinner v-model="form.pomodoro.duration_minutes" :min="1" :max="180" suffix="分" />
                    <div class="pomo-dial-k">专注时长</div>
                  </div>
                  <div class="pomo-dial">
                    <NumberSpinner v-model="form.pomodoro.short_break_minutes" :min="1" :max="60" suffix="分" />
                    <div class="pomo-dial-k">短休时长</div>
                  </div>
                  <div class="pomo-dial">
                    <NumberSpinner v-model="form.pomodoro.long_break_minutes" :min="1" :max="60" suffix="分" />
                    <div class="pomo-dial-k">长休时长</div>
                  </div>
                  <div class="pomo-dial">
                    <NumberSpinner v-model="form.pomodoro.long_break_every" :min="0" :max="12" suffix="个" />
                    <div class="pomo-dial-k">长休间隔</div>
                    <div class="hint">每 N 个专注进长休，0 = 只用短休</div>
                  </div>
                </div>
              </section>

              <section class="zt-block">
                <div class="zt-h3">专注行为</div>
                <div class="field-table">
                  <div class="field-line">
                    <span class="field-k">延长步长</span>
                    <NumberSpinner v-model="form.pomodoro.extend_minutes" :min="1" :max="60" suffix="分" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">专注结束自动休息</span>
                    <a-switch v-model="form.pomodoro.auto_start_breaks" size="small" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">休息结束自动专注</span>
                    <a-switch v-model="form.pomodoro.auto_start_focus" size="small" />
                  </div>
                  <div class="field-line">
                    <span class="field-k">每日目标</span>
                    <NumberSpinner v-model="form.pomodoro.daily_goal_pomodoros" :min="0" :max="50" suffix="个" />
                    <span class="hint">达标当次通知，0 = 不启用</span>
                  </div>
                </div>
              </section>

              <section class="zt-block">
                <div class="zt-h3">托盘与菜单</div>
                <p class="hint">
                  左侧专注为番茄饼图、休息为茶绿饼图；右侧可选倒计时或文案（休息恒为倒计时）。托盘菜单「专注」按钮空闲时融合今日统计。
                </p>
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
                  <div class="field-line">
                    <span class="field-k">图标叠加倒计时</span>
                    <a-switch v-model="form.pomodoro.tray_icon_countdown" size="small" />
                    <span class="hint">Windows：饼图内叠加剩余分钟数字</span>
                  </div>
                  <div class="field-line pomo-menu-line">
                    <span class="field-k">按钮文案</span>
                    <a-input
                      v-model="form.pomodoro.menu_label_format"
                      size="small"
                      placeholder="🍅 专注{focus}mins -- 今日{today}mins"
                      :max-length="64"
                    />
                  </div>
                  <p class="hint">占位符：{focus}=本次专注分钟、{today}=今日专注分钟、{count}=今日番茄数。</p>
                </div>
              </section>
            </div>
          </template>

          <template v-else-if="mainKey === 'ops'">
            <div class="zt-stack plugin-settings">
              <!-- 总开关走页面底部「保存设置」 -->
              <section class="zt-block">
  <div class="zt-h3">总开关</div>
                <div class="plugin-switch-row">
                  <div>
                    <div class="plugin-title">启用插件</div>
                    <div class="plugin-desc">
                      开启后，托盘菜单顶部显示「🧩 插件」子菜单；目录恒扫描，
                      仅加载通过 <code>plugin.yaml</code> 校验的插件。
                    </div>
                  </div>
                  <a-switch v-model="form.ops.enabled" />
                </div>
                <div class="plugin-switch-row" style="margin-top: 14px">
                  <div>
                    <div class="plugin-title">运行报告托盘轮播</div>
                    <div class="plugin-desc">
                      脚本完成通知未点击查看时，报告提示进入顶栏任务轮播，到期自动退出。
                    </div>
                  </div>
                  <a-space size="small">
                    <a-input-number
                      v-model="form.ops.report_tray_minutes"
                      :min="1"
                      :max="1440"
                      :step="5"
                      size="small"
                      style="width: 104px"
                      :disabled="!form.ops.report_tray_enabled"
                    />
                    <span class="plugin-desc">分钟</span>
                    <a-switch v-model="form.ops.report_tray_enabled" />
                  </a-space>
                </div>
                <a-divider style="margin: 10px 0" />
                <div class="plugin-desc">
                  报告通知渠道已改为插件级：在各插件「编辑」面板中单独选择，选项来自 设置 → 🔔 通知 中已开启的渠道。
                </div>
              </section>

              <!-- 已安装插件：行精简为四动作（说明/参数预设/编辑/删除），展开面板编辑+预设+授权 -->
              <section class="zt-block">
                <div class="zt-block-head">
                  <div class="zt-h3">
                    已安装插件
                    <a-tag size="small" color="arcoblue">{{ opsItems.length }}</a-tag>
                  </div>
                  <a-button size="mini" type="text" :loading="opsListLoading" @click="refreshOpsPlugins">刷新</a-button>
                </div>

                <div v-if="opsSortedByName.length" class="plug-list">
                  <div v-for="p in opsSortedByName" :key="p.id" class="plug-item">
                    <div class="plug-row">
                      <span class="zt-h4">{{ p.name }}</span>
                      <a-tag size="small" :color="p.type === 'service' ? 'orangered' : 'green'">
                        {{ p.type === 'service' ? '服务' : '脚本' }}
                      </a-tag>
                      <a-tag v-if="p.category" size="small" color="cyan">{{ p.category }}</a-tag>
                      <a-tag v-if="p.write_back" size="small" color="purple">结果写回任务</a-tag>
                      <a-tag v-for="(t, i) in p.manifest_triggers" :key="i" size="small" color="arcoblue">{{ trigLabel(t) }}</a-tag>
                      <div class="plug-actions">
                        <a-button size="mini" type="text" @click.stop="opsDocPlugin = p">说明</a-button>
                        <a-button size="mini" type="text" :disabled="!p.params?.length" @click="toggleOpsEdit(p)">参数预设</a-button>
                        <a-button size="mini" type="text" @click="toggleOpsEdit(p)">编辑</a-button>
                        <a-popconfirm
                          :content="p.source === 'bundled'
                            ? `删除示例插件「${p.name}」？安装文件保留，重新导入可恢复。`
                            : `删除「${p.name}」？将移除插件目录，不可恢复。`"
                          ok-text="删除"
                          position="tr"
                          @ok="onOpsDelete(p)"
                        >
                          <a-button size="mini" type="text" status="danger">删除</a-button>
                        </a-popconfirm>
                      </div>
                    </div>

                    <!-- 展开面板：编辑 / 参数预设 / 自动运行授权（编辑与参数预设共用同一面板） -->
                    <div v-if="opsEditOpen[p.id]" class="plug-expand">
                      <div class="plug-edit-sec">
                        <div class="plug-edit-head">
                          <b>名称 / 简介</b>
                          <span class="pc-muted">（保存后改写 plugin.yaml，立即生效<template v-if="p.source === 'bundled'">；示例插件保存时复制到用户插件目录</template>）</span>
                        </div>
                        <div class="preset-row">
                          <span class="preset-k">名称</span>
                          <a-input v-model="metaDrafts[p.id].name" size="small" style="width: 320px" @press-enter="savePluginMeta(p)" />
                        </div>
                        <div class="preset-row">
                          <span class="preset-k">简介</span>
                          <a-input v-model="metaDrafts[p.id].description" size="small" style="width: 320px" maxlength="200" @press-enter="savePluginMeta(p)" />
                        </div>
                        <div class="trig-actions">
                          <a-button size="small" type="primary" :loading="opsMetaSaving === p.id" @click="savePluginMeta(p)">保存</a-button>
                        </div>
                        <div class="pc-muted plug-meta-line">
                          {{ p.type === 'service' ? '服务' : '脚本' }} · 来源 {{ p.source === 'bundled' ? '内置示例' : '用户安装' }} · 版本 {{ p.version || '—' }}
                        </div>
                      </div>

                      <div v-if="p.params?.length" class="plug-edit-sec">
                        <div class="plug-edit-head">
                          <b>参数预设</b>
                          <span class="pc-muted">（运行时预填，可临时修改）</span>
                        </div>
                        <div v-for="prm in p.params" :key="prm.name" class="preset-row">
                          <span class="preset-k" :title="prm.description || prm.name">
                            {{ prm.description || prm.name }}
                          </span>
                          <!-- 可变长度参数：默认一行，「＋ 加一条」增行 -->
                          <div v-if="prm.variadic" class="preset-many">
                            <div v-for="(_, vi) in presetDrafts[p.id][prm.name]" :key="vi" class="preset-many-row">
                              <a-input v-model="presetDrafts[p.id][prm.name][vi]" size="small" style="width: 260px" :placeholder="`缺省 ${prm.default || '空'}`" />
                              <a-button
                                v-if="presetDrafts[p.id][prm.name].length > 1"
                                size="mini" type="text" status="danger"
                                @click="presetDrafts[p.id][prm.name].splice(vi, 1)"
                              >删除</a-button>
                            </div>
                            <a-button size="mini" @click="presetDrafts[p.id][prm.name].push('')">＋ 加一条</a-button>
                          </div>
                          <a-input v-else v-model="presetDrafts[p.id][prm.name]" size="small" style="width: 260px" :placeholder="`缺省 ${prm.default || '空'}`" />
                        </div>
                        <div class="trig-actions">
                          <a-button size="small" type="primary" :loading="opsPresetSaving === p.id" @click="saveParamPreset(p)">保存预设</a-button>
                        </div>
                      </div>

                      <div class="plug-edit-sec">
                        <div class="plug-edit-head">
                          <b>报告通知渠道</b>
                          <span class="pc-muted">（随「保存设置」生效）</span>
                        </div>
                        <a-select
                          multiple
                          allow-clear
                          size="small"
                          style="width: 320px"
                          :model-value="form.ops.plugin_notify_channels?.[p.id] || []"
                          :options="enabledChannelOptions"
                          placeholder="跟随通知设置已启用渠道"
                          @change="(v) => setPluginChannels(p.id, v)"
                        />
                        <div class="hint" style="margin-top: 4px">
                          选项来自 设置 → 🔔 通知 中已开启的渠道（先在那里启用）；不选 = 跟随已启用渠道
                        </div>
                      </div>

                      <div v-if="p.manifest_triggers?.length" class="plug-edit-sec">
                        <div class="plug-edit-head">
                          <b>自动运行授权</b>
                        </div>
                        <div class="field-line">
                          <span class="field-k">允许自动运行（{{ p.manifest_triggers.map(trigLabel).join('；') }}）</span>
                          <a-switch
                            size="small"
                            :model-value="p.authorized === true"
                            :disabled="!opsListEnabled || opsAuthBusy === p.id"
                            @change="(v) => onOpsAuthorize(p, v)"
                          />
                        </div>
                        <div class="hint">关闭后该插件不再自动执行，可随时重新开启</div>
                      </div>
                    </div>
                  </div>
                </div>
                <a-empty v-else description="暂无已加载插件，可在下方导入" />

                <div v-if="opsFailures.length" class="plug-fail-box">
                  <div class="plug-fail-title">校验失败（未加载）</div>
                  <div v-for="(f, i) in opsFailures" :key="i" class="plug-fail-item">
                    <code>{{ f.path }}</code>
                    <ul>
                      <li v-for="(e, j) in f.errors" :key="j">{{ e }}</li>
                    </ul>
                  </div>
                </div>
              </section>

              <!-- 导入插件：两行收敛（模式+路径+选择 / 预览+安装） -->
              <section class="zt-block">
                <div class="zt-h3">导入插件</div>
                <div class="pc-add-row">
                  <a-radio-group v-model="plugImportMode" type="button" size="small">
                    <a-radio value="dir">目录</a-radio>
                    <a-radio value="zip">zip 包</a-radio>
                  </a-radio-group>
                  <a-input
                    v-model="plugImportPath"
                    :placeholder="plugImportMode === 'zip' ? '本机 zip 包路径，或点右侧选择' : '插件目录路径（含 plugin.yaml），默认为内置插件目录'"
                    allow-clear
                    @press-enter="plugOnImportPreview"
                  />
                  <a-button @click="plugOnImportPick">
                    {{ plugImportMode === 'zip' ? '选择文件' : '选择目录' }}
                  </a-button>
                </div>
                <div class="pc-add-row plug-import-actions">
                  <a-button type="outline" :loading="plugImportPreviewing" @click="plugOnImportPreview">预览校验</a-button>
                  <a-button
                    type="primary"
                    :loading="plugImportInstalling"
                    :disabled="!plugImportPreview?.ok"
                    @click="plugOnImportInstall"
                  >
                    安装
                  </a-button>
                </div>

                <div v-if="plugImportPreview" class="pc-preview" :class="{ ok: plugImportPreview.ok, bad: !plugImportPreview.ok }">
                  <div class="pc-preview-head">
                    <a-tag :color="plugImportPreview.ok ? 'green' : 'red'" size="small">
                      {{ plugImportPreview.ok ? '校验通过，可以安装' : '校验失败' }}
                    </a-tag>
                    <span class="pc-muted">{{ plugImportPreview.path }}</span>
                  </div>
                  <a-descriptions v-if="plugImportPreview.ok && plugImportPreview.preview" :column="2" size="small" bordered>
                    <a-descriptions-item label="名称">{{ plugImportPreview.preview.name }}</a-descriptions-item>
                    <a-descriptions-item label="ID">{{ plugImportPreview.preview.id }}</a-descriptions-item>
                    <a-descriptions-item label="类型">{{ plugImportPreview.preview.type }}</a-descriptions-item>
                    <a-descriptions-item label="版本">{{ plugImportPreview.preview.version }}</a-descriptions-item>
                    <a-descriptions-item label="说明" :span="2">
                      {{ plugImportPreview.preview.description || '—' }}
                    </a-descriptions-item>
                  </a-descriptions>
                  <ul v-if="plugImportPreview.errors?.length" class="pc-err-list">
                    <li v-for="(e, i) in plugImportPreview.errors" :key="i">{{ e }}</li>
                  </ul>
                </div>

                <a-collapse :bordered="false" class="pc-advanced">
                  <a-collapse-item key="adv" header="高级：用户插件目录（安装目标）">
                    <div class="pc-add-row">
                      <a-input v-model="opsUserDir" :placeholder="opsUserDirHint || '留空 = 数据目录/plugins'" allow-clear />
                      <a-button :loading="opsDirSaving" @click="onSaveOpsUserDir">保存目录</a-button>
                    </div>
                  </a-collapse-item>
                </a-collapse>
              </section>
            </div>
          </template>

          <template v-else-if="mainKey === 'system'">
            <div class="zt-stack system-settings">
            <!-- 页内分组（UI 重构 P2）：外观 / 系统行为 / 软件更新 -->
            <div class="zt-group">
              <h3 class="zt-h3">外观</h3>
              <section class="zt-block">
                <a-form layout="vertical" style="max-width: 420px">
                  <a-form-item>
                    <template #label>主题 <span class="zt-instant">即时</span></template>
                    <a-radio-group v-model="form.appearance.theme" @change="onThemePreview">
                      <a-radio value="system">跟随系统</a-radio>
                      <a-radio value="light">浅色</a-radio>
                      <a-radio value="dark">深色</a-radio>
                    </a-radio-group>
                  </a-form-item>
                  <a-form-item>
                    <template #label>界面皮肤 <span class="zt-instant">即时</span></template>
                    <a-radio-group v-model="form.appearance.skin" @change="onAppearancePreview">
                      <a-radio value="neo">Neo</a-radio>
                      <a-radio value="aurora">Aurora</a-radio>
                      <a-radio value="synth">霓虹 Synth</a-radio>
                      <a-radio value="clay">黏土 Clay</a-radio>
                    </a-radio-group>
                  </a-form-item>
                  <a-form-item>
                    <template #label>界面动效 <span class="zt-instant">即时</span></template>
                    <a-switch
                      v-model="form.appearance.motion"
                      checked-value="full"
                      unchecked-value="off"
                      checked-text="开"
                      unchecked-text="关"
                      @change="onAppearancePreview"
                    />
                  </a-form-item>
                  <a-form-item>
                    <template #label>形状风格 <span class="zt-instant">即时</span></template>
                    <a-radio-group v-model="form.appearance.shape" @change="onAppearancePreview">
                      <a-radio value="round">圆润</a-radio>
                      <a-radio value="crisp">利落</a-radio>
                    </a-radio-group>
                  </a-form-item>
                  <a-alert type="info">主题预览立即生效；点底部「保存设置」写入配置。</a-alert>
                </a-form>
              </section>

              </div>
            <div class="zt-group">
              <h3 class="zt-h3">系统行为</h3>
              <section class="zt-block">
                <div class="zt-h3">启动</div>
                <div class="sys-row">
                  <div>
                    <div class="zt-h4">开机自启 <span class="zt-instant">即时</span></div>
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
              </section>

              <!-- Windows 状态条（任务栏正上方，设计 §3.0）；非 Windows 整块隐藏 -->
              <section v-if="statusbarSupported" class="zt-block">
                <div class="zt-h3">状态条显示（Windows）</div>
                <div class="sys-row">
                  <div>
                    <div class="zt-h4">任务栏正上方状态条</div>
                    <div class="sys-desc">
                      任务栏上缘常驻全宽条带：动态图标 + 完整任务标题不截断，左键=速览面板、右键=菜单；
                      系统级保留，最大化窗口自动避让，不依赖任务栏合并模式。关闭则退回仅通知区图标。
                    </div>
                  </div>
                  <a-switch v-model="form.appearance.statusbar_enabled" />
                </div>
                <div class="field-table" style="margin-top: 12px">
                  <div class="field-line">
                    <span class="field-k">超宽标题跑马灯</span>
                    <a-switch v-model="form.appearance.statusbar_marquee" size="small" />
                  </div>
                </div>
                <p class="sys-desc" style="margin-top: 10px">超宽标题默认尾部省略号；跑马灯开启后整条滚动。改动随底部「保存设置」生效。</p>
              </section>
              </div>

              <div class="zt-group">
              <h3 class="zt-h3">软件更新</h3>
              <section class="zt-block">
                <div class="sys-row">
                  <div>
                    <div class="zt-h4">当前版本 v{{ appVersion || '…' }}</div>
                    <a-alert v-if="upd.result && !upd.result.has_update" type="success" class="upd-alert">
                      已是最新版本 v{{ upd.result.version }}
                    </a-alert>
                    <a-alert v-if="upd.result && upd.result.has_update" type="warning" class="upd-alert">
                      发现新版本 v{{ upd.result.version }}（{{ (upd.result.asset_size / 1048576).toFixed(1) }}MB）
                      <a :href="upd.result.notes_url" target="_blank" rel="noreferrer" style="margin-left: 8px">查看发布说明</a>
                    </a-alert>
                    <a-alert v-if="upd.error" type="error" class="upd-alert">{{ upd.error }}</a-alert>
                    <!-- Arco progress 百分比取 0~1，后端 0~100 需除 100 -->
                    <a-progress
                      v-if="upd.state === 'downloading' || upd.state === 'ready'"
                      :percent="upd.progress / 100"
                      size="small"
                      style="max-width: 320px; margin-top: 4px"
                    />
                  </div>
                  <div class="upd-actions">
                    <a-button :loading="upd.checking" @click="onUpdatesCheck">检查更新</a-button>
                    <a-button
                      v-if="upd.result && upd.result.has_update && upd.state !== 'downloading' && upd.state !== 'ready'"
                      type="primary"
                      @click="onUpdatesDownload"
                    >
                      下载更新
                    </a-button>
                    <a-button v-if="upd.state === 'ready'" type="primary" status="warning" @click="onUpdatesInstall">
                      安装并重启
                    </a-button>
                  </div>
                </div>
                <div class="field-line" style="margin-top: 8px">
                  <span class="field-k">下载代理</span>
                  <a-input
                    v-model="form.update.proxy"
                    placeholder="http://127.0.0.1:7897（访问 GitHub 失败时填写，留空直连）"
                    style="max-width: 320px"
                  />
                </div>
              </section>
              </div>
            </div>
          </template>

          <!-- 备份：五块（存储目录 / 手动备份 / 自动策略 / 恢复 / 历史快照） -->
          <template v-else-if="mainKey === 'backup'">
            <div class="zt-stack system-settings">
              <section class="zt-block">
  <div class="zt-h3">备份存储目录</div>
                <div class="sys-row">
                  <div style="min-width: 0">
                    <div class="zt-h4">
                      {{ backupDirDirty ? '待保存' : backupStatus.custom ? '自定义目录' : '默认目录' }}
                      <a-tag v-if="backupDirDirty" size="small" color="orange">未保存</a-tag>
                    </div>
                    <div class="sys-path"><code>{{ backupDirDisplay }}</code></div>
                    <div class="sys-hint muted">
                      更改后需点底部「保存设置」生效；手动/自动备份与历史快照均写入此目录。
                    </div>
                  </div>
                  <a-space>
                    <a-button :disabled="!backupDirDisplay" @click="onChangeBackupDir">更改目录</a-button>
                    <a-button v-if="form.backup.dir" @click="form.backup.dir = ''">恢复默认</a-button>
                  </a-space>
                </div>
              </section>

              <section class="zt-block">
  <div class="zt-h3">手动即时备份</div>
                <div class="sys-section-label">备份内容</div>
                <a-checkbox-group v-model="exportInclude" direction="vertical" class="export-checks">
                  <a-checkbox v-for="opt in includeOptions" :key="opt.key" :value="opt.key">
                    {{ opt.label }}
                    <a-tag v-if="opt.sensitive" size="small" color="orangered" style="margin-left: 6px">
                      含密钥
                    </a-tag>
                  </a-checkbox>
                </a-checkbox-group>

                <div class="sys-section-label" style="margin-top: 14px">密码加密（AES-256）</div>
                <div class="bk-inline">
                  <a-switch v-model="encryptEnabled" size="small" />
                  <a-input-password
                    v-if="encryptEnabled"
                    v-model="backupPassword"
                    placeholder="备份密码（恢复时需输入）"
                    style="width: 240px"
                    allow-clear
                  />
                </div>

                <a-space style="margin-top: 14px" wrap>
                  <a-button type="primary" :loading="exportLoading" @click="onExportBackup">
                    立即备份
                  </a-button>
                  <a-button :loading="saveAsLoading" @click="onExportSaveAs">另存为…</a-button>
                  <a-button :loading="archivePackLoading" @click="onPackArchive">仅打包归档</a-button>
                </a-space>
                <p v-if="lastExportPath" class="sys-path">
                  最近导出：<code>{{ lastExportPath }}</code>
                </p>
              </section>

              <section class="zt-block">
  <div class="zt-h3">自动周期备份策略</div>
                <div class="sys-row">
                  <div>
                    <div class="zt-h4">自动备份</div>
                    <div class="sys-desc">
                      按周期自动全量备份（明文，默认六项）。到点未开机会在下次启动后补跑；改动需点底部保存。
                    </div>
                  </div>
                  <a-switch v-model="form.backup.auto_enabled" />
                </div>
                <div v-if="form.backup.auto_enabled" class="bk-policy">
                  <span class="bk-policy-k">频率</span>
                  <a-select
                    v-model="form.backup.interval_days"
                    size="small"
                    style="width: 100px"
                    :options="[
                      { label: '每天', value: 1 },
                      { label: '每 3 天', value: 3 },
                      { label: '每周', value: 7 },
                    ]"
                  />
                  <span class="bk-policy-k">保留份数</span>
                  <a-input-number v-model="form.backup.keep" :min="1" :max="50" size="small" style="width: 88px" />
                  <span class="bk-policy-k">备份时刻</span>
                  <a-select v-model="form.backup.trigger_hour" size="small" style="width: 84px" :options="HOUR_OPTS" />
                </div>
                <p class="sys-hint muted">
                  上次自动备份：{{ backupStatus.last_backup_at || '尚未自动备份' }}。
                  轮转仅清理自动备份自身（zentray-auto-*），不影响手动导出。
                </p>
              </section>

              <section class="zt-block">
  <div class="zt-h3">从备份文件恢复</div>
                <div class="sys-import-row">
                  <a-input
                    v-model="importPath"
                    placeholder="本机 zip 绝对路径，或点右侧按钮选择"
                    allow-clear
                    @clear="importNeedsPassword = false"
                  />
                  <a-button @click="onPickBackupFile">选择文件</a-button>
                  <a-button :loading="previewLoading" @click="loadImportPreview">预览内容</a-button>
                  <a-button type="primary" status="warning" :loading="importLoading" @click="onImportBackup">
                    恢复
                  </a-button>
                </div>
                <div v-if="importNeedsPassword" class="bk-inline" style="margin-top: 10px">
                  <span class="bk-policy-k">备份密码</span>
                  <a-input-password v-model="importPassword" placeholder="该备份已加密" style="width: 240px" allow-clear />
                </div>
                <template v-if="importPreviewData">
                  <div class="sys-section-label" style="margin-top: 12px">选择要恢复的内容</div>
                  <a-tree
                    v-model:checked-keys="importChecked"
                    :data="importTree"
                    :default-expanded-keys="importTreeExpanded"
                    checkable
                    :selectable="false"
                    size="small"
                  />
                  <p v-if="importTplHint" class="sys-hint muted">{{ importTplHint }}</p>
                  <p class="sys-hint muted">
                    勾选父项 = 整类替换；勾选子项 = 仅替换对应分区，其余保持本地现状。
                  </p>
                  <p v-if="importPreviewData.manifest" class="sys-hint muted">
                    备份时间 {{ importPreviewData.manifest.created_at || '未知' }} ·
                    生成版本 v{{ importPreviewData.manifest.app_version || '?' }}
                  </p>
                </template>
                <a-alert type="warning" style="margin-top: 10px">
                  恢复为<strong>替换</strong>模式：覆盖本地所选数据；操作前会自动写入安全备份。
                </a-alert>
                <p v-if="lastImportMsg" class="sys-path">{{ lastImportMsg }}</p>
              </section>

              <section class="zt-block bk-snapshots">
                <div class="zt-block-head">
                  <h3 class="zt-h3">历史备份快照</h3>
                  <a-space>
                    <a-tag size="small">{{ snapshots.length }} 个备份</a-tag>
                    <a-button size="small" :loading="snapshotsLoading" @click="loadBackups">刷新</a-button>
                  </a-space>
                </div>
                <a-table
                  :data="snapshots"
                  :loading="snapshotsLoading"
                  :pagination="snapshots.length > 8 ? { pageSize: 8 } : false"
                  size="small"
                  :scroll="{ x: 620 }"
                >
                  <template #columns>
                    <a-table-column title="文件名" data-index="name" :width="240">
                      <template #cell="{ record }">
                        <span class="bk-name" :title="record.name">{{ record.name }}</span>
                      </template>
                    </a-table-column>
                    <a-table-column title="大小" :width="84">
                      <template #cell="{ record }">{{ fmtSize(record.size) }}</template>
                    </a-table-column>
                    <a-table-column title="时间" :width="150">
                      <template #cell="{ record }">{{ fmtTime(record.mtime) }}</template>
                    </a-table-column>
                    <a-table-column title="状态" :width="140">
                      <template #cell="{ record }">
                        <a-tag size="small" :color="KIND_COLOR[record.kind] || 'gray'">
                          {{ KIND_LABEL[record.kind] || record.kind }}
                        </a-tag>
                        <a-tag v-if="record.encrypted" size="small" color="orangered">加密</a-tag>
                      </template>
                    </a-table-column>
                    <a-table-column title="操作" :width="128">
                      <template #cell="{ record }">
                        <a-space size="mini">
                          <a-button size="mini" type="outline" @click="restoreSnapshot(record)">恢复</a-button>
                          <a-button size="mini" status="danger" @click="deleteSnapshot(record)">删除</a-button>
                        </a-space>
                      </template>
                    </a-table-column>
                  </template>
                  <template #empty>
                    <a-empty description="暂无备份文件" />
                  </template>
                </a-table>
                <p class="sys-hint muted">目录：<code>{{ backupStatus.dir || backupDirDisplay }}</code></p>
              </section>
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
      <span v-if="mainKey !== 'history'" class="hint save-hint">带「即时」标记的项改动立即生效，其余随「保存设置」写入</span>
      <a-button @click="cancelHost">取消</a-button>
      <a-button v-if="mainKey !== 'history'" type="primary" :loading="saving" @click="onSave">💾 保存设置</a-button>
    </div>

    <!-- 插件使用说明抽屉 -->
    <PluginDocDrawer v-model:visible="opsDocVisible" :plugin="opsDocPlugin" />
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  authorizePlugin,
  cancelHost,
  closeHost,
  deleteBackup,
  deletePlugin,
  exportBackup,
  feishuSyncResync,
  feishuSyncTest,
  getSettings,
  getSystemStatus,
  importBackup,
  importPreview,
  installPluginPath,
  installPluginZip,
  exportTasksCalendar,
  getMeta,
  listBackups,
  listPlugins,
  openAttachment,
  packArchive,
  pickPath,
  previewPluginZip,
  saveSettings,
  setAutostart,
  updatePlugin,
  updatesCheck,
  updatesDownload,
  updatesInstall,
  updatesStatus,
  validatePluginPath,
} from '@/api/client'
import { applyAppearance, applyTheme } from '@/theme'
import JobEditor from '@/components/JobEditor.vue'
import HistoryPanel from '@/components/HistoryPanel.vue'
import NumberSpinner from '@/components/NumberSpinner.vue'
import PluginDocDrawer from '@/components/PluginDocDrawer.vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const setThemeMode = inject('setThemeMode', null)
const loading = ref(false)
const saving = ref(false)
const mainKey = ref('ai')
const apiExpandKeys = ref([])
const notifyExpandKeys = ref([])

function goNewTask() {
  router.push('/tasks/new?from=list')
}

// —— 飞书同步（任务页卡片）——
const feishuTesting = ref(false)
const feishuResyncing = ref(false)
const FEISHU_DOC_URL = 'https://github.com/iyouex/zentray/blob/staging/docs/FEISHU_SYNC.md'

function openFeishuDoc() {
  openAttachment(FEISHU_DOC_URL).catch(() => {})
}

/** 测试/重同步读的是已保存配置：先局部保存本卡片再执行（同 saveOpsPatch 惯例，只动本节避免覆盖后台写入的状态） */
async function saveFeishuSection() {
  await saveSettings({ feishu_sync: { ...form.feishu_sync } })
}

async function onFeishuTest() {
  feishuTesting.value = true
  try {
    await saveFeishuSection()
    const r = await feishuSyncTest()
    form.feishu_sync.last_error = r.ok ? '' : (r.message || '连接失败')
    if (r.ok) Message.success(r.message || '连接成功')
    else Message.error(r.message || '连接失败')
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '保存或测试失败')
  } finally {
    feishuTesting.value = false
  }
}

async function onFeishuResync() {
  feishuResyncing.value = true
  try {
    await saveFeishuSection()
    const r = await feishuSyncResync()
    Message.success(`已入队 ${r.queued ?? 0} 条任务重推，稍后在飞书查看`)
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '重同步失败')
  } finally {
    feishuResyncing.value = false
  }
}

const feishuStatusText = computed(() => {
  const f = form.feishu_sync
  if (f.last_error) return `最近错误：${f.last_error}`
  if (f.last_sync_at) return `上次同步：${f.last_sync_at}`
  return ''
})

// —— 系统日历订阅源（任务页卡片）——
const sysDataDir = ref('')
const calendarFeedPath = computed(() =>
  sysDataDir.value ? `${sysDataDir.value}/calendar/zentray.ics` : ''
)

async function onCalendarOpenFolder() {
  const dir = calendarFeedPath.value.replace(/\/[^/]*$/, '')
  if (!dir) return
  try {
    await openAttachment(dir)
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '打开失败（先保存设置生成源文件）')
  }
}

async function onCalendarCopyLink() {
  const url = `file://${calendarFeedPath.value}`
  try {
    await navigator.clipboard.writeText(url)
    Message.success('已复制订阅链接')
  } catch {
    // WebEngine 剪贴板权限缺失时退回 execCommand
    const ta = document.createElement('textarea')
    ta.value = url
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    if (ok) Message.success('已复制订阅链接')
    else Message.warning(`复制失败，请手动复制：${url}`)
  }
}

// —— 系统页 ——
const autostartEnabled = ref(false)
const autostartLoading = ref(false)
const autostartHint = ref('')
// Windows 任务栏标签可见性（§3.0）：true/false；null=非 Windows/未知 → 隐藏整卡
const statusbarSupported = ref(false)
const includeOptions = ref([])
const exportInclude = ref([])
const exportLoading = ref(false)
const archivePackLoading = ref(false)
const calendarExporting = ref(false)
const lastExportPath = ref('')
const importPath = ref('')
const importLoading = ref(false)
const lastImportMsg = ref('')

// —— 备份页 ——
const backupStatus = ref({}) // /api/system/status 的 backup 节（dir/default_dir/custom/last_backup_at）
const snapshots = ref([])
const snapshotsLoading = ref(false)
const encryptEnabled = ref(false)
const backupPassword = ref('')
const importNeedsPassword = ref(false)
const importPassword = ref('')
// 选择性恢复：预览数据 + 勾选树选中项（key 或 key:sub）
const importPreviewData = ref(null)
const importChecked = ref([])
const previewLoading = ref(false)
const saveAsLoading = ref(false)
const savedBackupDir = ref('')

// —— 插件（设置页只做管理：列表 / 导入；运行与历史在托盘运行台） ——
const opsLoaded = ref(false)
const opsListLoading = ref(false)
const opsListEnabled = ref(false)
const opsItems = ref([])
const opsFailures = ref([])
const opsAuthBusy = ref('')
const opsPresetSaving = ref('')
// 每插件展开面板（编辑 / 参数预设 / 自动运行授权），受控：保存刷新列表不丢
const opsEditOpen = reactive({})
// 使用说明抽屉
const opsDocVisible = ref(false)
const opsDocPlugin = ref(null)
watch(opsDocPlugin, (v) => { if (v) opsDocVisible.value = true })
// 名称/简介编辑（就地改写 plugin.yaml）
const opsMetaSaving = ref('')
const metaDrafts = reactive({})

// 导入块：zip/目录切换 + 预览校验门 + 高级（用户目录）
const plugImportMode = ref('dir')
const plugImportPath = ref('')
const plugImportPreviewing = ref(false)
const plugImportInstalling = ref(false)
const plugImportPreview = ref(null)
const opsUserDir = ref('')
const opsUserDirHint = ref('')
const opsDirSaving = ref(false)

// 参数预设草稿
const presetDrafts = reactive({})

const TRIGGER_LABEL = {
  manual: '手动',
  daily: '每日',
  interval: '间隔',
  cron: 'cron',
  task_done: '任务完成',
  pomodoro_end: '番茄结束',
  break_end: '休息结束',
  startup: '启动时',
}

/** manifest 触发器的一行式提示（如「每日 08:30」） */
function trigLabel(t) {
  if (!t) return ''
  if (t.type === 'daily') return `每日 ${t.time}`
  if (t.type === 'interval') return `每 ${t.minutes} 分钟`
  if (t.type === 'cron') return `cron ${t.expr}`
  return `事件: ${TRIGGER_LABEL[t.event] || t.event}`
}

// 个位数插件规模，固定名称排序即可
const opsSortedByName = computed(() =>
  [...opsItems.value].sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'zh')),
)

function applyOpsList(data) {
  opsListEnabled.value = !!data.enabled
  opsItems.value = data.items || []
  opsFailures.value = data.failures || []
  if (data.user_dir) opsUserDirHint.value = data.user_dir
  for (const p of opsItems.value) syncPresetDraft(p)
}

function syncPresetDraft(p) {
  const saved = form.ops.param_presets?.[p.id] || {}
  presetDrafts[p.id] = {}
  for (const prm of p.params || []) {
    if (prm.variadic) {
      // 可变长度：预设/缺省归一为行数组，至少一行
      const v = saved[prm.name]
      const rows = Array.isArray(v)
        ? v.filter((s) => s !== '')
        : v != null && v !== '' ? [v] : prm.default ? [prm.default] : []
      presetDrafts[p.id][prm.name] = rows.length ? rows : ['']
    } else {
      presetDrafts[p.id][prm.name] = saved[prm.name] ?? prm.default ?? ''
    }
  }
}

async function refreshOpsPlugins() {
  opsListLoading.value = true
  try {
    applyOpsList(await listPlugins())
  } catch (e) {
    Message.warning(e?.response?.data?.error || e?.message || '加载插件列表失败')
  } finally {
    opsListLoading.value = false
  }
}

async function loadOpsPage() {
  if (!opsLoaded.value) {
    opsLoaded.value = true
    await refreshOpsPlugins()
    // 导入路径默认 = 内置插件目录
    if (!plugImportPath.value) {
      try {
        const data = await listPlugins()
        if (data.bundled_dir) plugImportPath.value = data.bundled_dir
      } catch { /* 忽略：仅默认值 */ }
    }
  }
}

/** ops 局部保存惯例：getSettings → 合并 → saveSettings（后端 ops 分支整体替换） */
async function saveOpsPatch(patch) {
  const s = await getSettings()
  const ops = { ...(s?.ops || {}), ...patch }
  await saveSettings({ ops })
  Object.assign(form.ops, patch)
}

async function onOpsAuthorize(p, allow) {
  opsAuthBusy.value = p.id
  try {
    await authorizePlugin(p.id, !!allow)
    p.authorized = !!allow
    Message.success(allow ? '已授权自动运行' : '已拒绝自动运行（不再询问）')
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '设置授权失败')
  } finally {
    opsAuthBusy.value = ''
  }
}

/** 行展开开关：「编辑」「参数预设」共用同一面板（编辑/预设/授权三节） */
function toggleOpsEdit(p) {
  if (opsEditOpen[p.id]) {
    delete opsEditOpen[p.id]
    return
  }
  opsEditOpen[p.id] = true
  metaDrafts[p.id] = { name: p.name, description: p.description || '' }
}

async function savePluginMeta(p) {
  const d = metaDrafts[p.id] || {}
  if (!(d.name || '').trim()) {
    Message.warning('名称不能为空')
    return
  }
  opsMetaSaving.value = p.id
  try {
    const data = await updatePlugin(p.id, { name: d.name.trim(), description: (d.description || '').trim() })
    applyOpsList(data.plugins)
    Message.success('已保存')
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '保存失败')
  } finally {
    opsMetaSaving.value = ''
  }
}

/** Popconfirm 确认后执行（bundled=隐藏可恢复；user=移除目录不可恢复） */
async function onOpsDelete(p) {
  try {
    const data = await deletePlugin(p.id)
    applyOpsList(data.plugins)
    // 本地 ops 覆盖同步清理，避免下次整体保存时复活
    for (const k of ['trigger_overrides', 'param_presets', 'installed_at']) {
      if (form.ops[k]) delete form.ops[k][p.id]
    }
    delete presetDrafts[p.id]
    delete opsEditOpen[p.id]
    Message.success('已删除')
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '删除失败')
  }
}

async function plugOnImportPick() {
  const kind = plugImportMode.value === 'zip' ? 'file' : 'dir'
  const r = await pickPath(kind, {
    title: plugImportMode.value === 'zip' ? '选择插件 zip 包' : '选择插件目录',
  })
  if (r.cancelled || !r.path) {
    if (!r.id) Message.info('仅桌面端支持路径选择')
    return
  }
  plugImportPath.value = r.path
  plugImportPreview.value = null
}

async function plugOnImportPreview() {
  const path = plugImportPath.value.trim()
  if (!path) {
    Message.warning(plugImportMode.value === 'zip' ? '请填写 zip 包路径' : '请填写插件目录路径')
    return
  }
  plugImportPreviewing.value = true
  plugImportPreview.value = null
  try {
    const data = plugImportMode.value === 'zip'
      ? await previewPluginZip(path)
      : await validatePluginPath(path)
    plugImportPreview.value = data
    if (data.ok) Message.success('校验通过，可以安装')
    else Message.error('校验未通过，见下方错误')
  } catch (e) {
    const err = e?.response?.data
    plugImportPreview.value = {
      ok: false,
      errors: err?.errors || [err?.error || e?.message || '校验请求失败'],
      preview: null,
      path,
    }
  } finally {
    plugImportPreviewing.value = false
  }
}

async function plugOnImportInstall() {
  const path = plugImportPath.value.trim()
  if (!path || !plugImportPreview.value?.ok) {
    Message.warning('请先预览校验并通过')
    return
  }
  const doInstall = async (overwrite = false) => {
    plugImportInstalling.value = true
    try {
      const data = plugImportMode.value === 'zip'
        ? await installPluginZip(path, { overwrite })
        : await installPluginPath(path, { overwrite })
      Message.success(data.message || '安装成功')
      if (data.plugins) applyOpsList(data.plugins)
      else await refreshOpsPlugins()
      plugImportPath.value = ''
      plugImportPreview.value = null
    } catch (e) {
      onOpsInstallConflict(e, () => doInstall(true), '安装失败')
    } finally {
      plugImportInstalling.value = false
    }
  }
  await doInstall(false)
}

/** 409 目标已存在 → 询问覆盖重装 */
function onOpsInstallConflict(e, onOverwrite, fallback) {
  const status = e?.response?.status
  const err = e?.response?.data
  if (status === 409) {
    Modal.confirm({
      draggable: true,
      title: '目标已存在',
      content: err?.error || '是否覆盖安装？',
      okText: '覆盖',
      onOk,
    })
  } else {
    Message.error(err?.error || e?.message || fallback)
  }
}

async function onSaveOpsUserDir() {
  opsDirSaving.value = true
  try {
    await saveOpsPatch({ user_plugins_dir: opsUserDir.value.trim() })
    Message.success('用户插件目录已保存')
    await refreshOpsPlugins()
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '保存失败')
  } finally {
    opsDirSaving.value = false
  }
}

async function saveParamPreset(p) {
  opsPresetSaving.value = p.id
  try {
    await saveOpsPatch({
      param_presets: { ...(form.ops.param_presets || {}), [p.id]: { ...(presetDrafts[p.id] || {}) } },
    })
    Message.success('参数预设已保存')
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '保存失败')
  } finally {
    opsPresetSaving.value = ''
  }
}


const HOUR_OPTS = Array.from({ length: 24 }, (_, h) => ({
  label: `${String(h).padStart(2, '0')}:00`,
  value: h,
}))
const KIND_LABEL = { auto: '自动', manual: '手动', pre_import: '导入前', archive: '归档', unknown: '其他' }
const KIND_COLOR = { auto: 'green', manual: 'arcoblue', pre_import: 'orange', archive: 'purple', unknown: 'gray' }

const backupDirDisplay = computed(
  () => (form.backup.dir || '').trim() || backupStatus.value.default_dir || backupStatus.value.dir || ''
)
const backupDirDirty = computed(() => (form.backup.dir || '').trim() !== savedBackupDir.value)

const form = reactive(emptyForm())

/** AI 场景能力卡片（docs/AI-FEATURES.md）：键名对应 ai.features.* */
const AI_FEATURES = [
  { key: 'smart_parse', icon: '✨', name: '智能解析', desc: '快速添加与任务表单中，一句话自动补全分类/优先级/截止与子任务' },
  { key: 'image_ocr', icon: '📷', name: '图片识别', desc: '上传或粘贴截图，AI 识别其中的待办并生成任务草稿' },
  { key: 'task_suggest', icon: '💡', name: '任务建议', desc: '基于任务列表给出优先级/截止/拆分建议，可一键应用' },
]

/** 固定两条渠道，不允许增删 */
const fixedChannels = computed(() => ensureFixedChannels(form.notification))

/** 插件级报告通知渠道下拉选项：仅 设置-通知 中已开启的渠道 */
const enabledChannelOptions = computed(() =>
  fixedChannels.value.filter((c) => c.enabled).map((c) => ({ label: c.name, value: c.type })),
)

function setPluginChannels(pid, v) {
  if (!form.ops.plugin_notify_channels) form.ops.plugin_notify_channels = {}
  form.ops.plugin_notify_channels[pid] = Array.isArray(v) ? v : []
}

/** 通知模板渲染（与后端 render_template 同语义：未知占位符原样保留） */
function renderTpl(tpl, ctx) {
  return String(tpl || '').replace(/\{(\w+)\}/g, (m, k) => (k in ctx ? String(ctx[k]) : m))
}

const NOTIFY_PREVIEW_CTX = {
  name: 'ai-news-digest',
  status: '执行成功',
  summary: '共 12 条要闻',
  result: 'AI 日报已生成：共 12 条要闻，其中高优 3 条……',
}
const notifyPreviewTitle = computed(() => renderTpl(form.notification.plugin_title_template, NOTIFY_PREVIEW_CTX))
const notifyPreviewBody = computed(() => renderTpl(form.notification.plugin_body_template, NOTIFY_PREVIEW_CTX))

/** 番茄钟节奏预设：回填时长数字框（非独立模式） */
const POMO_PRESETS = [
  { key: 'classic', label: '经典 25/5', focus: 25, short: 5, long: 15 },
  { key: 'deep', label: '深度 50/10', focus: 50, short: 10, long: 30 },
  { key: 'long', label: '超长 90/20', focus: 90, short: 20, long: 30 },
]

/** 当前三值恰好等于某预设时返回其 key（选中态反馈） */
const activePreset = computed(() => {
  const p = form.pomodoro
  const hit = POMO_PRESETS.find(
    (x) =>
      p.duration_minutes === x.focus &&
      p.short_break_minutes === x.short &&
      p.long_break_minutes === x.long,
  )
  return hit?.key || ''
})

function applyPomodoroPreset(focus, shortBreak, longBreak) {
  form.pomodoro.duration_minutes = focus
  form.pomodoro.short_break_minutes = shortBreak
  form.pomodoro.long_break_minutes = longBreak
}

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
      tray_icon_countdown: false,
      short_break_minutes: 5,
      long_break_minutes: 15,
      long_break_every: 4,
      auto_start_breaks: true,
      auto_start_focus: false,
      daily_goal_pomodoros: 0,
      menu_label_format: '🍅 专注{focus}mins -- 今日{today}mins',
    },
    nightly: {},
    notification: {
      channels: defaultChannels(),
      enabled: true,
      wxpusher_app_token: '',
      wxpusher_uid: '',
      plugin_title_template: '脚本: {name}',
      plugin_body_template: '{result}',
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
      features: { smart_parse: false, image_ocr: false, task_suggest: false },
    },
    categories: {
      enabled_secondary: true,
      wrap_left: '[',
      wrap_right: ']',
      level_separator: '-',
      primary_list: [],
    },
    quick_add: { enabled: true, hotkey: '', default_category: '工作', default_priority: 'medium' },
    feishu_sync: {
      enabled: false,
      app_id: '',
      app_secret: '',
      sync_calendar: true,
      sync_tasks: true,
      feishu_user_id: '',
      calendar_id: '',
      task_list_guid: '',
      last_error: '',
      last_sync_at: '',
    },
    appearance: {
      theme: 'system',
      autostart: false,
      motion: 'full',
      shape: 'round',
      skin: 'neo',
      statusbar_enabled: true,
      statusbar_marquee: false,
    },
    backup: { dir: '', auto_enabled: false, interval_days: 1, keep: 7, trigger_hour: 9 },
    ops: {
      enabled: false,
      user_plugins_dir: '',
      trigger_overrides: {},
      param_presets: {},
      report_tray_enabled: true,
      report_tray_minutes: 60,
      plugin_notify_channels: {},
    },
    update: { proxy: '' },
    calendar: { enabled: false },
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
    {
      id: 'ch_feishu_bot',
      type: 'feishu_bot',
      name: '飞书机器人',
      enabled: false,
      feishu_webhook: '',
      feishu_secret: '',
    },
  ]
}

/**
 * 始终只保留 app_popup + wxpusher + feishu_bot 各一条（合并旧数据）
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
  let fs = list.find((c) => c.type === 'feishu_bot')
  if (!fs) fs = defaultChannels().find((c) => c.type === 'feishu_bot')
  app.id = app.id || 'ch_app_popup'
  app.name = '应用弹窗'
  app.type = 'app_popup'
  wx.id = wx.id || 'ch_wxpusher'
  wx.name = 'WxPusher'
  wx.type = 'wxpusher'
  fs.id = fs.id || 'ch_feishu_bot'
  fs.name = '飞书机器人'
  fs.type = 'feishu_bot'
  // 写回 form，保证引用一致
  notification.channels = [app, wx, fs]
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
    report_tray_enabled: true,
    report_tray_minutes: 60,
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
  if (key === 'backup') loadBackupPage()
  if (key === 'ops') loadOpsPage()
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
    sysDataDir.value = data?.data_dir || ''
    autostartEnabled.value = !!data?.autostart?.enabled
    form.appearance.autostart = !!data?.autostart?.preference
    const target = data?.autostart?.launch_target
    autostartHint.value = target ? `启动目标：${target}` : ''
    statusbarSupported.value = !!data?.windows?.statusbar_supported
    const opts = data?.include_options || []
    includeOptions.value = opts
    if (!exportInclude.value.length) {
      exportInclude.value = opts.filter((o) => o.default).map((o) => o.key)
    }
    backupStatus.value = data?.backup || {}
  } catch (e) {
    // 系统 API 不可用时不影响其它设置
    autostartHint.value = e?.message || '无法读取系统状态'
  }
}

/** 导出活跃任务为 .ics 并唤起系统日历应用（用户确认后写入系统日历） */
async function onCalendarExport() {
  calendarExporting.value = true
  try {
    const data = await exportTasksCalendar()
    Message.success(`已生成 ${data.count} 条日历事件，请在系统日历应用中确认导入`)
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '导出失败')
  } finally {
    calendarExporting.value = false
  }
}

/** —— 软件更新：检查 → 下载（轮询进度）→ 安装并重启 —— */
const appVersion = ref('')
const upd = reactive({ checking: false, state: 'idle', progress: 0, error: '', result: null })
let updTimer = null

onBeforeUnmount(() => clearInterval(updTimer))

async function onUpdatesCheck() {
  upd.checking = true
  upd.error = ''
  try {
    upd.result = await updatesCheck()
  } catch (e) {
    upd.error = e?.response?.data?.error || e?.message || '检查失败'
  } finally {
    upd.checking = false
  }
}

async function onUpdatesDownload() {
  if (!upd.result || !upd.result.asset_url) return
  upd.error = ''
  upd.state = 'downloading'
  try {
    await updatesDownload({ url: upd.result.asset_url, version: upd.result.version })
    clearInterval(updTimer)
    updTimer = setInterval(async () => {
      try {
        const s = await updatesStatus()
        upd.state = s.state
        upd.progress = s.progress
        if (s.error) upd.error = s.error
        if (s.state === 'ready' || s.state === 'error') clearInterval(updTimer)
      } catch {
        clearInterval(updTimer)
      }
    }, 500)
  } catch (e) {
    upd.state = 'idle'
    upd.error = e?.response?.data?.error || e?.message || '下载启动失败'
  }
}

function onUpdatesInstall() {
  Modal.confirm({
    title: '安装并重启 ZenTray？',
    content: '安装完成后应用将自动重启（Linux 会先弹出系统认证窗口）。',
    okText: '安装并重启',
    onOk: async () => {
      try {
        await updatesInstall()
        Message.info('正在安装，应用即将重启…')
      } catch (e) {
        upd.error = e?.response?.data?.error || e?.message || '安装失败'
      }
    },
  })
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

/** env 含密钥时先确认；返回 false 表示用户取消 */
async function confirmEnvIfAny() {
  if (!exportInclude.value.includes('env')) return true
  return new Promise((resolve) => {
    Modal.confirm({
      draggable: true,
      title: '包含密钥',
      content: '导出内容包含 .env（API Key 等）。请妥善保管备份文件，确认继续？',
      okText: '继续导出',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}

function backupPasswordPayload() {
  if (!encryptEnabled.value) return ''
  if (!backupPassword.value) {
    Message.warning('已开启加密，请填写备份密码')
    return null
  }
  return backupPassword.value
}

async function onExportBackup() {
  if (!exportInclude.value.length) {
    Message.warning('请至少选择一项导出内容')
    return
  }
  const password = backupPasswordPayload()
  if (password === null) return
  if (!(await confirmEnvIfAny())) return
  exportLoading.value = true
  try {
    const data = await exportBackup(exportInclude.value, { password })
    if (!data?.ok) {
      Message.error(data?.message || '导出失败')
      return
    }
    lastExportPath.value = data.path || ''
    Message.success(`导出成功${data.path ? `：${data.path}` : ''}`)
    await loadBackups()
  } catch (e) {
    Message.error(e?.response?.data?.message || e?.message || '导出失败')
  } finally {
    exportLoading.value = false
  }
}

/** 另存为：原生保存对话框选路径后导出到该位置 */
async function onExportSaveAs() {
  if (!exportInclude.value.length) {
    Message.warning('请至少选择一项导出内容')
    return
  }
  const password = backupPasswordPayload()
  if (password === null) return
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const r = await pickPath('save', {
    title: '备份另存为',
    startDir: backupDirDisplay.value,
    defaultName: `zentray-backup-${stamp}.zip`,
  })
  if (r.cancelled || !r.path) {
    if (!r.id) Message.info('仅桌面端支持路径选择')
    return
  }
  const destPath = r.path.toLowerCase().endsWith('.zip') ? r.path : `${r.path}.zip`
  if (!(await confirmEnvIfAny())) return
  saveAsLoading.value = true
  try {
    const data = await exportBackup(exportInclude.value, { destPath, password })
    if (!data?.ok) {
      Message.error(data?.message || '导出失败')
      return
    }
    lastExportPath.value = data.path || ''
    Message.success(`已另存${data.path ? `：${data.path}` : ''}`)
    await loadBackups()
  } catch (e) {
    Message.error(e?.response?.data?.message || e?.message || '导出失败')
  } finally {
    saveAsLoading.value = false
  }
}

async function onChangeBackupDir() {
  const r = await pickPath('dir', { title: '选择备份存储目录', startDir: backupDirDisplay.value })
  if (r.cancelled || !r.path) {
    if (!r.id) Message.info('仅桌面端支持目录选择')
    return
  }
  form.backup.dir = r.path
}

/** 选择性恢复勾选树：父=整类替换，子=分区替换 */
const importTree = computed(() => {
  const data = importPreviewData.value
  if (!data) return []
  const labels = Object.fromEntries(includeOptions.value.map((o) => [o.key, o.label]))
  const secLabels = {
    polling: '轮询',
    pomodoro: '番茄钟',
    nightly: '夜间复盘',
    notification: '通知',
    ai: 'AI',
    categories: '分类',
    quick_add: '快捷添加',
    appearance: '外观',
    backup: '备份',
    ops: '插件运行时',
    update: '软件更新',
    feishu_sync: '飞书同步',
    calendar: '系统日历',
  }
  const nodes = []
  for (const c of data.categories || []) {
    if (!c.present) continue
    const label = labels[c.key] || c.key
    let children
    if (c.key === 'tasks') {
      children = [
        { key: 'tasks:one-time', title: `一次性任务（${c.counts?.['one-time'] || 0}）` },
        { key: 'tasks:periodic_instance', title: `周期任务实例（${c.counts?.periodic_instance || 0}）` },
      ]
    } else if (c.key === 'settings') {
      children = (c.sections || []).map((s) => ({ key: `settings:${s}`, title: secLabels[s] || s }))
    } else if (c.key === 'reviews') {
      children = [
        { key: 'reviews:plan', title: `AI 计划（${c.counts?.plan || 0}）` },
        { key: 'reviews:review', title: `AI 复盘（${c.counts?.review || 0}）` },
      ]
    } else if (c.key === 'archive') {
      children = (c.months || []).map((m) => ({ key: `archive:${m.month}`, title: `${m.month}（${m.files} 个文件）` }))
    } else if (c.key === 'plugins') {
      children = (c.plugins || []).map((p) => ({ key: `plugins:${p}`, title: p }))
    }
    const title = c.key === 'templates' && c.count != null ? `${label}（${c.count}）` : label
    nodes.push({ key: c.key, title, children })
  }
  return nodes
})

const importTreeExpanded = computed(() =>
  importTree.value.filter((n) => n.children?.length).map((n) => n.key)
)

/** 周期任务按模板分布（仅展示，不提供勾选） */
const importTplHint = computed(() => {
  const t = (importPreviewData.value?.categories || []).find((c) => c.key === 'tasks')
  const parts = (t?.templates || []).map((x) => `${x.title || x.template_id}×${x.count}`)
  return parts.length ? `周期任务按模板：${parts.join('、')}` : ''
})

/** 树选中项 → include 列表：父选中=整类，否则取勾中的子项 */
function selectionFromChecked(checked) {
  const set = new Set(checked)
  const out = []
  for (const node of importTree.value) {
    if (set.has(node.key)) {
      out.push(node.key)
      continue
    }
    for (const k of node.children || []) if (set.has(k.key)) out.push(k.key)
  }
  return out
}

async function loadImportPreview() {
  const path = (importPath.value || '').trim()
  if (!path) {
    Message.warning('请先选择或填写备份 zip 路径')
    return false
  }
  previewLoading.value = true
  try {
    const data = await importPreview(path, {
      password: importNeedsPassword.value ? importPassword.value || undefined : undefined,
    })
    if (!data?.ok) {
      const msg = data?.message || data?.error || '预览失败'
      Message.error(msg)
      // 服务端判定缺密码/密码错误：展开密码框让用户补
      if (msg.includes('密码')) importNeedsPassword.value = true
      importPreviewData.value = null
      return false
    }
    importPreviewData.value = data
    // 默认全选（与原整包恢复心智一致），用户再按需收窄
    importChecked.value = (data.categories || []).filter((c) => c.present).map((c) => c.key)
    return true
  } catch (e) {
    Message.error(e?.response?.data?.message || e?.response?.data?.error || e?.message || '预览失败')
    return false
  } finally {
    previewLoading.value = false
  }
}

// 路径变化后旧预览作废（手输/清空/重选）
watch(importPath, (v) => {
  if (importPreviewData.value && (v || '').trim() !== importPreviewData.value.path) {
    importPreviewData.value = null
  }
})

/** 原生文件选择器挑备份 zip；若快照表里是加密包，预置密码框 */
async function onPickBackupFile() {
  const r = await pickPath('file', { title: '选择备份文件', startDir: backupDirDisplay.value })
  if (r.cancelled || !r.path) {
    if (!r.id) Message.info('仅桌面端支持文件选择')
    return
  }
  importPath.value = r.path
  importNeedsPassword.value = snapshots.value.some((s) => s.path === r.path && s.encrypted)
  loadImportPreview()
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
  // 未预览（如手输路径直接点恢复）先出勾选树
  if (!importPreviewData.value) {
    if (!(await loadImportPreview())) return
  }
  const sel = selectionFromChecked(importChecked.value)
  if (!sel.length) {
    Message.warning('请勾选要恢复的内容')
    return
  }
  const ok = await new Promise((resolve) => {
    Modal.confirm({
      draggable: true,
      title: '确认导入（替换）',
      content:
        `将用备份替换所选 ${sel.length} 项内容（勾选子项时仅替换对应分区，其余保持现状），并先自动生成安全备份。是否继续？`,
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
      include: sel,
      safety_backup: true,
      password: importNeedsPassword.value ? importPassword.value || undefined : undefined,
    })
    if (!data?.ok) {
      Message.error(data?.message || data?.error || '导入失败')
      lastImportMsg.value = data?.message || data?.error || ''
      // 服务端判定缺密码/密码错误：展开密码框让用户补
      if ((lastImportMsg.value || '').includes('密码')) importNeedsPassword.value = true
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
    await loadBackups()
  } catch (e) {
    Message.error(e?.response?.data?.message || e?.response?.data?.error || e?.message || '导入失败')
  } finally {
    importLoading.value = false
  }
}

// —— 备份页：快照列表 / 恢复 / 删除 ——
async function loadBackups() {
  snapshotsLoading.value = true
  try {
    const data = await listBackups()
    snapshots.value = data?.items || []
  } catch (e) {
    // 快照拉取失败不阻塞页面，保留旧列表
    snapshots.value = []
  } finally {
    snapshotsLoading.value = false
  }
}

function loadBackupPage() {
  loadSystemStatus()
  loadBackups()
}

/** 快照行「恢复」：回填路径 + 密码态，出预览勾选树 */
function restoreSnapshot(record) {
  importPath.value = record.path
  importNeedsPassword.value = !!record.encrypted
  importPassword.value = ''
  importPreviewData.value = null
  loadImportPreview()
}

function deleteSnapshot(record) {
  Modal.confirm({
    draggable: true,
    title: '删除备份',
    content: `确定删除 ${record.name}？此操作不可恢复。`,
    okText: '删除',
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      try {
        const data = await deleteBackup(record.path)
        if (!data?.ok) {
          Message.error(data?.message || '删除失败')
          return
        }
        Message.success('已删除')
        await loadBackups()
      } catch (e) {
        Message.error(e?.response?.data?.message || e?.message || '删除失败')
      }
    },
  })
}

function fmtSize(n) {
  if (!Number.isFinite(n)) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function fmtTime(iso) {
  return (iso || '').replace('T', ' ').slice(0, 16)
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
  if (!form.ai.features) form.ai.features = { smart_parse: false, image_ocr: false, task_suggest: false }
  // 公休日：若仅一侧开启，展开为两边一致（以「都开」为准显示）
  for (const job of [form.ai.plan, form.ai.review]) {
    if (job.skip_weekends || job.skip_holidays) {
      // 保持各自值；UI 用 AND 显示，用户开公休日会两边都开
    }
  }
  if (!form.notification) form.notification = emptyForm().notification
  ensureFixedChannels(form.notification)
  // 通知格式模板（旧数据无键补默认）
  if (!form.notification.plugin_title_template) form.notification.plugin_title_template = '脚本: {name}'
  if (!form.notification.plugin_body_template) form.notification.plugin_body_template = '{result}'
  if (!form.appearance) form.appearance = { theme: 'system', autostart: false }
  if (form.appearance.autostart == null) form.appearance.autostart = false
  if (form.appearance.motion == null) form.appearance.motion = 'full'
  if (form.appearance.shape == null) form.appearance.shape = 'round'
  if (!['neo', 'aurora', 'synth', 'clay'].includes(form.appearance.skin)) form.appearance.skin = 'neo'
  if (form.appearance.statusbar_enabled == null) form.appearance.statusbar_enabled = true
  if (form.appearance.statusbar_marquee == null) form.appearance.statusbar_marquee = false
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
  if (!form.feishu_sync) form.feishu_sync = emptyForm().feishu_sync
  if (!form.calendar) form.calendar = emptyForm().calendar
  // 备份：normalize 时补默认 + 钳制（trigger_hour 0 点合法，不能用 || 兜底）
  const bk = { ...emptyForm().backup, ...(s.backup || {}) }
  if (![1, 3, 7].includes(bk.interval_days)) bk.interval_days = 1
  if (!Number.isFinite(bk.keep)) bk.keep = 7
  bk.keep = Math.max(1, Math.min(50, bk.keep))
  if (!Number.isFinite(bk.trigger_hour)) bk.trigger_hour = 9
  bk.trigger_hour = Math.max(0, Math.min(23, bk.trigger_hour))
  bk.auto_enabled = !!bk.auto_enabled
  bk.dir = (bk.dir || '').trim()
  form.backup = bk
  savedBackupDir.value = bk.dir
  // 插件：兜底合并
  form.ops = { ...emptyForm().ops, ...(s.ops || {}) }
  if (!form.ops.trigger_overrides) form.ops.trigger_overrides = {}
  if (!form.ops.param_presets) form.ops.param_presets = {}
  if (!form.ops.plugin_notify_channels) form.ops.plugin_notify_channels = {}
  opsUserDir.value = form.ops.user_plugins_dir || ''
  if (!form.polling) form.polling = emptyForm().polling
  // 番茄钟：旧配置缺新键时补默认
  form.pomodoro = { ...emptyForm().pomodoro, ...(form.pomodoro || s.pomodoro || {}) }
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
    getMeta().then(m => { appVersion.value = m.version }).catch(() => {})
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
.nav-main :deep(.arco-menu-group-title) {
  font-size: var(--zt-note);
  font-weight: 600;
  line-height: 1.2;
  color: var(--color-text-3);
  letter-spacing: 0.05em;
  padding: 10px 12px 4px;
  cursor: default;
}

/* 选中态统一结构（UI 重构 P1）：左 3px 主色竖条 + 主色文字 + 600 + 8% 主色底；
   四皮肤只在下方改竖条配色，不改结构 */
.nav-main :deep(.arco-menu-item.arco-menu-selected) {
  position: relative;
  font-weight: 600;
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 8%, transparent);
}
.nav-main :deep(.arco-menu-item.arco-menu-selected)::before {
  content: "";
  position: absolute;
  left: 6px;
  top: 22%;
  bottom: 22%;
  width: 3px;
  border-radius: 999px;
  background: var(--color-primary);
}
/* ---- 皮肤变体（body.zt-skin-* 门控，仅改色） ---- */
/* Aurora：导航玻璃 + 选中竖条极光渐变 */
body.zt-skin-aurora .nav-main {
  border: 1px solid color-mix(in srgb, var(--color-text-primary) 9%, transparent);
  background: color-mix(in srgb, var(--color-surface) 55%, transparent);
  backdrop-filter: blur(18px) saturate(1.5);
  -webkit-backdrop-filter: blur(18px) saturate(1.5);
  box-shadow: 0 8px 32px rgba(2, 6, 23, 0.35),
    inset 0 1px 0 color-mix(in srgb, #ffffff 6%, transparent);
}
body.zt-skin-aurora .nav-main :deep(.arco-menu-item.arco-menu-selected)::before {
  background: linear-gradient(180deg, var(--color-primary), #818cf8);
}
/* Neo：设置页容器去描边纯阴影 */
body.zt-skin-neo .settings-page-body .zt-block {
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
/* Synth：选中竖条霓虹渐变 + 辉光 */
body.zt-skin-synth .nav-main :deep(.arco-menu-item.arco-menu-selected)::before {
  background: linear-gradient(180deg, var(--color-primary), var(--zt-neon-pink));
  box-shadow: 0 0 8px var(--color-primary-glow);
}
/* Clay：导航容器描边投影（选中态走统一结构） */
body.zt-skin-clay .nav-main {
  border: 1px solid var(--color-border);
  box-shadow: var(--zt-shadow-card);
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
/* AI 场景能力开关卡片网格 */
.feat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  margin-bottom: 8px;
}
.feat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-border-2);
  border-radius: var(--zt-radius-card, 12px);
  background: var(--color-fill-1, rgba(148, 163, 184, 0.06));
  transition: border-color 0.2s ease, background-color 0.2s ease;
}
.feat-card.on {
  border-color: var(--color-primary);
  background: var(--color-primary-glow);
}
.feat-icon {
  font-size: 22px;
  flex: none;
}
.feat-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.feat-desc {
  font-size: 12px;
  color: var(--color-text-3);
  line-height: 1.4;
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
.api-meta {
  color: var(--color-text-3);
  font-size: 12px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 模型接入行状态点：使用中=主色实心，未启用=灰（替换文字 tag） */
.api-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--color-fill-3, #c9cdd4);
}
.api-dot.on {
  background: var(--color-primary);
}
.api-empty {
  padding: 8px 0 2px;
}
/* 展开区 2×2 grid（名称/Key/BaseURL/模型），动作行通栏 */
.api-edit-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
  max-width: 640px;
}
.api-edit-grid :deep(.arco-form-item) {
  margin-bottom: 8px;
}
.api-edit-actions {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
}
/* 每日计划与复盘：左右双栏（窄窗单列） */
.ai-jobs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
@media (max-width: 900px) {
  .ai-jobs {
    grid-template-columns: 1fr;
  }
}
.ai-job-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
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
/* 设置行：标签左、控件右，一行一条 */
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
  font-size: var(--zt-t3);
  color: var(--color-text-2);
  flex-shrink: 0;
}
.doc-link {
  color: var(--color-primary);
  cursor: pointer;
}
.doc-link:hover {
  text-decoration: underline;
}
/* 番茄钟页：满宽多栏网格（窄窗自动单列）；节奏盘通栏占整行 */
.pomo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 16px 24px;
  max-width: 1040px;
  align-items: start;
}
.pomo-grid > .is-wide {
  grid-column: 1 / -1;
}
/* 节奏盘：四拨盘格（NumberSpinner + 下方 t3 标注） */
.pomo-dials {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px 16px;
}
.pomo-dial {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}
.pomo-dial-k {
  font-size: var(--zt-t3);
  font-weight: 600;
  color: var(--color-text-2);
}
/* 菜单按钮文案行：输入框随列宽伸缩 */
.pomo-menu-line :deep(.arco-input-wrapper) {
  flex: 1;
}
/* 番茄钟节奏预设标签：可点击回填；恰等于预设值时主色 pill（chips 选中范式） */
.pomo-preset {
  cursor: pointer;
  user-select: none;
}
.pomo-preset.on {
  color: var(--color-primary) !important;
  background: color-mix(in srgb, var(--color-primary) 10%, transparent) !important;
  border-color: color-mix(in srgb, var(--color-primary) 45%, transparent) !important;
  font-weight: 600;
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
.sys-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.upd-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}
.upd-alert {
  margin-top: 10px;
  width: fit-content;
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

/* —— 插件页 —— */
.plugin-settings {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 880px;
  padding-bottom: 8px;
}
.plugin-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.plugin-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--color-text-1);
}
.plugin-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-3);
  line-height: 1.45;
}
/* —— 导入块 —— */
.pc-muted {
  color: var(--color-text-3);
  font-size: 12px;
}
.pc-add-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.pc-add-row .arco-input-wrapper {
  flex: 1;
  min-width: 220px;
}
.plug-import-actions {
  margin-top: 8px;
}
.pc-preview {
  margin-top: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--color-border-2);
  background: var(--color-bg-2, #fff);
}
.pc-preview.ok {
  border-color: rgb(var(--green-6, 0 180 42));
}
.pc-preview.bad {
  border-color: rgb(var(--red-6, 245 63 63));
}
.pc-preview-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.pc-err-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: rgb(var(--red-6, 245 63 63));
  font-size: 12px;
}
.pc-advanced {
  margin-top: 12px;
  border-top: 1px dashed var(--color-border-2);
}
.pc-advanced :deep(.arco-collapse-item) {
  border: none;
}
.pc-advanced :deep(.arco-collapse-item-header) {
  padding-left: 0;
}
.pc-advanced :deep(.arco-collapse-item-content-box) {
  padding-left: 0;
}
/* —— 列表块：每插件一行（名称+标签组：类型/分类/写回/触发，行尾四动作） —— */
.plug-list {
  display: flex;
  flex-direction: column;
}
.plug-item {
  padding: 7px 2px;
  border-bottom: 1px solid var(--color-border-2);
}
.plug-item:last-child {
  border-bottom: none;
}
.plug-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap; /* 标签多时折行，动作恒居行尾 */
  gap: 4px;
}
.plug-actions {
  flex: none;
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 2px;
}
/* —— 展开面板：编辑 / 参数预设 / 自动运行授权 —— */
.plug-expand {
  margin-top: 8px;
  padding: 4px 12px 10px;
  background: var(--color-fill-1, #f7f8fa);
  border-radius: 8px;
}
.plug-edit-sec {
  margin-top: 8px;
}
.plug-edit-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.plug-meta-line {
  margin-top: 6px;
}
.trig-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.preset-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.preset-k {
  min-width: 120px;
  font-size: 12.5px;
  color: var(--color-text-2);
}
/* 可变长度参数：多行值 + 加一条 */
.preset-many {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
.preset-many-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* —— 校验失败 —— */
.plug-fail-box {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-danger-light-1, #ffece8);
  font-size: 12px;
}
.plug-fail-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--color-text-1);
}
.plug-fail-item {
  margin-bottom: 8px;
}
.plug-fail-item ul {
  margin: 4px 0 0;
  padding-left: 18px;
  color: var(--color-text-2);
}
.plug-fail-item code {
  font-size: 11px;
  word-break: break-all;
}

/* —— 备份页 —— */
.bk-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bk-policy {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.bk-policy-k {
  font-size: 13px;
  color: var(--color-text-2);
}
.bk-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bk-snapshots :deep(.arco-table-th) {
  background: var(--color-fill-1);
}
</style>
