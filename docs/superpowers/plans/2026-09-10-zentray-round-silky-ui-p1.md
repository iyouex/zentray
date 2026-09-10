# ZenTray 圆润丝滑 UI 改造 — P1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地设计令牌层（圆角/投影/动效/色彩）+ `theme.js` 外观工具 + 路由过渡 + `appearance.motion/shape` 设置项 + TaskList 卡片柔润改造，构成 spec 的 P1 交付。

**Architecture:** 方案 1（令牌层 + Arco CSS 变量覆盖）：`styles.css` 定义 `--zt-*` 令牌与 `.zt-*` 组件类，body class（`zt-motion-off` / `zt-shape-crisp` / 主题 class）切换档位；`theme.js` 提供 `categoryColor()` 与 `applyAppearance()`；`App.vue` 给 `router-view` 包 `<Transition>`；Python 侧仅 `settings_manager.py` 加两个带默认值的键。

**Tech Stack:** Vue 3 + Arco Design 2.56.3（已装）+ Vite；Python/PySide6（本计划仅动 settings_manager）；零新增依赖。

**Spec:** `docs/superpowers/specs/2026-09-10-zentray-round-silky-ui-design.md`（令牌值见其 §2，本计划已内联，冲突时以 spec 为准）

## Global Constraints

- 工作区存在**与本计划无关的未提交改动**（dialog/web_host 加固等）。提交一律显式 `git add <本任务文件列表>`，**严禁 `git add -A` / `git add .`**。
- 提交信息：`feat:` / `fix:` 前缀 + 中文描述（CLAUDE.md 约定）。
- 零新增 npm / pip 依赖。
- P1 **不重建 `web/dist`**（spec §7：P2 统一重出 dist）。需要编译校验时输出到临时目录：`npx vite build --outDir /tmp/zt-dist-p1 --emptyOutDir`。
- Python 测试命令统一：`QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest <path> -q`（在仓库根执行）。
- 令牌值（spec §2，逐字）：圆角 win/card/md/pill = `22px/16px/12px/999px`（利落档 `12/8/6/999`）；hover 投影 `0 10px 26px rgba(0,0,0,.40)`；`--zt-ease-out: cubic-bezier(0.22,1,0.36,1)`；`--zt-ease-spring: cubic-bezier(0.34,1.56,0.64,1)`；时长 fast/page/dialog = `180ms/260ms/280ms`，关闭 `140ms`。
- 优先级色：高 `#F87171`、中 `#FB923C`、低 `#94A3B8`。紧迫度：`>24h #94A3B8`、`<24h #FBBF24`、逾期 `#F87171`。
- 分类色板 8 席：`#14b8a6, #a78bfa, #fbbf24, #38bdf8, #fb7185, #a3e635, #94a3b8, #e879f9`；「工作/个人/学习」固定落前三席。

---

### Task 1: Python `appearance.motion/shape` 设置键（TDD）

**Files:**
- Modify: `zentray/services/settings_manager.py:132-136`（AppearanceSettings 数据类）、`:472-479`（`_apply_dict` 的 appearance 分支）
- Test: `tests/unit/test_appearance_settings.py`（新建）

**Interfaces:**
- Produces: `AppearanceSettings.motion: str`（`"full"|"off"`，默认 `"full"`）、`AppearanceSettings.shape: str`（`"round"|"crisp"`，默认 `"round"`）；`sm.appearance.motion` / `sm.appearance.shape` 经 `asdict` 自动进 `settings.json` 的 `appearance` 段（`settings_manager.py:578` 已有，无需改）。

- [ ] **Step 1: 写失败测试**

```python
"""appearance 新键 motion/shape：默认值、非法值回退、往返持久化（spec §5）。"""
import json

from zentray.services import settings_manager as sm_mod
from zentray.services.settings_manager import SettingsManager

# 注意：SETTINGS_FILE 是模块级变量且被 tmp_data_dir fixture monkeypatch，
# 必须经 sm_mod.SETTINGS_FILE 运行时取属性（reload() 自身会重置 _instance）。


def test_appearance_defaults(tmp_data_dir):
    sm = SettingsManager.reload()
    assert sm.appearance.motion == "full"
    assert sm.appearance.shape == "round"


def test_appearance_invalid_values_fall_back(tmp_data_dir):
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(
        json.dumps({"appearance": {"theme": "dark", "motion": "banana", "shape": 3}}),
        encoding="utf-8",
    )
    sm = SettingsManager.reload()
    assert sm.appearance.motion == "full"
    assert sm.appearance.shape == "round"
    assert sm.appearance.theme == "dark"


def test_appearance_roundtrip(tmp_data_dir):
    sm = SettingsManager.reload()
    sm.appearance.motion = "off"
    sm.appearance.shape = "crisp"
    sm.save()
    sm2 = SettingsManager.reload()
    assert sm2.appearance.motion == "off"
    assert sm2.appearance.shape == "crisp"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/unit/test_appearance_settings.py -q`
Expected: FAIL（`AttributeError: ... no attribute 'motion'` 或断言不等）

- [ ] **Step 3: 最小实现**

数据类（`settings_manager.py:132`）改为：

```python
@dataclass
class AppearanceSettings:
    """系统/外观。theme: light | dark | system；autostart 为开机自启偏好；
    motion: full|off 界面动效开关；shape: round|crisp 形状风格。"""

    theme: str = "system"
    autostart: bool = False
    motion: str = "full"
    shape: str = "round"
```

`_apply_dict` 的 appearance 分支（`settings_manager.py:472` 附近）在解析 `autostart` 之后补：

```python
            motion = (a.get("motion") or "full").lower()
            if motion not in ("full", "off"):
                motion = "full"
            shape = (a.get("shape") or "round").lower()
            if shape not in ("round", "crisp"):
                shape = "round"
```

并把构造改为：

```python
            self._settings.appearance = AppearanceSettings(
                theme=theme,
                autostart=autostart,
                motion=motion,
                shape=shape,
            )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/unit/test_appearance_settings.py tests/unit/test_feature_migration_v38.py -q`
Expected: 全部 PASS（含既有迁移测试无回归）

- [ ] **Step 5: 提交**

```bash
git add zentray/services/settings_manager.py tests/unit/test_appearance_settings.py
git commit -m "feat(settings): appearance 新增 motion/shape 键（默认 full/round，旧配置兼容）"
```

---

### Task 2: `theme.js` — `categoryColor()` 与 `applyAppearance()`

**Files:**
- Modify: `web/src/theme.js`（文件末尾追加）

**Interfaces:**
- Produces: `categoryColor(name: string): string`（返回 `#rrggbb`，纯函数不触 DOM，同名稳定）；`applyAppearance(prefs: {motion?: string, shape?: string}): {motion, shape}`（非法值归一到 `full`/`round`，写 body class `zt-motion-off`/`zt-shape-crisp`）。Task 4/5/6 依赖这两个签名。

- [ ] **Step 1: 追加实现**

```js
/**
 * 分类识别色：固定 8 色板稳定映射（spec §2）。
 * 默认分类「工作/个人/学习」固定落前三席；其余分类按名称 hash，
 * 保证同名永远同色。
 */
const CATEGORY_PALETTE = [
  '#14b8a6', // teal    工作
  '#a78bfa', // violet  个人
  '#fbbf24', // amber   学习
  '#38bdf8', // sky
  '#fb7185', // rose
  '#a3e635', // lime
  '#94a3b8', // slate
  '#e879f9', // fuchsia
]
const KNOWN_CATEGORY_SEAT = { 工作: 0, 个人: 1, 学习: 2 }

export function categoryColor(name) {
  const s = String(name || '').trim()
  if (Object.prototype.hasOwnProperty.call(KNOWN_CATEGORY_SEAT, s)) {
    return CATEGORY_PALETTE[KNOWN_CATEGORY_SEAT[s]]
  }
  let h = 0
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) >>> 0
  return CATEGORY_PALETTE[h % CATEGORY_PALETTE.length]
}

/**
 * 外观偏好：动效开关与形状风格（spec §5）。
 * body class: zt-motion-off / zt-shape-crisp，令牌层按 class 切换档位。
 */
export function applyAppearance(prefs) {
  const motion = prefs?.motion === 'off' ? 'off' : 'full'
  const shape = prefs?.shape === 'crisp' ? 'crisp' : 'round'
  const root = document.body
  root.classList.toggle('zt-motion-off', motion === 'off')
  root.classList.toggle('zt-shape-crisp', shape === 'crisp')
  root.dataset.ztMotion = motion
  root.dataset.ztShape = shape
  return { motion, shape }
}
```

（设计说明：spec §2 说「固定偏移量」校正默认分类席位，实现用显式 `KNOWN_CATEGORY_SEAT` 映射达成同一效果——比偏移量可读且不依赖 hash 具体值。）

- [ ] **Step 2: 可运行检查（纯函数断言）**

Run（仓库根）:
```bash
cd web && node --input-type=module -e "
import { categoryColor } from './src/theme.js'
console.assert(categoryColor('工作') === '#14b8a6', '工作 seat')
console.assert(categoryColor('个人') === '#a78bfa', '个人 seat')
console.assert(categoryColor('学习') === '#fbbf24', '学习 seat')
console.assert(categoryColor('临时分类A') === categoryColor('临时分类A'), '同名稳定')
console.assert(/^#[0-9a-f]{6}$/.test(categoryColor('任意')), 'hex 格式')
console.log('categoryColor OK')
"
```
Expected: 输出 `categoryColor OK`，无 AssertionError。

- [ ] **Step 3: 提交**

```bash
git add web/src/theme.js
git commit -m "feat(ui): theme.js 增加 categoryColor 分类色与 applyAppearance 外观偏好"
```

---

### Task 3: `styles.css` 设计令牌层 + Arco 覆盖 + 动效类

**Files:**
- Modify: `web/src/styles.css`（文件末尾追加；并把 `:154-167` 的 `.task-card-item` 圆角从 `10px` 升到令牌引用）

**Interfaces:**
- Produces（CSS 契约，Task 4/6 消费）：
  - 令牌：`--zt-radius-win/card/md/pill`、`--zt-shadow-card(-hover)`、`--zt-ease-out/spring`、`--zt-dur-fast/page/dialog/off`
  - 卡片自定义属性：`--cat-color`（Task 6 在卡片元素上内联注入）
  - 优先级 chip：`.zt-pri-h/.zt-pri-m/.zt-pri-l`；紧迫度：`.zt-dl-late/.zt-dl-soon`
  - 路由过渡：`.zt-page-enter-active/-leave-active/-enter-from/-leave-to`；列表动效：`.zt-list-enter-active/-leave-active/-enter-from/-leave-to/-move`
  - 档位 class：`body.zt-motion-off`、`body.zt-shape-crisp`

- [ ] **Step 1: 升级 `.task-card-item` 圆角与呼吸条**

把现有 `.task-card-item`（`styles.css:154-167`）整块替换为：

```css
/* 48px 舒缓型 Task Card 架构（spec §3：圆角16 + 分类色呼吸条） */
.task-card-item {
  position: relative;
  min-height: var(--task-card-height);
  box-sizing: border-box;
  padding: 8px 14px 8px 18px;
  margin-bottom: 8px;
  border-radius: var(--zt-radius-card, 16px);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  box-shadow: var(--zt-shadow-card);
  transition: transform var(--zt-dur-fast) var(--zt-ease-out),
    box-shadow var(--zt-dur-fast) ease, background 0.2s ease;
}

.task-card-item:hover {
  background: var(--color-surface-hover);
  transform: translateY(-3px);
  box-shadow: var(--zt-shadow-card-hover);
}

/* 分类色呼吸条：默认内缩 12px，hover 各伸展 4px（逾期红优先由 --cat-color 控制） */
.task-card-item::before {
  content: "";
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 999px;
  background: var(--cat-color, var(--color-border));
  transition: top var(--zt-dur-fast) var(--zt-ease-out),
    bottom var(--zt-dur-fast) var(--zt-ease-out);
}

.task-card-item:hover::before {
  top: 8px;
  bottom: 8px;
}
```

- [ ] **Step 2: 文件末尾追加令牌层与动效**

```css
/* ================= 设计令牌（spec §2） ================= */
:root {
  --zt-radius-win: 22px;
  --zt-radius-card: 16px;
  --zt-radius-md: 12px;
  --zt-radius-pill: 999px;
  --zt-shadow-card: 0 4px 14px rgba(0, 0, 0, 0.25);
  --zt-shadow-card-hover: 0 10px 26px rgba(0, 0, 0, 0.4);
  --zt-ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --zt-ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --zt-dur-fast: 180ms;
  --zt-dur-page: 260ms;
  --zt-dur-dialog: 280ms;
  --zt-dur-off: 140ms;
  /* 优先级/紧迫度 */
  --zt-pri-high: #f87171;
  --zt-pri-mid: #fb923c;
  --zt-pri-low: #94a3b8;
  --zt-due-soon: #fbbf24;
  --zt-due-late: #f87171;
}

/* 形状两档：利落（spec §5 shape=crisp） */
body.zt-shape-crisp {
  --zt-radius-win: 12px;
  --zt-radius-card: 8px;
  --zt-radius-md: 6px;
}

/* 浅色主题投影减半（spec §2） */
body.theme-light {
  --zt-shadow-card: 0 4px 14px rgba(15, 23, 42, 0.12);
  --zt-shadow-card-hover: 0 10px 26px rgba(15, 23, 42, 0.2);
}

/* ================= Arco 圆角覆盖（spec §6） ================= */
body {
  --border-radius-small: 8px;
  --border-radius-medium: 12px;
  --border-radius-large: 16px;
}

body.zt-shape-crisp {
  --border-radius-small: 4px;
  --border-radius-medium: 6px;
  --border-radius-large: 8px;
}

.arco-btn {
  border-radius: var(--zt-radius-pill);
}

.arco-message {
  border-radius: var(--zt-radius-pill);
}

/* 滚动条：8px 圆角细条（spec §3） */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 999px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-subdued);
}

::-webkit-scrollbar-track {
  background: transparent;
}

/* 主题切换：仅背景过渡，防意外动画（spec §4） */
body {
  transition: background-color 200ms ease;
}

/* ================= 优先级 chip / 紧迫度（spec §2） ================= */
.zt-pri {
  font-size: 10px;
  line-height: 1.5;
  padding: 1px 7px;
  border-radius: var(--zt-radius-pill);
  flex: none;
}

.zt-pri-h { background: color-mix(in srgb, var(--zt-pri-high) 16%, transparent); color: var(--zt-pri-high); }
.zt-pri-m { background: color-mix(in srgb, var(--zt-pri-mid) 16%, transparent); color: var(--zt-pri-mid); }
.zt-pri-l { background: color-mix(in srgb, var(--zt-pri-low) 16%, transparent); color: var(--zt-pri-low); }

.zt-dl-late { color: var(--zt-due-late); font-weight: 600; }
.zt-dl-soon { color: var(--zt-due-soon); }

/* ================= 路由过渡 pt-b 弹性聚拢（spec §4） ================= */
.zt-page-enter-active {
  transition: opacity var(--zt-dur-page) var(--zt-ease-spring),
    transform var(--zt-dur-page) var(--zt-ease-spring);
}

.zt-page-leave-active {
  transition: opacity var(--zt-dur-off) ease;
}

.zt-page-enter-from {
  opacity: 0;
  transform: scale(0.96);
}

.zt-page-leave-to {
  opacity: 0;
}

/* ================= 列表增删（spec §4） ================= */
.zt-list-enter-active {
  transition: opacity var(--zt-dur-fast) var(--zt-ease-out),
    transform var(--zt-dur-fast) var(--zt-ease-out);
}

.zt-list-leave-active {
  transition: opacity var(--zt-dur-off) ease, transform var(--zt-dur-off) ease;
  position: absolute;
  width: 100%;
}

.zt-list-move {
  transition: transform var(--zt-dur-fast) var(--zt-ease-out);
}

.zt-list-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.zt-list-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* ================= 动效降级（spec §4） ================= */
body.zt-motion-off *,
body.zt-motion-off *::before,
body.zt-motion-off *::after {
  transition-duration: var(--zt-dur-off) !important;
  animation-duration: var(--zt-dur-off) !important;
  animation-iteration-count: 1 !important;
}

body.zt-motion-off .zt-page-enter-from,
body.zt-motion-off .zt-list-enter-from,
body.zt-motion-off .zt-list-leave-to,
body.zt-motion-off .task-card-item:hover {
  transform: none;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition-duration: 140ms !important;
    animation-duration: 140ms !important;
  }

  .zt-page-enter-from,
  .zt-list-enter-from,
  .task-card-item:hover {
    transform: none;
  }
}
```

- [ ] **Step 3: 编译校验（不动已跟踪的 dist）**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p1 --emptyOutDir`
Expected: 构建成功，无 CSS 语法错误。

- [ ] **Step 4: 提交**

```bash
git add web/src/styles.css
git commit -m "feat(ui): 设计令牌层——圆角/投影/动效/优先级色与 Arco 圆角覆盖"
```

---

### Task 4: `App.vue` 路由过渡 + 外观偏好接线

**Files:**
- Modify: `web/src/App.vue:1-5`（模板）、`:9`（import）、`:111-117`（onMounted 内）

**Interfaces:**
- Consumes: Task 2 的 `applyAppearance(prefs)`；Task 3 的 `.zt-page-*` 过渡类。
- Produces: `getSettings()` 返回的 `s.appearance` 被消费（`{theme, motion, shape}`），body class 生效。

- [ ] **Step 1: 模板改写（`App.vue:2-4`）**

```html
<a-config-provider :update-at-scroll="true">
  <router-view :key="viewKey" v-slot="{ Component }">
    <Transition name="zt-page" mode="out-in">
      <component :is="Component" />
    </Transition>
  </router-view>
</a-config-provider>
```

- [ ] **Step 2: import 与接线**

`App.vue:9` 改为：

```js
import { applyAppearance, applyTheme, watchSystemTheme } from './theme'
```

`onMounted` 中 `getSettings` 成功分支（现 `themeMode.value = s?.appearance?.theme || 'system'`）后补一行（在 `applyTheme` 调用之前）：

```js
    applyAppearance(s?.appearance)
```

失败分支（`catch`）补：

```js
    applyAppearance()
```

- [ ] **Step 3: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p1 --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 4: 提交**

```bash
git add web/src/App.vue
git commit -m "feat(ui): 路由过渡 pt-b 弹性聚拢 + 外观偏好接线"
```

---

### Task 5: `Settings.vue` 外观区两个控件 + 立即预览

**Files:**
- Modify: `web/src/views/Settings.vue:388-395`（外观卡模板）、`:498`（import）、`:573`（form 默认值）、`:702-706` 附近（新增预览函数）、`:886-887`（backfill）

**Interfaces:**
- Consumes: Task 2 的 `applyAppearance`；Task 1 的 `appearance.motion/shape`（经 `getSettings`/保存往返）。
- Produces: 无（终端 UI）。

- [ ] **Step 1: form 默认值（`:573`）**

```js
    appearance: { theme: 'system', autostart: false, motion: 'full', shape: 'round' },
```

- [ ] **Step 2: backfill（`:886-887` 后追加两行）**

```js
  if (form.appearance.motion == null) form.appearance.motion = 'full'
  if (form.appearance.shape == null) form.appearance.shape = 'round'
```

- [ ] **Step 3: import（`:498`）**

```js
import { applyAppearance, applyTheme } from '@/theme'
```

- [ ] **Step 4: 预览函数（`onThemePreview` 旁新增）**

```js
function onAppearancePreview() {
  applyAppearance(form.appearance)
}
```

- [ ] **Step 5: 外观卡模板（主题 form-item 之后、`a-alert` 之前插入）**

```html
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
```

（既有 `a-alert`「主题预览立即生效；点底部保存写入配置」的文案对这两项同样成立，不另加提示。）

- [ ] **Step 6: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p1 --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 7: 提交**

```bash
git add web/src/views/Settings.vue
git commit -m "feat(ui): 设置页外观区新增界面动效/形状风格控件"
```

---

### Task 6: `TaskList.vue` 卡片柔润改造 + `Home` 验证

**Files:**
- Modify: `web/src/views/TaskList.vue:24-48`（列表模板）、`:94`（import 区）、`:113` 后（新增辅助函数）
- Verify: `web/src/views/Home.vue`（预期**零代码改动**——全局令牌与 Arco 覆盖已覆盖其观感）

**Interfaces:**
- Consumes: Task 2 的 `categoryColor(name)`；Task 3 的 `--cat-color`、`.zt-pri-*`、`.zt-dl-*`、`.zt-list-*`。

- [ ] **Step 1: script 增加工具（`TaskList.vue`，import 区加）**

```js
import { categoryColor } from '@/theme'
```

`selectedId` 定义之后加：

```js
const PRI_CLASS = { high: 'zt-pri-h', medium: 'zt-pri-m', low: 'zt-pri-l' }
const PRI_LABEL = { high: '高', medium: '中', low: '低' }

function deadlineInfo(item) {
  if (!item.deadline) return null
  const t = new Date(String(item.deadline).replace(' ', 'T')).getTime()
  if (Number.isNaN(t)) return null
  const diff = t - Date.now()
  if (diff < 0) return { text: item.deadline, cls: 'zt-dl-late' }
  if (diff < 24 * 3600 * 1000) return { text: item.deadline, cls: 'zt-dl-soon' }
  return { text: item.deadline, cls: '' }
}
```

- [ ] **Step 2: 列表模板改写（`:24-48` 的 `.task-card-list` 块）**

```html
          <div v-if="tasks.length" class="task-card-list">
            <TransitionGroup name="zt-list" tag="div" class="task-card-list">
              <div
                v-for="item in tasks"
                :key="item.id"
                class="task-card-item"
                :class="{ active: item.id === selectedId }"
                :style="{ '--cat-color': categoryColor(item.category) }"
                @click="selectedId = item.id"
              >
                <div class="task-card-main">
                  <span class="task-card-title">
                    {{ item.title }}
                    <span v-if="item.priority" class="zt-pri" :class="PRI_CLASS[item.priority] || 'zt-pri-l'">
                      {{ PRI_LABEL[item.priority] || '低' }}
                    </span>
                  </span>
                  <div class="task-card-meta">
                    <a-tag
                      v-if="item.category"
                      size="small"
                      :style="{
                        color: categoryColor(item.category),
                        background: categoryColor(item.category) + '24',
                        borderRadius: '999px',
                      }"
                    >
                      {{ item.category }}
                    </a-tag>
                    <span class="task-card-sub">进度: {{ item.progress || 0 }}%</span>
                    <span
                      v-if="deadlineInfo(item)"
                      class="task-card-sub"
                      :class="deadlineInfo(item).cls"
                    >
                      截止: {{ deadlineInfo(item).text }}
                    </span>
                  </div>
                  <div v-if="item.progress" class="zt-card-prog">
                    <i :style="{ width: (item.progress || 0) + '%', background: categoryColor(item.category) }" />
                  </div>
                </div>
                <PhCheckCircle
                  v-if="item.progress === 100"
                  class="icon-check-animated"
                  :size="22"
                  weight="fill"
                />
              </div>
            </TransitionGroup>
          </div>
```

（外层 `v-if` 的 div 保留原结构：`<div v-if="tasks.length" class="task-card-list">` 内直接放 `TransitionGroup` 会有嵌套重复——实际改法是把原来的 `<div ... class="task-card-list">` 整体替换为 `<TransitionGroup name="zt-list" tag="div" class="task-card-list">`，闭合标签对应替换。）

- [ ] **Step 3: 进度条样式（TaskList `<style scoped>` 末尾追加）**

```css
.zt-card-prog {
  height: 4px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
  margin-top: 6px;
  overflow: hidden;
}

.zt-card-prog i {
  display: block;
  height: 100%;
  border-radius: 999px;
}
```

- [ ] **Step 4: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p1 --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 5: Home 零改动确认**

Run: `git diff --stat web/src/views/Home.vue`
Expected: 无输出（Home 由全局令牌自动覆盖）。

- [ ] **Step 6: 提交**

```bash
git add web/src/views/TaskList.vue
git commit -m "feat(ui): 任务卡柔润改造——呼吸条/优先级chip/进度条/紧迫度/列表动效"
```

---

### Task 7: P1 收尾验证

**Files:**
- 无代码改动；只跑验证并汇报。

**Interfaces:**
- Consumes: 全部前序任务。

- [ ] **Step 1: Python 全量回归**

Run: `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ -q`
Expected: 全部 PASS（原 108 项 + Task 1 新增 3 项）。

- [ ] **Step 2: 前端构建校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p1 --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 3: 提交面检查**

Run: `git log --oneline staging..HEAD && git status --short | grep -E "styles.css|theme.js|App.vue|Settings.vue|TaskList.vue|settings_manager|test_appearance"`
Expected: 恰好 6 个 P1 提交；上述文件无残留未提交改动；`web/dist` 无本计划产生的改动。

- [ ] **Step 4: 手测清单（交给用户，dev server 可选）**

```bash
cd web && npx vite dev
```

清单：任务列表 hover 呼吸条/上浮、优先级 chip 三色、逾期红/临期琥珀、进度条分类色；设置页切「形状风格→利落」圆角立变、「界面动效→关」过渡变纯淡入；保存后重开生效。

---

## Self-Review 记录

- **Spec P1 覆盖**：令牌层（Task 3）✓ theme.js（Task 2）✓ App.vue 过渡（Task 4）✓ 设置项含 Python 键（Task 1/5）✓ TaskList（Task 6）✓ Home 零改动验证（Task 6 Step 5 / Task 7）✓。
- **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码。
- **类型/命名一致性**：`categoryColor(name)->'#rrggbb'`、`applyAppearance(prefs)->{motion,shape}`、CSS class 名在 Task 3 定义与 Task 4/6 使用处逐字一致（`zt-page-*`、`zt-list-*`、`zt-pri-*`、`zt-dl-*`、`--cat-color`）。
- **已知取舍**：spec §2「hash + 固定偏移」实现为「显式席位表 + hash」，语义等价且可在 Task 2 Step 2 用断言验证；`.zt-list-leave-active` 用 `position: absolute` 防 TransitionGroup 移除时跳动。
