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
          <a-menu-item key="ai">✨ AI 能力</a-menu-item>
          <a-menu-item key="notify">🔔 通知</a-menu-item>
          <a-menu-item key="polling">📋 任务</a-menu-item>
          <a-menu-item key="pomodoro">🍅 番茄钟</a-menu-item>
          <a-menu-item key="categories">🏷️ 分类</a-menu-item>
          <a-menu-item key="system">🖥️ 系统</a-menu-item>
          <a-menu-item key="backup">💾 备份</a-menu-item>
          <a-menu-item key="history">📜 历史</a-menu-item>
        </a-menu>

        <div class="settings-body" :class="{ 'is-ai': mainKey === 'ai', 'is-history': mainKey === 'history' }">
          <template v-if="mainKey === 'ai'">
            <!-- 场景能力开关：卡片网格，默认全关 -->
            <section class="feat-section">
              <div class="feat-grid">
                <div
                  v-for="f in AI_FEATURES"
                  :key="f.key"
                  class="feat-card"
                  :class="{ on: form.ai.features[f.key] }"
                >
                  <span class="feat-icon">{{ f.icon }}</span>
                  <div class="feat-info">
                    <span class="feat-name">{{ f.name }}</span>
                    <span class="feat-desc">{{ f.desc }}</span>
                  </div>
                  <a-switch v-model="form.ai.features[f.key]" size="small" />
                </div>
              </div>
              <p class="hint">
                场景能力默认关闭；开启后立即出现在对应入口，模型调用复用下方「模型接入」中的当前 API。
              </p>
            </section>

            <a-tabs class="ai-tabs" type="rounded" v-model:active-key="aiTab">
              <a-tab-pane key="plan" title="每日计划">
                <JobEditor v-model="form.ai.plan" kind-label="每日计划" />
              </a-tab-pane>

              <a-tab-pane key="review" title="每日复盘">
                <JobEditor v-model="form.ai.review" kind-label="每日复盘" />
              </a-tab-pane>

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
            </a-tabs>
          </template>

          <!-- 通知：从 AI 页拆出的独立页（固定渠道，不可增删，可折叠） -->
          <template v-else-if="mainKey === 'notify'">
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
            </div>
          </template>

          <!-- 备份：五卡片（存储目录 / 手动备份 / 自动策略 / 恢复 / 历史快照） -->
          <template v-else-if="mainKey === 'backup'">
            <div class="system-settings">
              <a-card class="sys-card" :bordered="false" title="备份存储目录">
                <div class="sys-row">
                  <div style="min-width: 0">
                    <div class="sys-title">
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
              </a-card>

              <a-card class="sys-card" :bordered="false" title="手动即时备份">
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
              </a-card>

              <a-card class="sys-card" :bordered="false" title="自动周期备份策略">
                <div class="sys-row">
                  <div>
                    <div class="sys-title">自动备份</div>
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
              </a-card>

              <a-card class="sys-card" :bordered="false" title="从备份文件恢复">
                <div class="sys-import-row">
                  <a-input
                    v-model="importPath"
                    placeholder="本机 zip 绝对路径，或点右侧按钮选择"
                    allow-clear
                    @clear="importNeedsPassword = false"
                  />
                  <a-button @click="onPickBackupFile">选择文件</a-button>
                  <a-button type="primary" status="warning" :loading="importLoading" @click="onImportBackup">
                    恢复
                  </a-button>
                </div>
                <div v-if="importNeedsPassword" class="bk-inline" style="margin-top: 10px">
                  <span class="bk-policy-k">备份密码</span>
                  <a-input-password v-model="importPassword" placeholder="该备份已加密" style="width: 240px" allow-clear />
                </div>
                <a-alert type="warning" style="margin-top: 10px">
                  恢复为<strong>替换</strong>模式：覆盖本地所选数据；操作前会自动写入安全备份。
                </a-alert>
                <p v-if="lastImportMsg" class="sys-path">{{ lastImportMsg }}</p>
              </a-card>

              <a-card class="sys-card bk-snapshots" :bordered="false" title="历史备份快照">
                <template #extra>
                  <a-space>
                    <a-tag size="small">{{ snapshots.length }} 个备份</a-tag>
                    <a-button size="small" :loading="snapshotsLoading" @click="loadBackups">刷新</a-button>
                  </a-space>
                </template>
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
  deleteBackup,
  exportBackup,
  getSettings,
  getSystemStatus,
  importBackup,
  listBackups,
  packArchive,
  pickPath,
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
const mainKey = ref('ai')
const aiTab = ref('plan')
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

// —— 备份页 ——
const backupStatus = ref({}) // /api/system/status 的 backup 节（dir/default_dir/custom/last_backup_at）
const snapshots = ref([])
const snapshotsLoading = ref(false)
const encryptEnabled = ref(false)
const backupPassword = ref('')
const importNeedsPassword = ref(false)
const importPassword = ref('')
const saveAsLoading = ref(false)
const savedBackupDir = ref('')

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
      features: { smart_parse: false, image_ocr: false, task_suggest: false },
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
    backup: { dir: '', auto_enabled: false, interval_days: 1, keep: 7, trigger_hour: 9 },
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
  if (key === 'backup') loadBackupPage()
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
    backupStatus.value = data?.backup || {}
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

/** 原生文件选择器挑备份 zip；若快照表里是加密包，预置密码框 */
async function onPickBackupFile() {
  const r = await pickPath('file', { title: '选择备份文件', startDir: backupDirDisplay.value })
  if (r.cancelled || !r.path) {
    if (!r.id) Message.info('仅桌面端支持文件选择')
    return
  }
  importPath.value = r.path
  importNeedsPassword.value = snapshots.value.some((s) => s.path === r.path && s.encrypted)
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

/** 快照行「恢复」：回填路径 + 密码态，走 onImportBackup 的确认流程 */
function restoreSnapshot(record) {
  importPath.value = record.path
  importNeedsPassword.value = !!record.encrypted
  importPassword.value = ''
  onImportBackup()
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
/* AI 页：场景开关 + 标签栏固定，仅 pane 内容滚动 */
.settings-body.is-ai {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.settings-body.is-ai :deep(.ai-tabs),
.settings-body.is-ai :deep(.arco-tabs) {
  flex: 1;
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
/* AI 场景能力开关卡片网格 */
.feat-section {
  flex: none;
  margin-bottom: 4px;
}
.feat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
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
.feat-name {
  font-weight: 600;
  font-size: 13.5px;
}
.feat-desc {
  font-size: 12px;
  color: var(--color-text-3);
  line-height: 1.4;
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
