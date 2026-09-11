# ZenTray GSAP 动效升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec 与交互原型（`.superpowers/prototypes/gsap-motion.html`）落地 GSAP 编排级动效：页面转场、Flip 筛选、主题/形状色彩流动、弹层内容 stagger、关键时刻编排，双轨制与既有降级语义完全兼容。

**Architecture:** 双轨制——CSS 微交互层原样保留；新增 `web/src/motion/` 作 GSAP 单一事实源（插件注册、曲线、时长、降级查询）。四个消费面：App.vue 页面转场 JS 钩子、theme.js 令牌补间（@property 注册）、TaskList Flip 筛选、v-stagger 指令 + 关键时刻。

**Tech Stack:** 新增 npm 依赖仅 `gsap`（^3.13，全插件免费）。Python 侧零改动。

**Spec:** `docs/superpowers/specs/2026-09-11-zentray-gsap-motion-design.md`（数值以 spec §2 为准）

## Global Constraints

- 工作区存在**与本计划无关的未提交改动**（packaging/、scripts/、tests/、zentray/）。提交一律显式 `git add <本任务文件>`，**严禁 `git add -A` / `git add .`**。
- 提交信息：`feat:` / `fix:` 前缀 + 中文描述。
- **dist 只在 Task 6 重建**。Task 1-5 编译校验输出临时目录：`cd web && npx vite build --outDir /tmp/zt-dist-gsap --emptyOutDir`。
- Python 回归命令（仓库根）：`QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ -q`（当前 112 项全绿；本计划零 Python 改动，Task 6 全量确认）。
- **降级语义（spec §5，铁律）**：`body.zt-motion-off` → GSAP 侧不创建补间（duration 0.001 + 提前 return）；`prefers-reduced-motion` → 140ms 纯淡入、无位移缩放、无 Flip；关档优先于系统档。
- GSAP Vue 规范（gsap-frameworks skill）：选择器必须带 scope（容器 ref 或 `:scope >`）；组件内动画在 `onUnmounted` 清理（`ctx.revert()` 或 kill）；插件只在 `motion/index.js` 注册一次。
- minified CSS 断言用 `grep -o ... | wc -l`（单行文件 `grep -c` 恒 ≤1）。
- Flip 与 TransitionGroup 共存约束：筛选用 **class 隐藏**（`.flip-gone{display:none}`）而非 v-if 移除节点——避免 TransitionGroup 把过滤当成增删触发 CSS 动画与 Flip 打架。

---

### Task 1: 基座 — gsap 依赖 + motion/index.js

**Files:**
- Modify: `web/package.json`（+gsap 依赖）
- Create: `web/src/motion/index.js`

**Interfaces:**
- Produces（后续所有任务消费）：`EASE.{spring,out}`、`DUR` 常量、`dur(v)`（关档→0.001）、`motionOff()`、`isReduced()`；gsap/Flip/SplitText/CustomEase 已注册。

- [ ] **Step 1: 安装依赖**

Run: `cd web && npm install gsap`
Expected: package.json dependencies 出现 `"gsap": "^3.13.x"`，node_modules/gsap 就位。

- [ ] **Step 2: 创建 motion/index.js（逐字）**

```javascript
/**
 * GSAP 动效基座（spec §2 单一事实源）。
 * 插件只在这里注册一次；曲线与 CSS 侧 --zt-ease-* 同参数。
 */
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { SplitText } from 'gsap/SplitText'
import { CustomEase } from 'gsap/CustomEase'

gsap.registerPlugin(Flip, SplitText, CustomEase)

let spring = 'back.out(1.6)'
let out = 'power2.out'
try {
  CustomEase.create('zt-spring', 'cubic-bezier(0.34,1.56,0.64,1)')
  CustomEase.create('zt-out', 'cubic-bezier(0.22,1,0.36,1)')
  spring = 'zt-spring'
  out = 'zt-out'
} catch (e) {
  /* ponytail: CustomEase 解析失败的内置曲线回退，手感近似 */
}

export { gsap, Flip, SplitText }

export const EASE = { spring, out }

/** 时长（秒）——spec §2；命名与 CSS 令牌一一对应 */
export const DUR = {
  leave: 0.12,
  enter: 0.26,
  theme: 0.45,
  shape: 0.35,
  flip: 0.4,
  staggerCards: 0.04,
  staggerModal: 0.03,
  staggerChars: 0.035,
  reduce: 0.14,
}

/** 动效=关：所有补间时长归零（调用方仍应尽早 return，此为兜底） */
export function motionOff() {
  return typeof document !== 'undefined' && document.body.classList.contains('zt-motion-off')
}

/** 系统减动效：降级为 140ms 纯淡入 */
export function isReduced() {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch (e) {
    return false
  }
}

/** 关档把时长压为零；正常档原样返回 */
export function dur(v) {
  return motionOff() ? 0.001 : v
}
```

- [ ] **Step 3: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-gsap --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 4: 提交**

```bash
git add web/package.json web/package-lock.json web/src/motion/index.js
git commit -m "feat(ui): 引入 gsap 依赖与 motion 基座——插件注册/曲线/时长/降级查询单一事实源"
```

---

### Task 2: 主题/形状令牌流动 — @property 注册 + theme.js 补间

**Files:**
- Modify: `web/src/styles.css`（文件头部新增 @property 注册块）
- Modify: `web/src/theme.js`（applyTheme / applyAppearance 补间）

**Interfaces:**
- Consumes: Task 1 的 `gsap`、`EASE`、`DUR`、`dur`、`motionOff`、`isReduced`。
- Produces: 切主题 450ms 色彩流动、切形状 350ms 圆角变形；关档瞬时、系统减动效 140ms。

- [ ] **Step 1: styles.css 顶部（`:root` 块之前）新增 @property 注册块（逐字）**

```css
/* ================= 令牌可补间注册（GSAP 主题/形状流动，spec §3.4） =================
   只注册跨主题会变值的令牌（success/warning/danger 四主题同值，不注册）。 */
@property --color-bg-base { syntax: '<color>'; inherits: true; initial-value: #0f172a; }
@property --color-surface { syntax: '<color>'; inherits: true; initial-value: #1e293b; }
@property --color-surface-hover { syntax: '<color>'; inherits: true; initial-value: rgba(255, 255, 255, 0.04); }
@property --color-border { syntax: '<color>'; inherits: true; initial-value: #334155; }
@property --color-primary { syntax: '<color>'; inherits: true; initial-value: #0d9488; }
@property --color-primary-hover { syntax: '<color>'; inherits: true; initial-value: #14b8a6; }
@property --color-primary-glow { syntax: '<color>'; inherits: true; initial-value: rgba(20, 184, 166, 0.25); }
@property --color-text-primary { syntax: '<color>'; inherits: true; initial-value: #f8fafc; }
@property --color-text-muted { syntax: '<color>'; inherits: true; initial-value: #94a3b8; }
@property --color-text-subdued { syntax: '<color>'; inherits: true; initial-value: #64748b; }
@property --zt-radius-card { syntax: '<length>'; inherits: true; initial-value: 16px; }
@property --zt-radius-md { syntax: '<length>'; inherits: true; initial-value: 12px; }
```

- [ ] **Step 2: theme.js 补间**

在文件头部 import 区追加：

```javascript
import { gsap, EASE, DUR, dur, motionOff, isReduced } from './motion'
```

在 `applyTheme` 上方新增辅助函数，并改造两个应用函数（`applyTheme` 的 class 翻转逻辑整体包进回调，返回值语义不变）：

```javascript
/** 跨主题流动的令牌（与 styles.css @property 注册块一一对应） */
const FLOW_COLOR_VARS = [
  '--color-bg-base', '--color-surface', '--color-surface-hover', '--color-border',
  '--color-primary', '--color-primary-hover', '--color-primary-glow',
  '--color-text-primary', '--color-text-muted', '--color-text-subdued',
]
const FLOW_SHAPE_VARS = ['--zt-radius-card', '--zt-radius-md']

/**
 * class 翻转补间：先取旧值 → 翻转 → 取新值 → fromTo 内联覆盖，结束清除内联。
 * 关档瞬时；系统减动效 140ms 无缓动。中断时 overwrite:auto 从当前值接管。
 */
function tweenClassFlip(root, flip, vars, seconds, ease) {
  const before = vars.map((v) => getComputedStyle(root).getPropertyValue(v).trim())
  flip()
  if (motionOff()) return
  const reduced = isReduced()
  const from = {}
  const to = {}
  vars.forEach((v, i) => {
    const after = getComputedStyle(root).getPropertyValue(v).trim()
    from[v] = before[i]
    to[v] = after
  })
  gsap.fromTo(root, from, {
    ...to,
    duration: reduced ? DUR.reduce : dur(seconds),
    ease: reduced ? 'none' : ease,
    overwrite: 'auto',
    onComplete() {
      vars.forEach((v) => root.style.removeProperty(v))
    },
  })
}
```

`applyTheme` 中「清除旧主题 class」到「return effective」的原有主体改为：

```javascript
  const effective = resolveEffectiveTheme(mode)
  const root = document.body
  tweenClassFlip(
    root,
    () => {
      root.classList.remove('theme-light', 'theme-dark', 'theme-slate-dark', 'theme-oled-dark')
      if (effective === 'light') {
        root.removeAttribute('arco-theme')
        root.classList.add('theme-light')
      } else if (effective === 'oled-dark') {
        root.setAttribute('arco-theme', 'dark')
        root.classList.add('theme-dark', 'theme-oled-dark')
      } else {
        root.setAttribute('arco-theme', 'dark')
        root.classList.add('theme-dark', 'theme-slate-dark')
      }
      root.dataset.themeMode = mode || 'system'
      root.dataset.themeEffective = effective
    },
    FLOW_COLOR_VARS,
    DUR.theme,
    EASE.out,
  )
  return effective
```

（注：`arco-theme` 属性切换是瞬时快照——Arco 内部变量不注册补间，属已知取舍，见计划尾注。）

`applyAppearance` 的两行 class toggle 改为：

```javascript
  tweenClassFlip(
    root,
    () => {
      root.classList.toggle('zt-motion-off', motion === 'off')
      root.classList.toggle('zt-shape-crisp', shape === 'crisp')
    },
    FLOW_SHAPE_VARS,
    DUR.shape,
    EASE.spring,
  )
  root.dataset.ztMotion = motion
  root.dataset.ztShape = shape
```

（动效开关本身不补间——形状档圆角变形流动。）

- [ ] **Step 3: 编译校验 + 产物断言**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-gsap --emptyOutDir && grep -o "@property" /tmp/zt-dist-gsap/assets/*.css | wc -l`
Expected: 构建成功；`@property` ≥12 次（12 个注册声明）。

- [ ] **Step 4: 提交**

```bash
git add web/src/styles.css web/src/theme.js
git commit -m "feat(ui): 主题/形状切换令牌流动——@property 注册 + GSAP 补间，关档瞬时减动效纯淡入"
```

---

### Task 3: 页面转场 — App.vue JS 钩子 + 退役 CSS 过渡

**Files:**
- Modify: `web/src/App.vue`（Transition 改 JS 钩子）
- Modify: `web/src/styles.css`（退役 zt-page 规则、`#app` host-in 块及其 media 条目）

**Interfaces:**
- Consumes: Task 1 的 `gsap`、`SplitText`、`EASE`、`DUR`、`motionOff`、`isReduced`。
- Produces: 退场 120ms 子块下沉；入场 260ms 标题逐字 + 子块 stagger；`zentray:reopen` 复用入场编排。

- [ ] **Step 1: App.vue 模板与脚本**

模板第 4 行 `<Transition name="zt-page" mode="out-in">` 改为：

```html
      <Transition :css="false" mode="out-in" @enter="onPageEnter" @leave="onPageLeave">
```

script setup 追加（import 区 + 函数体）：

```javascript
import { gsap, SplitText, EASE, DUR, motionOff, isReduced } from './motion'

// ---- 页面转场（spec §3.1）：CSS 类退役，GSAP timeline 接管 ----
// 退场：根直接子块依次下沉淡出；入场：标题逐字浮升 + 其余子块弹簧 stagger。
function onPageLeave(el, done) {
  if (motionOff()) {
    done()
    return
  }
  if (isReduced()) {
    gsap.to(el, { autoAlpha: 0, duration: DUR.reduce, ease: 'none', onComplete: done })
    return
  }
  gsap.to(el.querySelectorAll(':scope > *'), {
    y: 10,
    autoAlpha: 0,
    duration: DUR.leave,
    stagger: 0.015,
    ease: EASE.out,
    onComplete: done,
  })
}

function onPageEnter(el, done) {
  gsap.set(el, { autoAlpha: 1 })
  if (motionOff()) {
    done()
    return
  }
  if (isReduced()) {
    gsap.from(el, { autoAlpha: 0, duration: DUR.reduce, ease: 'none', onComplete: done })
    return
  }
  const blocks = el.querySelectorAll(':scope > *:not(.page-header)')
  const title = el.querySelector('.page-header h2')
  const tl = gsap.timeline({ onComplete: done })
  let split = null
  try {
    if (title) split = new SplitText(title, { type: 'chars' })
  } catch (e) {
    /* 标题整体动画回退 */
  }
  if (split && split.chars && split.chars.length) {
    tl.from(
      split.chars,
      { yPercent: 110, autoAlpha: 0, duration: DUR.enter, stagger: DUR.staggerChars, ease: EASE.spring },
      0,
    )
  } else if (title) {
    tl.from(title, { y: 14, autoAlpha: 0, duration: 0.2, ease: EASE.spring }, 0)
  }
  if (blocks.length) {
    tl.from(
      blocks,
      { y: 26, autoAlpha: 0, duration: DUR.enter, stagger: DUR.staggerCards, ease: EASE.spring, clearProps: 'all' },
      0.02,
    )
  }
  if (split) tl.add(() => split.revert())
}
```

- [ ] **Step 2: styles.css 退役清理**

删除（按内容定位，非行号）：
1. `.zt-page-enter-active` / `.zt-page-enter-from` / `.zt-page-leave-active` / `.zt-page-leave-to` 四条规则（页面过渡 CSS）。
2. `#app { transform-origin: 50% 100%; animation: zt-host-in ... }` 规则与 `@keyframes zt-host-in` 定义。
3. `@media (prefers-reduced-motion: reduce)` 两处块的选择器名单中，`.zt-page-enter-from` / `.zt-page-leave-active` / `#app` 条目删除（`.zt-list-*`、`.task-card-item:hover`、`.fade-message-enter-from`、`.arco-btn-primary:hover` 保留）；文件末尾 media 块内 `@keyframes zt-host-in` 重定义删除（`zt-dlg-in` 保留）。
4. 若 `--zt-dur-page` 因此零消费（全文件 grep 确认），其 `:root` 定义行一并删除。

- [ ] **Step 3: 编译校验 + 产物断言**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-gsap --emptyOutDir && grep -o "zt-page\|zt-host-in" /tmp/zt-dist-gsap/assets/*.css | wc -l`
Expected: 构建成功；计数 0（CSS 侧完全退役；JS 侧逻辑在 bundle，不在此断言）。

- [ ] **Step 4: 提交**

```bash
git add web/src/App.vue web/src/styles.css
git commit -m "feat(ui): 页面转场改 GSAP 编排——标题逐字与子块 stagger，退役 zt-page CSS 过渡"
```

---

### Task 4: TaskList 筛选 chips + Flip 布局流动

**Files:**
- Modify: `web/src/views/TaskList.vue`

**Interfaces:**
- Consumes: Task 1 的 `Flip`、`gsap`、`EASE`、`DUR`、`dur`、`motionOff`、`isReduced`。
- Produces: 原型 §3.2 场景——分类筛选 chip 行（全部分类 + 计数）+ Flip.from 流动；reload 数据刷新同样 Flip。

- [ ] **Step 1: 模板 — 活跃任务卡内 TransitionGroup 之前插入 chip 行**

`<a-card title="活跃任务">` 内、`<a-spin>` 之前：

```html
        <div v-if="filterChips.length > 1" class="filter-row" role="group" aria-label="分类筛选">
          <button
            v-for="c in filterChips"
            :key="c.key"
            class="fchip"
            type="button"
            :aria-pressed="String(filter === c.key)"
            @click="setFilter(c.key)"
          >
            {{ c.label }} · {{ c.count }}
          </button>
        </div>
```

TransitionGroup 的 `v-for="item in tasks"` 改为 `v-for="item in tasks"`（**不变**——过滤用 class 隐藏，见 Step 2），卡片 div 的 class 绑定追加隐藏类：

```html
              :class="{ active: item.id === selectedId, 'flip-gone': !matchesFilter(item) }"
```

- [ ] **Step 2: 脚本 — 筛选状态 + Flip**

script setup 追加：

```javascript
import { nextTick } from 'vue'
import { gsap, Flip, EASE, DUR, dur, motionOff, isReduced } from '@/motion'

// ---- 分类筛选 + Flip 布局流动（spec §3.2，原型场景 2） ----
// 过滤用 class 隐藏而非 v-if：TransitionGroup 把节点移除当增删动画，会与 Flip 打架。
const filter = ref('all')
const listRef = ref(null)

const filterChips = computed(() => {
  const counts = new Map()
  for (const t of tasks.value) {
    const k = t.category || '未分类'
    counts.set(k, (counts.get(k) || 0) + 1)
  }
  const chips = [{ key: 'all', label: '全部', count: tasks.value.length }]
  for (const [k, n] of counts) chips.push({ key: k, label: k, count: n })
  return chips.slice(0, 6)
})

function matchesFilter(item) {
  return filter.value === 'all' || (item.category || '未分类') === filter.value
}

function setFilter(k) {
  if (filter.value === k) return
  runFlip(() => {
    filter.value = k
  })
}

/** DOM 集合变化前后捕获/回放：幸存卡片流动，离场收缩淡出、回归弹性放大 */
async function runFlip(mutate) {
  const root = listRef.value?.$el ?? listRef.value // TransitionGroup 的 ref 是组件实例，$el 才是 tag 渲染的 div
  if (!root || motionOff() || isReduced()) {
    await mutate()
    return
  }
  const cards = root.querySelectorAll('.task-card-item')
  const state = Flip.getState(cards)
  await mutate()
  await nextTick()
  Flip.from(state, {
    duration: DUR.flip,
    ease: EASE.spring,
    stagger: 0.02,
    absolute: true,
    onEnter: (els) => gsap.fromTo(els, { opacity: 0, scale: 0.88 }, { opacity: 1, scale: 1, duration: DUR.enter, ease: EASE.spring, clearProps: 'all' }),
    onLeave: (els) => gsap.to(els, { opacity: 0, scale: 0.88, duration: 0.2, ease: EASE.out }),
  })
}
```

TransitionGroup 标签加 ref（`<TransitionGroup ... ref="listRef">`，tag="div" 保留）。

`reload()` 的 `tasks.value = await listTasks()` 一行改为数据刷新也走 Flip：

```javascript
    const fresh = await listTasks()
    runFlip(() => {
      tasks.value = fresh
    })
```

- [ ] **Step 3: scoped 样式 — chip 行（原型视觉）**

scoped style 追加：

```css
.filter-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.filter-row .fchip {
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  color: var(--color-text-muted);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-pill);
  padding: 5px 14px;
  transition: color 0.2s ease, background-color 0.2s ease, border-color 0.2s ease;
}
.filter-row .fchip:hover {
  color: var(--color-text-primary);
}
.filter-row .fchip[aria-pressed='true'] {
  background: var(--color-primary-glow);
  color: var(--color-primary-hover);
  border-color: var(--color-primary);
}
.flip-gone {
  display: none;
}
```

- [ ] **Step 4: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-gsap --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 5: 提交**

```bash
git add web/src/views/TaskList.vue
git commit -m "feat(ui): 任务列表分类筛选 chips 与 Flip 布局流动，数据刷新平滑重排"
```

---

### Task 5: 弹层内容 stagger + 关键时刻编排

**Files:**
- Create: `web/src/directives/stagger.js`
- Modify: `web/src/main.js`（注册指令）
- Modify: `web/src/views/TaskForm.vue`（二级分类 modal 内容根挂 v-stagger）
- Modify: `web/src/views/Progress.vue`（100% 庆祝）
- Modify: `web/src/views/TaskList.vue`（完成/废弃前庆祝编排）
- Modify: `web/src/views/QuickAdd.vue`（聚焦弹性绽放）

**Interfaces:**
- Consumes: Task 1 全部导出。
- Produces: `v-stagger` 全局指令；完成时刻（对勾 pop + 涟漪 + 相邻让位）；快速录入聚焦弹性。

- [ ] **Step 1: v-stagger 指令（逐字）**

```javascript
/**
 * v-stagger：弹层/区块内容依次浮升（spec §3.3，原型场景 4）。
 * 挂在内容根节点上，其直接子块 stagger 入场；关档/减动效不动作。
 */
import { gsap, EASE, DUR, motionOff, isReduced } from '../motion'

export const vStagger = {
  mounted(el) {
    if (motionOff() || isReduced()) return
    const kids = el.querySelectorAll(':scope > *')
    if (!kids.length) return
    gsap.from(kids, {
      y: 14,
      autoAlpha: 0,
      duration: DUR.enter,
      stagger: DUR.staggerModal,
      ease: EASE.spring,
      clearProps: 'all',
      delay: 0.05,
    })
  },
}
```

main.js：`import { vStagger } from './directives/stagger'`，`app.use(router)` 之前加 `app.directive('stagger', vStagger)`。

TaskForm.vue 二级分类 `a-modal` 的默认插槽内容根元素加 `v-stagger`（插槽内第一个包裹 div）。

- [ ] **Step 2: Progress.vue 100% 庆祝**

`onSave()` 成功分支（`Message.success('已保存')` 处）与「完成」路径（markDone 成功后）插入庆祝；`onSave` 原为保存后立即 `handleExit`，改为 100% 时先庆祝再延迟退出：

```javascript
import { gsap, EASE, DUR, dur, motionOff } from '@/motion'

/** 100% 达成庆祝（spec §3.5，原型场景 5）：百分比数字弹性绽放 + 页面轻微脉冲 */
function celebrate() {
  if (motionOff()) return
  const pct = document.querySelector('.pct-label')
  if (pct) {
    gsap.fromTo(pct, { scale: 1 }, { scale: 1.18, duration: 0.28, ease: EASE.spring, yoyo: true, repeat: 1, transformOrigin: '50% 50%' })
  }
  const body = document.querySelector('.progress-body')
  if (body) {
    gsap.fromTo(body, { scale: 1 }, { scale: 1.012, duration: 0.22, ease: EASE.spring, yoyo: true, repeat: 1, transformOrigin: '50% 100%' })
  }
}
```

onSave 成功分支改为：

```javascript
    Message.success('已保存')
    if (Number(percent.value) >= 100) {
      celebrate()
      setTimeout(() => handleExit({ action: 'progress', percent: snap10(percent.value) }), DUR.theme * 1000)
    } else {
      handleExit({ action: 'progress', percent: snap10(percent.value) })
    }
```

（markDone 快捷路径同理：成功后 celebrate() + 600ms 延迟退出；实施时按该函数现有结构接入，语义同上。）

- [ ] **Step 3: TaskList 完成前庆祝**

`onDone()` / `onAbandon()` 的 onOk 成功分支：`closeHost(...)` 之前对当前卡片播放编排，延迟 ~500ms 关窗：

```javascript
import { gsap, EASE, motionOff } from '@/motion'

/** 卡片离场庆祝：卡片弹性收缩浮起，邻居轻微让位（spec §3.5） */
function celebrateCard(itemId) {
  if (motionOff()) return false
  const root = listRef.value?.$el ?? listRef.value // 同 Task 4：组件实例 → $el
  if (!root) return false
  const cards = Array.from(root.querySelectorAll('.task-card-item'))
  const idx = cards.findIndex((c) => c.dataset.taskId === String(itemId))
  const target = idx >= 0 ? cards[idx] : null
  if (target) {
    gsap.to(target, { scale: 1.02, y: -3, duration: 0.2, ease: EASE.spring })
    gsap.to(target, { autoAlpha: 0, scale: 0.88, y: -8, duration: 0.26, ease: EASE.out, delay: 0.18 })
  }
  cards.forEach((c, j) => {
    if (!target || c === target) return
    const dir = j < idx ? -1 : 1
    gsap.fromTo(c, { y: dir * 2 }, { y: 0, duration: 0.5, ease: EASE.spring })
  })
  return true
}
```

（配套：卡片 div 加 `:data-task-id="item.id"`；onDone 成功后 `if (celebrateCard(id)) setTimeout(() => closeHost(...), 520)` else 直接 closeHost——onAbandon 的 Modal onOk 同构。）

- [ ] **Step 4: QuickAdd 聚焦绽放**

QuickAdd.vue script 追加（`.quick-add-box` 已有 ref 或加一个）：

```javascript
import { gsap, EASE, dur, motionOff } from '@/motion'

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
```

（模板 `.quick-add-box` 加 `ref="boxRef"`；聚焦 teal 亮环仍由 CSS `:focus-within` 负责，GSAP 只加弹性 scale。）

- [ ] **Step 5: 编译校验**

Run: `cd web && npx vite build --outDir /tmp/zt-dist-gsap --emptyOutDir`
Expected: 构建成功。

- [ ] **Step 6: 提交**

```bash
git add web/src/directives/stagger.js web/src/main.js web/src/views/TaskForm.vue web/src/views/Progress.vue web/src/views/TaskList.vue web/src/views/QuickAdd.vue
git commit -m "feat(ui): 弹层内容 stagger 指令与关键时刻编排——完成庆祝/进度绽放/快速录入聚焦弹性"
```

---

### Task 6: dist 成对重建 + 全量收尾验证

**Files:**
- Rebuild: `web/dist/`（`npm run build` 产出）；无源码改动。

- [ ] **Step 1: 重建 dist**

Run: `cd web && npm run build`
Expected: 构建成功，产出新 hash 资产。

- [ ] **Step 2: 成对检查**

Run: `git status --short -- web/dist`
Expected: 旧 hash 删除（D）与新 hash（??）成对、index.html 引用更新。

- [ ] **Step 3: Python 全量回归**

Run: `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ -q`（仓库根）
Expected: 112 项全部 PASS。

- [ ] **Step 4: 提交 dist**

```bash
git add web/dist
git commit -m "feat(ui): 重建 web/dist——GSAP 编排级动效构建产物"
```

- [ ] **Step 5: 手测清单（交给用户）**

1. 页面切换（任务↔历史↔设置等）：旧页下沉 → 标题逐字 + 卡片弹簧入场；关档瞬时。
2. 任务列表点分类 chip：卡片流动重排；刷新数据同样平滑。
3. 设置切主题：全界面色彩流动 450ms；切形状：圆角变形 350ms；快速连切不跳变。
4. 新建任务 → 添加二级分类弹层：内容依次浮升。
5. 进度拉到 100 保存：百分比绽放 + 延迟关窗；任务列表点完成：卡片庆祝后关窗。
6. 快速录入窗口：点击输入框弹性放大 + teal 亮环，失焦复原。
7. 动效=关：以上全部瞬时；系统减动效（DevTools 模拟）：纯淡入。
8. 页头拖拽、`zentray://` 桥接不退化。

---

## 已知取舍（评审勿报）

- **Arco 内部变量不补间**：`arco-theme` 属性切换瞬时生效（Arco 自有变量几十个不注册 @property），主题切换时 Arco 控件内部色快照式跳变、我方令牌面流动。观感问题留手测反馈，如刺眼再扩注册清单（另立任务）。
- **庆祝延迟关窗 ~500ms**：完成/100% 保存先播编排再 closeHost，属设计意图（spec §3.5），非遗漏。
- **Flip 只接 TaskList**：其他视图出现筛选需求时复用 `runFlip` 封装（spec §3.2 已声明）。
- **Modal.confirm（JS API 弹窗）不挂 stagger**：指令只服务模板插槽内容；此类弹窗仍有 CSS dg-a 骨架。

## Self-Review 记录

- **Spec 覆盖**：§2 令牌（Task 1）✓ §3.1 转场（Task 3）✓ §3.2 Flip（Task 4）✓ §3.3 stagger（Task 5）✓ §3.4 令牌流动（Task 2）✓ §3.5 时刻（Task 5）✓ §5 降级矩阵（Task 1 基座 + 各任务分支）✓ §6 分期对应 Task 1-2=M1、Task 3=M2、Task 4-5=M3、Task 6=收尾 ✓ §7 验收 1/2 由 Task 6 静态覆盖、3-6 归手测清单 ✓
- **占位符扫描**：无 TBD/TODO；关键代码块完整给出（Progress markDone 路径与 TaskForm 插槽根按现场结构接入，语义已写死）。
- **类型一致**：`runFlip(mutate)` 返回 Promise；`celebrateCard` 返回 boolean 供调用方决定是否延迟关窗；`tweenClassFlip` 不改 applyTheme/applyAppearance 返回值语义。
- **机制核验**：`:css="false"` 时 Vue 不加过渡类，JS 钩子独占；TransitionGroup 与 Flip 经 class 隐藏隔离；SplitText 对中文按 chars 切分（原型已验证）；@property 需要 `inherits:true` 才能沿 DOM 继承补间值。
