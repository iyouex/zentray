# ZenTray 前端 UI/UX 深度重构与设计规范 (Design System & Component Spec)

> **设计目标**：依托 `ui-ux-pro-max`、`frontend-design`、`web-design-guidelines` 与 `vercel-react-best-practices` 规范，为 ZenTray 打造符合现代桌面端高质感、无边框、平滑微交互的全局 UI/UX 规范与组件设计方案。
> **状态**：用户已确认决策项，已形成完整实施级设计规范（纯设计规划，待用户指示后落地代码）。

---

## 🎨 第一部分：全局主题与多主题切换系统 (Theme System)

根据用户要求，**所有主题均为可选项**，系统提供 4 套高对比度、风格鲜明的主题，用户可在设置面板中自由切换，并支持系统层 (`prefers-color-scheme`) 自动联动。

### 1.1 可选主题类型与 Token 定义 (Themes)

1.  **ZenSlate Dark (默认 - 专注 Slate 深色)**：
    *   `--color-bg-base`: `#0F172A` (Slate 900)
    *   `--color-surface`: `#1E293B` (Slate 800)
    *   `--color-surface-hover`: `rgba(255, 255, 255, 0.04)`
    *   `--color-border`: `#334155` (Slate 700)
    *   `--color-primary`: `#0D9488` (Teal 600)
    *   `--color-primary-hover`: `#14B8A6` (Teal 500)
    *   `--color-primary-glow`: `rgba(20, 184, 166, 0.25)`

2.  **OLED Midnight (高对比纯黑模式)**：
    *   `--color-bg-base`: `#000000` (Pure OLED Black)
    *   `--color-surface`: `#121212` (OLED Dark Grey)
    *   `--color-surface-hover`: `rgba(255, 255, 255, 0.06)`
    *   `--color-border`: `#262626`
    *   `--color-primary`: `#10B981` (Emerald 500)
    *   `--color-primary-hover`: `#34D399` (Emerald 400)
    *   `--color-primary-glow`: `rgba(16, 185, 129, 0.3)`

3.  **Clean Light (日间清爽浅色)**：
    *   `--color-bg-base`: `#F8FAFC` (Slate 50)
    *   `--color-surface`: `#FFFFFF` (Pure White)
    *   `--color-surface-hover`: `rgba(0, 0, 0, 0.02)`
    *   `--color-border`: `#E2E8F0` (Slate 200)
    *   `--color-primary`: `#0D9488` (Teal 600)
    *   `--color-primary-hover`: `#0F766E` (Teal 700)
    *   `--color-primary-glow`: `rgba(13, 148, 136, 0.15)`

4.  **System Auto (跟随 OS 自动切换)**：
    *   实时监听 `(prefers-color-scheme: dark)`，自动映射至 Slate Dark 或 Clean Light。

### 1.2 字体排版系统 (Typography Scale)

*   **字系 (Font Family)**：`Inter`, `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `Roboto`, `sans-serif`
*   **字号与行高阶梯 (Type Hierarchy)**：
    1.  **Display Level (大标题/番茄钟数字)**: `32px` / 行高 `40px` (SemiBold 600)
    2.  **Dialog Title (弹窗标题)**: `18px` / 行高 `24px` (SemiBold 600, letter-spacing `-0.01em`)
    3.  **Section Header (分组标题)**: `14px` / 行高 `20px` (Medium 500, uppercase `0.05em`)
    4.  **Body Text (任务内容/默认文本)**: `14px` / 行高 `22px` (Regular 400)
    5.  **Caption & Badge (标签/副信息)**: `12px` / 行高 `16px` (Medium 500)

---

## 🧩 第二部分：核心页面组件设计蓝图 (frontend-design & User Confirmed)

用户已确认：**图标库统一采用 Phosphor Icons (`@phosphor-icons/vue`)**，**卡片布局采用 Spacious & Animated 舒缓型微卡片 (`48px` 高度)**。

```
+-------------------------------------------------------------------+
|  [Drag-Bar] ZenTray Task Manager                        [Esc/X]   |
+-------------------------------------------------------------------+
|  +-------------------------------------------------------------+  |
|  | Quick Add: "Add new task or command..."            [+ Add]  |  |
|  +-------------------------------------------------------------+  |
|                                                                   |
|  Filter: [ All ] [ Active ] [ Completed ]        Sort: [ Deadline] |
|  ---------------------------------------------------------------  |
|  [✓] Complete quarterly report                 (Overdue) [Work]   |  <- 48px Height
|      * 14:00 - 15:30  | ⏱ Pomodoro: 2/4                         |
|  [ ] Prepare team sync demo                             [Personal]|  <- 48px Height
|      * Tomorrow 10:00                                             |
|                                                                   |
|  +-------------------------------------------------------------+  |
|  | ⏱ Pomodoro Hub: Focus Mode Active (22:45 remaining)  [Pause]|  |
|  +-------------------------------------------------------------+  |
+-------------------------------------------------------------------+
```

### 2.1 组件一：Frameless Window Chrome & Nav Header (无边框窗口头部与页内控制栏)
*   **图标应用**：使用 Phosphor 图标组件 `<PhX />`, `<PhMinus />`, `<PhGear />`, `<PhSquaresFour />`。
*   **设计细节**：
    *   顶部 `36px` 柔和拖拽区域 (`-webkit-app-region: drag` / PySide event filter)。
    *   右侧悬浮页内关闭/取消控制项，图标悬浮时具有 `scale(1.1)` 柔和反馈。

### 2.2 组件二：Task List & Quick Add Card (舒缓型任务卡片与极速新增)
*   **布局参数**：
    *   卡片高度：固定 `48px`（含行高与上下边距），提供舒适的视线间距。
    *   图标应用：完成复选框使用 Phosphor `<PhCheckCircle />`（未完成为 `<PhCircle />`）。
*   **动画与微交互**：
    *   勾选完成时，`<PhCheckCircle />` 触发 `scale(0.8) -> scale(1.15) -> scale(1.0)` 的波形弹跳动画（0.25s 弹性曲线 `cubic-bezier(0.34, 1.56, 0.64, 1)`）。
    *   卡片悬浮状态：产生 `translateY(-1px)` 浮动，背景由 `--color-surface` 变为 `--color-surface-hover`，左侧隐约显现 `2px` 亮色线索框。

### 2.3 组件三：Pomodoro & Focus Mode Ring (番茄钟与专注状态控制组)
*   **图标应用**：`<PhPlay />`, `<PhPause />`, `<PhArrowCounterClockwise />`。
*   **设计细节**：
    *   **SVG 环形倒计时**：底层渐变轨迹，上层为动态 `stroke-dashoffset` 过渡动画（`1s linear`）。
    *   **数字倒计时**：`32px` 极简等宽数字（Monospace font variant），避免数字更替时的布局抖动（Layout Shift）。

### 2.4 组件四：Vue Router Dialog Host Container (通用的 WebDialog 宿主容器)
*   **设计细节**：
    *   外层带 `1px solid var(--color-border)` 细柔微光外框与 `0 20px 50px rgba(0,0,0,0.5)` 落地阴影，增强桌面浮动层级感。

---

## 🔍 第三部分：代码与视觉审查与优化规范 (web-design-guidelines & vercel-react-best-practices)

### 3.1 无障碍与视觉对比度规范 (web-design-guidelines)
1.  **对比度断言**：所有主文本在深色/浅色背景下的对比度均高于 **7.0:1**（WCAG AAA 级），副文本高于 **4.5:1**（WCAG AA 级）。
2.  **键盘焦点**：所有交互元素配置统一的 `:focus-visible` 样式：
    ```css
    :focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
    }
    ```
3.  **SVG 图标语义**：装饰性图标显式添加 `aria-hidden="true"`，纯图标按钮必须配置 `aria-label="关闭窗口"` 或 `aria-label="新增任务"`。

### 3.2 性能与渲染优化规范 (vercel-react-best-practices 迁移至 Vue 3 / Vite)
1.  **Eliminating Waterfalls (并发加载)**：
    *   WebBridge 交互采用 `Promise.all([fetchTasks(), fetchCategories(), fetchSettings()])` 并行并发。
2.  **Bundle Size Optimization (包体积与动态路由)**：
    *   路由组件采用 Vite 动态导入：`defineAsyncComponent(() => import('./views/Settings.vue'))`。
3.  **Re-render & Virtualization Optimization (高性能列表)**：
    *   针对大量任务列表，使用 `shallowRef` 存储 Task 数组，配合 CSS `content-visibility: auto` 进行万级 DOM 虚拟化过滤。

---

## 🚀 第四部分：落地实施计划 (Implementation Roadmap)

1.  **CSS 样式与多主题系统层 (`web/src/styles.css` & `web/src/theme.js`)**：
    - 增加 OLED Midnight、ZenSlate Dark、Clean Light 及 System Auto 的 CSS 变量映射。
2.  **组件层体验改造 (`web/src/views/TaskList.vue`, `Progress.vue`, `TaskForm.vue`, `App.vue`)**：
    - 将 Arco 原生图标替换为选定的 `@phosphor-icons/vue` 柔和图标。
    - 将任务卡片调整为 `48px` 舒缓型高度，并添加 SVG 完成复选波形动画。
    - 在界面头部规范无边框页内 Close / Minimize 控制项。
3.  **自动化测试与构建校验 (`scratch/self_test.py` & `build_package.sh`)**：
    - 校验全量 9 个弹窗无边框、桌面居中、拖拽过滤器及全量 83 项 unit tests 持续通过。
