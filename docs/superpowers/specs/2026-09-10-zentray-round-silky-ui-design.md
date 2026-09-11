# ZenTray 圆润丝滑 UI 改造设计（Round & Silky UI）

- **日期**: 2026-09-10
- **分支**: feature/ui-streamline-design
- **状态**: 已与用户逐节确认，待落地
- **与既有设计稿的关系**: 与 [docs/ui-ux-design-proposal.md](../../ui-ux-design-proposal.md) **融合落地**——该稿已确认项全部保留（Phosphor 图标库、48px 舒缓卡片、字号阶梯、AAA 对比度、四主题系统）；本文在其之上叠加「圆润丝滑 + 曲线 + 色彩编码」设计语言，视觉与动效参数以本文为准。

## 1. 设计支柱

1. **形状 — A · 柔润浮起**：大圆角卡片、柔和投影、分类色左侧「呼吸条」、全胶囊控件；悬停上浮。
2. **色彩编码**（四支柱，均已确认）：
   - 分类识别：8 色相环按分类名 hash 稳定映射
   - 优先级梯度：高红 → 中橙 → 低灰青
   - 进度/时间紧迫度：进度条取分类色，截止临近色相偏移（宽松中性 → <24h 琥珀 → 逾期红）
   - 专注模式氛围：页面背景 ≤6% 色调偏移（专注偏青 / 休息偏天蓝），克制
3. **动效**：
   - hover 微反馈：卡片上浮 3px、呼吸条伸展、主按钮弹性放大
   - 页面过渡 **pt-b 弹性聚拢**：淡入 + scale 0.96→1，260ms `cubic-bezier(0.34,1.56,0.64,1)`
   - 弹层展开 **dg-a 源点生长**：transform-origin 在触发侧，280ms 弹性曲线
   - 收起/退出：一律 140ms 反向、无回弹
4. **用户可选**：动效开关、形状两档（圆润 / 利落），见 §5。

## 2. 设计令牌（styles.css，四主题各一份）

| 类别 | 令牌 | 圆润档（默认） | 利落档 |
|---|---|---|---|
| 圆角 | `--zt-radius-win` | 22px | 12px |
| 圆角 | `--zt-radius-card` | 16px | 8px |
| 圆角 | `--zt-radius-md` | 12px | 6px |
| 圆角 | `--zt-radius-pill` | 999px | 999px |
| 投影 | `--zt-shadow-card` | `0 4px 14px rgba(0,0,0,.25)` | 同值 |
| 投影 | `--zt-shadow-card-hover` | `0 10px 26px rgba(0,0,0,.40)` | 同值 |
| 曲线 | `--zt-ease-out` | `cubic-bezier(0.22,1,0.36,1)` | |
| 曲线 | `--zt-ease-spring` | `cubic-bezier(0.34,1.56,0.64,1)` | |
| 时长 | `--zt-dur-fast / page / dialog` | 180ms / 260ms / 280ms | |
| 时长 | 关闭动画 | 140ms 反向、无回弹 | |

- 浅色主题（Clean Light）投影透明度减半；OLED Midnight 投影加深 10%。
- **分类色**：固定 8 色板（teal / violet / amber / sky / rose / lime / slate / fuchsia），`hash(分类名) % 8` 稳定映射；深浅主题分别调整亮度保证与表面对比。`categoryColor()` 内写死一个固定偏移量，使默认分类「工作/个人/学习」分别落 teal / violet / amber 席位。
- **优先级**：高 `#F87171`、中 `#FB923C`、低 `#94A3B8`（浅色主题各调亮一档）。
- **紧迫度**：>24h 中性 `#94A3B8`、<24h `#FBBF24`、逾期 `#F87171`，进度条色相平滑过渡。

## 3. 组件规格

| 组件 | 规格 |
|---|---|
| 任务卡 | 高 48px（既有确认值）、圆角 `--zt-radius-card`、左侧 3px 分类色呼吸条（默认上下内缩 12px，hover 时各伸展 4px→内缩 8px）、分类胶囊标签、优先级 chip、4px 分类色进度条；勾选完成播 scale 弹跳（既有确认曲线）；hover 上浮 3px + 投影加深；逾期时呼吸条与截止文本改用紧迫度红（优先于分类色） |
| 快速添加 | 全胶囊；聚焦 teal 描边点亮（1px→1.5px） |
| 番茄钟 | SVG 环形实色描边、圆头端点；32px 等宽数字（`font-variant-numeric: tabular-nums`）；专注中环体微辉光（`drop-shadow` 半径 ≤3px） |
| 筛选 chips / 按钮 | 全胶囊；主按钮 hover `scale(1.05)` 弹性；active 档 teal 淡底 |
| 页内弹层（Arco modal/popover/drawer） | dg-a 源点生长；遮罩 `rgba(2,6,23,.45)` + 2px 背景模糊渐入 |
| 宿主弹窗页（VueDialog 整窗） | mount 时播放同族入场（源点偏下、scale .97→1 + 淡入） |
| 页头拖拽栏 | 36px 高（既有确认值），样式随主题令牌刷新 |
| 表单控件（输入/下拉/开关） | focus：teal 1.5px 亮环；error：红描边沿用 Arco 内置（抖动延后：Arco 校验消息常驻重渲染，抖动会随输入反复触发） |
| Message / Toast | 全胶囊圆角 + 顶部滑入淡入 180ms，退出 140ms |
| 空状态 / 加载 | `a-empty` 图标区圆角化；`a-spin` 取主题主色 |
| Tabs / 表格行 | tabs 用 Arco 内置 `type="rounded"`（不自绘指示条）；表格行 hover 用 `--color-surface-hover` |
| 滚动条 | 8px 圆角细条（`::-webkit-scrollbar`），hover 加深 |

## 4. 动效规格

- 路由：`<router-view>` 外包 `<Transition name="zt-page" mode="out-in">`；`.zt-page-enter-from { opacity:0; transform:scale(.96) }`，260ms spring。
- 弹层 keyframes：`zt-dlg-in`（源点 scale .8→1 + 淡入，280ms spring）/ `zt-dlg-out`（scale .88 + 淡出，140ms ease-out）。
- `transform-origin` 注入：Arco modal 打开时按触发元素位置设置（web 侧事件委托，约 15 行）。
- **列表增删**：`<TransitionGroup>`——新增 180ms 淡入 + 8px 上滑；移除 140ms 淡出 + 4px 下坠。
- **主题切换**：`body` 背景 200ms 过渡，其余属性不设过渡（防意外动画）。
- **降级**：`prefers-reduced-motion: reduce` 或设置关档 → 所有过渡降为 140ms 纯淡入，无位移无缩放。

## 5. 设置项（用户可选）

| 设置 | 键 | 值 | 默认 |
|---|---|---|---|
| 界面动效 | `appearance.motion` | `full` \| `off` | `full` |
| 形状风格 | `appearance.shape` | `round` \| `crisp` | `round` |

- 传递链：Python settings → `getSettings()` → `theme.js` 应用 body class（`zt-motion-off` / `zt-shape-crisp`）→ 令牌/动画层按 class 切换。
- 向后兼容：旧 `settings.json` 缺键 → 取默认值，无需迁移。
- Python 改动面：`settings_manager` 两个默认键 + `Settings.vue` 外观区两个控件（合计约 20 行）。
- 氛围色不设独立开关：`motion=off` 时氛围呼吸同步关闭。

## 6. 落地架构（方案 1 · 令牌层 + Arco 接线层）

> **2026-09-11 修订**：P1 验证发现「仅靠覆盖 `--border-radius-small/medium/large` 变量」不够——Arco 大表面不消费这些变量（`.arco-card` 写死 `var(--border-radius-none)`=0px，输入/弹层等各写各的）。变量覆盖保留（123 处消费仍生效），**新增组件接线层**：把关键 Arco 表面直接接到 `--zt-*` 令牌，两档经令牌翻转自动生效。同时修正两处语义：**crisp 档按钮不用胶囊**（用 `--zt-radius-md`，使形状档在按钮上可见）；**motion=off 彻底关闭**（过渡 0s、动画 none），与 `prefers-reduced-motion` 的 140ms 纯淡入降级区分。

| 文件 | 改动 |
|---|---|
| `web/src/styles.css` | 令牌定义（body class 作用域）+ `.zt-*` 组件类 + Arco 变量覆盖（small/medium/large：圆润 8/12/16、利落 4/6/8）+ **Arco 接线层**（`.arco-card→--zt-radius-card`；输入/下拉/菜单/弹层/表格→`--zt-radius-md`；tag/tabs/消息→pill；圆润档按钮 pill、利落档按钮 md） |
| `web/src/theme.js` | `categoryColor(name)` 工具（hash→色板）+ `applyAppearance()` body class |
| `web/src/App.vue` | `<Transition>` 包装 |
| `zentray/services/settings_manager.py` | appearance 两个默认键 |
| 各视图 | 按分期套用 `.zt-*` 类与语义色 |

**平台约束**：窗口级 22px 圆角在 Wayland frameless 下不可实现（合成器不支持透明角），本期窗口保持直角，仅内容层圆角；X11/Windows 不额外适配（同样直角，保持三平台一致）。

## 7. 分期

- **P1 核心面**：令牌层 + theme.js + App.vue 过渡 + 设置项（含 Python 键）+ TaskList / Home 视图改造。
- **P2 交互面**：Progress / TaskForm / QuickAdd / Reminder / TaskAction + 页内弹层 dg-a + `npm run build` 重出 dist。
- **P3 收尾面**：Settings / History / Periodic / SetupWizard 样式统一。（专注模式氛围色延后：番茄钟为托盘服务，web 侧无专注状态消费面，待出现专注页面时再做）

每期结束跑全量回归（Python 单测 + `npm run build`），P1/P2 之间可独立交付验证。

## 8. 验收标准

1. Python 108 项单测全绿。
2. `npm run build` 通过；dist 新 hash 与旧资源删除成对入库（避免坏树）。
3. 4 主题 × 2 形状 × 2 动效 = 16 组合，抽查 TaskList / Home / 一个表单视图无破版。
4. 对比度断言（脚本检查令牌）：主文本 ≥7:1（AAA）、副文本 ≥4.5:1（AA）。
5. 动效降级验证：`prefers-reduced-motion` 与设置关档下均无位移/缩放动画。
6. 拖拽回归：页头拖拽、`zentray://` 桥接、保活复用行为不因样式改动退化。

## 9. 明确不做（YAGNI）

- 窗口级圆角（平台限制，见 §6）
- 纯 Qt 回退弹窗 QSS 化（主路径为 Vue；回退弹窗仅 QWebEngine 不可用时出场，首启 Qt 向导一次性）
- 番茄钟数字翻动动画（等宽数字已防布局抖动）
- 托盘原生菜单（平台原生样式，非 web 管辖）
- 分类色/优先级色编码独立开关（设置噪音）
- 氛围色独立开关（绑定动效开关）
- per-category 自定义颜色 UI
- 组件封装层（评审时的方案 3）
