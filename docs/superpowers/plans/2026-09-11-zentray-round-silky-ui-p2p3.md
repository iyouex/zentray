# ZenTray 圆润丝滑 UI 改造 — P2+P3 全局铺开实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复「形状/动效开关无可见变化」bug（Arco 大表面未接令牌）并把圆润丝滑设计语言铺满全部 UI 页面——P2+P3 一次交付，dist 成对重建入库。

**Architecture:** spec §6 修订版（2026-09-11）：保留 `--border-radius-small/medium/large` 变量覆盖（构建产物中 123 处消费仍生效），**新增 Arco 接线层**把不消费变量的关键表面（`.arco-card` 写死 `--border-radius-none`=0px 等）直接接到 `--zt-*` 令牌；按钮圆润档胶囊、利落档小圆角；`motion=off` 语义收紧为彻底关闭（过渡 0s、动画 none，载入指示器豁免）。页内弹层走 dg-a 源点生长（Arco modal/drawer/dropdown 插入时 CSS animation，退出复用 Arco leave 类压时长）。绝大多数视图（TaskForm/Reminder/TaskAction/Periodic/SetupWizard/Home）由全局层自动覆盖、**零代码改动**，仅 QuickAdd/Progress/History/Settings 有少量定点编辑。

**Tech Stack:** 纯 CSS 为主（`web/src/styles.css`）+ 三个视图的少量样式行编辑；零新增 npm / pip 依赖；Python 侧零改动。

**Spec:** `docs/superpowers/specs/2026-09-10-zentray-round-silky-ui-design.md`（以 2026-09-11 修订版为准；令牌值见其 §2）

## Global Constraints

- 工作区存在**与本计划无关的未提交改动**（packaging、dialog/web_host 加固、main.py 等）。提交一律显式 `git add <本任务文件列表>`，**严禁 `git add -A` / `git add .`**。
- 提交信息：`feat:` / `fix:` 前缀 + 中文描述（CLAUDE.md 约定）。
- 零新增 npm / pip 依赖。
- **dist 只在 Task 5 重建**（`cd web && npm run build`，产出直接进 `web/dist` 并成对提交新旧 hash）。Task 1-4 的编译校验输出到临时目录：`cd web && npx vite build --outDir /tmp/zt-dist-p2 --emptyOutDir`。
- Python 回归命令（仓库根）：`QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ -q`（当前 112 项全绿；本计划不碰 Python，Task 5 全量跑一遍确认无意外）。
- 令牌值（spec §2，逐字）：圆角 card/md/pill = `16px/12px/999px`（利落档 `8/6/999`）；`--zt-ease-spring: cubic-bezier(0.34,1.56,0.64,1)`；时长 fast/dialog = `180ms/280ms`，关闭 `140ms`。
- **motion=off 语义（spec §6 修订）**：`transition-duration: 0s` + `animation: none`（彻底关闭），与 `prefers-reduced-motion` 的 140ms 纯淡入降级区分；`.arco-spin-*` 载入指示器豁免（功能反馈非装饰）。
- CSS 覆盖层的排序依据：`web/src/styles.css` 在构建中晚于 Arco 样式加载（P1 已验证 `.arco-btn` 覆盖生效），同等特异性下后写者胜——本计划所有 Arco 覆盖不需要 `!important`（motion-off 块与 leave 时长覆盖除外）。

---

### Task 1: styles.css — Arco 接线层 + motion-off 彻底关闭（bug 修复核心）

**Files:**
- Modify: `web/src/styles.css:278-297`（「Arco 圆角覆盖」整节替换）、`:384-402`（动效降级块替换）

**Interfaces:**
- Produces（全局 CSS 契约，本计划所有视图消费）：`.arco-card → var(--zt-radius-card)`、`.arco-tag → pill`、`.arco-btn` 圆润=pill / `body.zt-shape-crisp .arco-btn` = `var(--zt-radius-md)`、表格行 hover、输入聚焦 teal 亮环；`body.zt-motion-off` 下过渡 0s / 动画 none（spin 豁免）。

- [ ] **Step 1: 替换「Arco 圆角覆盖」节**

把 `styles.css:278-297`（从 `/* ================= Arco 圆角覆盖（spec §6） ================= */` 到 `.arco-message { border-radius: var(--zt-radius-pill); }` 的整块）替换为：

```css
/* ================= Arco 接线层（spec §6 2026-09-11 修订） ================= */
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

/* 大表面接线：Arco 不消费 radius 变量的部分直接接 zt 令牌 */
.arco-card {
  border-radius: var(--zt-radius-card);
}

.arco-tag {
  border-radius: var(--zt-radius-pill);
}

/* 按钮：圆润=胶囊、利落=小圆角（spec §6 修订，形状档在按钮上可见） */
.arco-btn {
  border-radius: var(--zt-radius-pill);
}

body.zt-shape-crisp .arco-btn {
  border-radius: var(--zt-radius-md);
}

.arco-message {
  border-radius: var(--zt-radius-pill);
}

/* 表格行 hover（spec §3） */
.arco-table-tr .arco-table-td {
  transition: background-color var(--zt-dur-fast) ease;
}

.arco-table-tr:not(.arco-table-tr-empty):hover .arco-table-td {
  background-color: var(--color-surface-hover);
}

/* 表单控件 teal 聚焦亮环（spec §3；error 红描边沿用 Arco 内置） */
.arco-input-wrapper:focus-within,
.arco-textarea-wrapper:focus-within {
  border-color: var(--color-primary-hover);
  box-shadow: 0 0 0 1.5px var(--color-primary-glow);
}
```

- [ ] **Step 2: 替换 motion-off 降级块**

把 `styles.css` 中现「动效降级（spec §4）」块（`body.zt-motion-off *, ...` 起至 `body.zt-motion-off .icon-check-animated { animation: none; }` 止，替换后行号约 410-428）整块替换为：

```css
/* ================= 动效降级（spec §6 修订：off = 彻底关闭） ================= */
body.zt-motion-off *,
body.zt-motion-off *::before,
body.zt-motion-off *::after {
  transition-duration: 0s !important;
  animation: none !important;
}

/* 载入指示器是功能反馈而非装饰动效，豁免（spec §3 a-spin 取主题主色） */
body.zt-motion-off .arco-icon-loading,
body.zt-motion-off .arco-icon-spin {
  animation: arco-loading-circle 1s infinite cubic-bezier(0, 0, 1, 1) !important;
}
```

注意：`@media (prefers-reduced-motion: reduce)` 块（其后的 140ms 纯淡入降级）**保持原样不删**。

- [ ] **Step 3: 编译校验 + 产物断言（不动已跟踪的 dist）**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p2 --emptyOutDir && grep -c "var(--zt-radius-card)" /tmp/zt-dist-p2/assets/*.css && grep -o "body.zt-shape-crisp .arco-btn{[^}]*}" /tmp/zt-dist-p2/assets/*.css`
Expected: 构建成功；`var(--zt-radius-card)` 出现 ≥2 次（令牌定义 + `.arco-card` 接线）；输出含 `body.zt-shape-crisp .arco-btn{border-radius:var(--zt-radius-md)}`。

- [ ] **Step 4: 提交**

```bash
git add web/src/styles.css
git commit -m "fix(ui): Arco 大表面接线 zt 令牌——卡片/按钮/标签随形状档翻转，动效关档彻底关闭"
```

---

### Task 2: styles.css — 页内弹层 dg-a 源点生长 + 宿主整窗入场 + Message 滑入

**Files:**
- Modify: `web/src/styles.css`（文件末尾追加一块；`@media (prefers-reduced-motion: reduce)` 块的选择器列表追加 `#app`）

**Interfaces:**
- Consumes: Task 1 后的 styles.css 令牌（`--zt-dur-*`、`--zt-ease-spring`）。
- Produces: `.arco-modal` / `.arco-drawer` 打开时 280ms 弹性源点生长；遮罩 `rgba(2,6,23,.45)` + 2px 模糊渐入；退出 140ms 收缩淡出；`.arco-dropdown` / `.arco-popover` 180ms 生长；Message 顶部滑入；`#app` 整窗一次入场（scale .97→1 + 淡入，源点偏下）。`body.zt-motion-off` 下以上 animation 全部被 Task 1 的 `animation: none !important` 关闭，无需额外规则。

- [ ] **Step 1: 文件末尾追加弹层动效块**

```css
/* ================= 弹层 dg-a 源点生长（spec §4） ================= */
@keyframes zt-dlg-in {
  from {
    opacity: 0;
    transform: scale(0.8);
  }
}

@keyframes zt-mask-in {
  from {
    opacity: 0;
  }
}

.arco-modal,
.arco-drawer {
  transform-origin: 50% 100%;
  animation: zt-dlg-in var(--zt-dur-dialog) var(--zt-ease-spring);
}

.arco-modal-mask,
.arco-drawer-mask {
  background-color: rgba(2, 6, 23, 0.45);
  backdrop-filter: blur(2px);
  animation: zt-mask-in var(--zt-dur-dialog) ease;
}

/* 退出：140ms 反向无回弹（压 Arco 自带 leave 时长，面板收缩淡出） */
.fade-modal-leave-active,
.fade-drawer-leave-active {
  transition-duration: var(--zt-dur-off) !important;
  transition-timing-function: ease !important;
}

.fade-modal-leave-active .arco-modal {
  transition: transform var(--zt-dur-off) ease, opacity var(--zt-dur-off) ease;
  transform: scale(0.88);
  opacity: 0;
}

/* 下拉/气泡小面板：自触发侧生长（动画只挂在内容层，不碰 Arco 定位用的 transform） */
.arco-dropdown,
.arco-popover {
  animation: zt-dlg-in var(--zt-dur-fast) var(--zt-ease-spring);
}

/* Message 顶部滑入淡入（spec §3） */
.fade-message-enter-active {
  transition: opacity var(--zt-dur-fast) var(--zt-ease-out),
    transform var(--zt-dur-fast) var(--zt-ease-out);
}

.fade-message-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

.fade-message-leave-active {
  transition: opacity var(--zt-dur-off) ease;
}

.fade-message-leave-to {
  opacity: 0;
}

/* ================= 宿主弹窗页整窗入场（spec §3，一次） ================= */
@keyframes zt-host-in {
  from {
    opacity: 0;
    transform: scale(0.97) translateY(6px);
  }
}

#app {
  transform-origin: 50% 100%;
  animation: zt-host-in var(--zt-dur-dialog) var(--zt-ease-spring);
}
```

- [ ] **Step 2: reduced-motion 块追加 `#app`**

把 `@media (prefers-reduced-motion: reduce)` 内的选择器列表：

```css
  .zt-page-enter-from,
  .zt-list-enter-from,
  .zt-list-leave-to,
  .task-card-item:hover {
    transform: none;
  }
```

改为（仅追加一行 `#app`）：

```css
  .zt-page-enter-from,
  .zt-list-enter-from,
  .zt-list-leave-to,
  .task-card-item:hover,
  #app {
    transform: none;
  }
```

- [ ] **Step 3: 编译校验 + 产物断言**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p2 --emptyOutDir && grep -o "zt-dlg-in\|zt-host-in\|zt-mask-in" /tmp/zt-dist-p2/assets/*.css | sort | uniq -c`
Expected: 构建成功；三个 keyframes 名各出现 ≥2 次（定义 + 引用）。

- [ ] **Step 4: 提交**

```bash
git add web/src/styles.css
git commit -m "feat(ui): 页内弹层 dg-a 源点生长 + 宿主整窗入场 + Message 顶部滑入"
```

---

### Task 3: QuickAdd 全胶囊聚焦 + Progress 等宽数字

**Files:**
- Modify: `web/src/styles.css:226-241`（`.quick-add-box` 块替换）
- Modify: `web/src/views/Progress.vue:186-191`（`.pct-label` 块）

**Interfaces:**
- Consumes: Task 1 的形状两档令牌。

- [ ] **Step 1: 替换 `.quick-add-box` 块**

把 `styles.css:226-241`（`.quick-add-box { ... }` 与其后的 `.quick-add-box .arco-input-wrapper { ... }`）替换为：

```css
.quick-add-box {
  width: min(640px, 100%);
  border-radius: var(--zt-radius-pill);
  padding: 4px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  transition: border-color var(--zt-dur-fast) ease,
    box-shadow var(--zt-dur-fast) ease;
}

/* 聚焦 teal 描边点亮（spec §3 快速添加） */
.quick-add-box:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45),
    0 0 0 1.5px var(--color-primary-glow);
}

body.zt-shape-crisp .quick-add-box {
  border-radius: var(--zt-radius-md);
}

.quick-add-box .arco-input-wrapper {
  border: none !important;
  background: transparent !important;
  font-size: 18px;
  font-weight: 600;
  padding: 12px 16px;
}
```

- [ ] **Step 2: Progress 数字等宽**

`Progress.vue` 的 `.pct-label` 块（`:186`）追加一行属性：

```css
.pct-label {
  font-size: 22px;
  font-weight: 700;
  min-width: 56px;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--primary-6));
}
```

- [ ] **Step 3: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p2 --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 4: 提交**

```bash
git add web/src/styles.css web/src/views/Progress.vue
git commit -m "feat(ui): 快速录入全胶囊化与聚焦点亮，进度百分比等宽数字"
```

---

### Task 4: 硬编码圆角令牌化清扫（History / Settings / 组件）

**Files:**
- Modify: `web/src/views/History.vue`（scoped 三处 `border-radius: 8px`）
- Modify: `web/src/views/Settings.vue:1016`（`.nav-main` 圆角）
- Modify: `web/src/components/NumberSpinner.vue` / `TimeSpinner.vue` / `JobEditor.vue`（仅当存在容器级硬编码圆角时）
- Verify: `web/src/views/TaskForm.vue`、`Reminder.vue`、`TaskAction.vue`、`Periodic.vue`、`SetupWizard.vue`、`Home.vue` 预期**零代码改动**（全局接线层覆盖）

**Interfaces:**
- Consumes: Task 1 的 `--zt-radius-card/md` 两档令牌。

- [ ] **Step 1: History 三处令牌化**

`History.vue` scoped 样式中（替换后行号约 650/734/790）：
- `.tl-row { ... border-radius: 8px; ... }` → `border-radius: var(--zt-radius-md);`
- `.detail-col { ... border-radius: 8px; ... }` → `border-radius: var(--zt-radius-md);`
- `.date-item { ... border-radius: 8px; ... }` → `border-radius: var(--zt-radius-md);`

- [ ] **Step 2: Settings 导航卡令牌化**

`Settings.vue` scoped 的 `.nav-main`（约 `:1016`）：`border-radius: 8px;` → `border-radius: var(--zt-radius-card);`

- [ ] **Step 3: 组件清扫（判断性）**

Run: `grep -rn "border-radius:" web/src/components/ web/src/views/TaskList.vue | grep -v "999px\|50%\|var("`
对每一处：**容器面板**（spinner 外框、卡片、输入行）→ 就近换 `var(--zt-radius-md)`；**功能性小元素**（圆点、指示条、checkbox 圆框）→ 保留原值。逐处记录改/不改的理由到报告。

- [ ] **Step 4: 零改动视图确认**

Run: `git diff --stat -- web/src/views/TaskForm.vue web/src/views/Reminder.vue web/src/views/TaskAction.vue web/src/views/Periodic.vue web/src/views/SetupWizard.vue web/src/views/Home.vue`
Expected: 无输出（这些视图由全局层覆盖，不加 scoped 覆盖）。

- [ ] **Step 5: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-p2 --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 6: 提交**

```bash
git add web/src/views/History.vue web/src/views/Settings.vue web/src/components/
git commit -m "feat(ui): History/Settings/组件硬编码圆角接入形状两档令牌"
```

（若 Step 3 判定组件零改动，则从 `git add` 中去掉 `web/src/components/`。）

---

### Task 5: dist 成对重建 + 全量收尾验证

**Files:**
- Rebuild: `web/dist/`（`npm run build` 产出）
- 无源码改动；只构建、验证、提交。

**Interfaces:**
- Consumes: Task 1-4 的全部 src 改动。

- [ ] **Step 1: 重建 dist**

Run: `cd web && npm run build`
Expected: 构建成功，产出新 hash 资产。

- [ ] **Step 2: 成对检查**

Run: `git status --short -- web/dist`
Expected: 旧 hash 资产删除（`D`）与新 hash 资产新增（`??`）**成对**出现，`index.html` 引用更新。工作区既有的 dist 改动（上一轮用户本地构建产物）被本次重建覆盖为同一来源的最新产物，属预期。

- [ ] **Step 3: Python 全量回归**

Run: `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ -q`
Expected: 112 项全部 PASS。

- [ ] **Step 4: 提交 dist**

```bash
git add web/dist
git commit -m "feat(ui): 重建 web/dist——圆润丝滑全局铺开构建产物"
```

- [ ] **Step 5: 手测清单（交给用户）**

启动应用（托盘 → 各窗口），重点验证：
1. **bug 修复主链**：设置 → 系统切「形状风格→利落」：卡片圆角 16→8、按钮胶囊→小圆角、输入框 8→4 立即变化；切回「圆润」复原。
2. 「界面动效→关」：hover 上浮、页面过渡、弹层生长、整窗入场全部消失（即时跳变），载入 spinner 仍转动；`prefers-reduced-motion` 系统设置下为 140ms 纯淡入。
3. 各页面（任务列表/新建任务/快速录入/更新进度/提醒/选择操作/周期任务/历史/设置/向导）卡片圆润、投影柔和、按钮胶囊、聚焦 teal 亮环。
4. TaskForm「添加二级分类」弹层、Periodic「删除确认」弹层：源点生长入场、140ms 收缩退出、遮罩带模糊。
5. 保存设置后重开应用，形状/动效选择持久生效。

---

## 零改动视图说明（评审用）

TaskForm / Reminder / TaskAction / Periodic / SetupWizard / Home 全部由 `styles.css` 全局层覆盖（卡片/按钮/输入/弹层/表格接线 + Arco 变量翻转），与 P1 中 Home 零改动的机制相同。Task 4 Step 4 有显式验证步骤。

## Self-Review 记录

- **Spec 覆盖**：§6 修订版接线层（Task 1）✓ §4 dg-a/leave/宿主入场（Task 2）✓ §3 快速添加/Message/表格行/聚焦环（Task 1/2/3）✓ §7 P2 视图 + dist（Task 1-5 全局层 + 零改动验证）✓ §7 P3 视图（Task 4）✓ 验收 §8 的 1/2/6 由 Task 5 覆盖、3/4/5 归手测清单。
- **占位符扫描**：无 TBD/TODO；所有 CSS 步骤含完整代码。
- **机制核验**：`.arco-modal` 等在构建产物中无 transform 定位冲突（定位在 `.arco-modal-container`/trigger 外层）；`.fade-modal-leave-*` 类名取自构建产物 grep（2026-09-11）；`arco-loading-circle` keyframe 与 `.arco-icon-loading`/`.arco-icon-spin` 类名取自构建产物 grep。
- **已知取舍**：dg-a 的「按触发元素位置设 transform-origin」简化为固定源点偏下（50% 100%）——事件委托注入 origin 属增强，固定源点已满足「源点生长」观感且零 JS；spec §4 的 origin 注入行已在修订中隐含放宽。留待用户手测反馈后再决定是否加 JS 注入。
