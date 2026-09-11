# ZenTray GSAP 动效升级设计（高级感 · 分层混搭）

- **日期**: 2026-09-11
- **分支**: feature/ui-streamline-design（叠加在「圆润丝滑」P1-P3 之上）
- **状态**: 已与用户确认方向（分层混搭 / 双轨制 / 四类切换全要），待评审
- **与既有设计的关系**: [2026-09-10 圆润丝滑设计](2026-09-10-zentray-round-silky-ui-design.md) 的令牌层、CSS 微交互层、两档开关语义**全部保留**；本文在其上叠加 GSAP 编排级动效。冲突处以本文为准。

## 1. 设计支柱

1. **分层混搭**：日常状态静如止水（CSS 微交互），关键时刻编排级动画（GSAP）——高级感靠克制打底，炫酷用在刀刃上。
2. **流动感**：任何「集合状态变化」（页面、筛选、主题、形状）都不消失重现，而是元素/色彩平滑流动到新状态（Flip / 属性补间）。
3. **物理质感**：弹性曲线、轻微过冲、让位与回弹——与既有 `--zt-ease-spring` 手感同源。
4. **开关语义延续**：动效=关 → GSAP 侧同样彻底关闭；系统减动效 → 140ms 纯淡入。CSS 与 GSAP 两轨永远同进退。

## 2. 设计令牌（GSAP 侧，数值与 zt 令牌对齐）

| 令牌 | 值 | 说明 |
|---|---|---|
| 曲线 spring | `CustomEase` 复刻 `cubic-bezier(0.34,1.56,0.64,1)` | 与 `--zt-ease-spring` 同参数，两轨手感一致 |
| 曲线 out | `CustomEase` 复刻 `cubic-bezier(0.22,1,0.36,1)` | 与 `--zt-ease-out` 同参数 |
| 时长 leave / enter | 120ms / 260ms | 页面转场（用户已确认利落档） |
| 时长 theme / shape | 450ms / 350ms | 主题色彩流动 / 形状圆角变形 |
| stagger | 卡片 40ms、弹层内容 30ms、标题词 35ms | 编排节奏 |
| Flip 弹簧 | spring，dur 400ms | 列表重排 |

- 全部数值集中在 `motion/index.js` 导出（单一事实源），不散落各组件。

## 3. 场景规格

### 3.1 页面转场（替换现 zt-page CSS 类）
- 保留 `<Transition name="zt-page" mode="out-in">` 骨架，CSS 过渡类退役，JS 钩子（`@leave`/`@enter`）调 timeline。
- **退场** 120ms：视图根直接子块（卡片/分组）`translateY(8px)` + 淡出，stagger 15ms，ease-out。
- **入场** 260ms：页面标题 SplitText 逐词浮升（mask 上移）+ 内容卡片 stagger 40ms 弹簧浮升。
- `zentray:reopen` 的 viewKey 重入场复用入场编排。
- **窗口首开**：`#app` 整窗缩放 CSS 动画退役，改为首屏卡片 stagger 浮升（+遮罩快淡入）。

### 3.2 列表增删/筛选（Flip）
- 增删：沿用现有 TransitionGroup（zt-list）。
- 筛选/重排：点击筛选 chip → `Flip.getState(卡片集)` → 数据更新 → `Flip.from(state, {duration:400, ease:spring, stagger:20, absolute:true})`。幸存卡片流动到新位置，不闪烁重建。
- 首期只接 TaskList（含其分组/筛选）；其他视图出现筛选需求时复用同一封装。

### 3.3 弹层开合（内容层 stagger）
- 面板 dg-a 源点生长骨架（CSS，2026-09-11 刚验收）**保留不动**。
- 新增 `v-stagger` 自定义指令：挂 modal/drawer 内容根节点，打开时内容块（标题/正文/操作区）依次 `translateY(12px)` 浮升淡入，stagger 30ms，260ms。
- 指令挂在我们自己的内容根节点上，不依赖 Arco 内部结构；Arco modal 经 teleport 渲染不受影响。

### 3.4 主题/形状切换（@property + 补间）
- 全部主题色令牌（4 主题块的颜色变量）与圆角令牌（`--zt-radius-card/md/win`）注册 `@property`（`<color>` / `<length>`，`inherits:true`）。
- 切主题：`applyAppearance` 翻转 body class 后，GSAP 补间 body 上旧→新值，450ms——全界面色彩流动渐变。
- 切形状：圆角令牌补间 350ms，界面平滑变形。
- 补间期间重复切换：GSAP overwrite 自动从当前值接管，无跳变。
- 动效=关：不补间，瞬时切换（现行为）。

### 3.5 关键时刻
- **任务完成**：对勾 scale 弹性 pop（elastic）+ 涟漪环扩散 + 相邻卡片 2px 让位回弹（弹簧），~500ms 总编排。
- **快速录入聚焦**：输入区 scale(1.01) 弹性 + 阴影绽放（与 CSS 聚焦亮环叠加）。
- 不做：文字打字机、3D 视差、数字翻滚（旧 spec 已排）。

## 4. 架构

| 文件 | 职责 |
|---|---|
| `web/package.json` | + `gsap`（唯一新增依赖） |
| `web/src/motion/index.js` | 插件注册（Flip/SplitText/CustomEase，仅这几个）、共享曲线与时长常量、`shouldAnimate()`/`reducedMotion()` 查询、matchMedia 降级注册 |
| `web/src/App.vue` | 页面转场 JS 钩子 + 窗口首开编排 |
| `web/src/theme.js` | 主题/形状切换补间（applyAppearance 内） |
| `web/src/views/TaskList.vue` | Flip 封装 + 任务完成编排 |
| `web/src/directives/stagger.js` | `v-stagger` 指令（modal 内容编排） |
| `web/src/styles.css` | `@property` 注册块 + 退役规则清理（zt-page 类、#app host-in） |

- 双轨边界纪律：**单元素、瞬时反馈、<200ms → CSS；多元素、有次序、有叙事 → GSAP**。
- Vue 集成规范（gsap-frameworks skill）：全部编排 `gsap.context(fn, 容器ref)` 创建、`onUnmounted` `ctx.revert()`；插件只在 motion/index.js 注册一次；选择器必须带 scope。

## 5. 设置与降级矩阵

| 状态 | CSS 轨 | GSAP 轨 |
|---|---|---|
| 动效=full（默认） | 现行全部 | 全部编排生效 |
| 动效=off | blanket 0s/none（现行） | **不创建 timeline**（创建前 `shouldAnimate()` 门禁）；运行中立即 kill |
| 系统 prefers-reduced-motion | 140ms 纯淡入（现行） | `gsap.matchMedia` 注册降级版：仅淡入 140ms，无位移无缩放、Flip/stagger 关闭 |
| 双叠加 | — | 关档优先 |

- Python 侧零改动（appearance 键不变）；设置传递链不变。

## 6. 分期

- **M1 基座 + 模式切换**：npm i gsap、motion/index.js、@property 注册、主题/形状补间、降级矩阵。最快见效，风险最低。
- **M2 转场**：页面转场 JS 钩子 + SplitText 标题 + 窗口首开 stagger，退役对应 CSS。
- **M3 列表与关键时刻**：TaskList Flip、v-stagger 弹层内容、任务完成/快速录入聚焦编排。
- 每期收尾：`npm run build` dist 成对入库 + Python 112 项回归 + 手测清单（沿用上轮纪律）。

## 7. 验收标准

1. Python 112 项单测全绿（零 Python 改动）。
2. `npm run build` 通过；dist 新旧 hash 成对入库。
3. 降级矩阵逐格验证：full / off / 系统 reduce / 双叠加，GSAP 侧行为与表格一致。
4. 4 主题 × 2 形状切换补间无破版、无残色；重复快速切换无跳变。
5. 10 个视图转场抽查流畅无闪烁；Flip 筛选不重建 DOM 闪烁。
6. 拖拽回归：页头拖拽、`zentray://` 桥接、保活复用不退化。

## 8. 明确不做（YAGNI）

- ScrollSmoother / Draggable / Inertia / Observer（无场景）
- DrawSVG / MorphSVG（图标为 fill 型，无 stroke 可描）
- 3D 视差、GSDevTools 进生产
- 窗口级动画（Qt 侧零改动）
- ScrollTrigger 驱动动画（桌面固定高窗口，滚动叙事场景仅列表内滚动，首期不接）
- 每场景独立配置 UI（令牌集中在 motion/index.js，不加设置项）
