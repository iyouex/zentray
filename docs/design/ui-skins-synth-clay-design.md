# ZenTray 新皮肤双方案：霓虹 Synth × 黵土 Clay（设计方案）

> 分支：`feature/ui-skins-synth-clay`（自 staging `c7e03b1` 切出）
> 状态：设计定稿 + 已实现。本文档为两套皮肤的完整设计规范。
> 前置：皮肤挂载沿用 `appearance.skin` 体系（同 neo/aurora 机制），浅/深双模式复用
> `theme-light / theme-slate-dark / theme-oled-dark` 三档主题变量。

## 0. 选型来源（开源 UI 设计组件/体系）

| 皮肤 | 主要开源参照 | 借鉴点 |
|------|-------------|--------|
| **Synth 霓虹** | [Catppuccin](https://github.com/catppuccin/catppuccin)、[Tokyo Night](https://github.com/folke/tokyonight.nvim)、[Vercel Geist](https://vercel.com/geist/introduction)、uiverse.io 霓虹卡 | 深靛夜底色板；青/品红/紫三色霓虹强调；辉光描边与聚焦光环 |
| **Clay 黵土** | [Claymorphism 风潮](https://uiverse.io/claymorphism)（uiverse.io / css 玻璃系社区）、[Material 3 Expressive](https://m3.material.io/styles/shape/shape-scale)、shadcn/ui 软卡 | 大圆角实心软表面；对夹式膨膨阴影（光/暗双向）；果冻按压回弹；tonal 选中态 |

与现有两套皮肤的区隔：neo = 硬边 brutalism（方角+硬阴影+lime），aurora = 玻璃拟态（半透明+模糊+渐变极光）。新两套分别补齐「暗色系霓虹电竞感」与「软萌大圆角」两个气质象限，四套皮肤覆盖硬/软/透/光四种质感。

## 1. 霓虹 Synth —— 暗夜霓虹

### 1.1 概念

深夜街机 / synthwave 专辑封面：深靛紫夜幕做底，青与品红做霓虹灯管。所有强调都「发光」——
聚焦环、选中描边、主按钮、滚动条。克制点：辉光只出现在交互态（hover/active/focus），
静态元素保持低亮度，避免长时间使用的视觉疲劳。

### 1.2 色板令牌

**深色（默认 · 夜霓虹）**

| 令牌 | 值 | 说明 |
|------|-----|------|
| `--color-bg-base` | `#12101c` | 靛黑夜幕 |
| `--color-surface` | `#1b1830` | 卡面 |
| `--color-surface-hover` | `rgba(255,255,255,0.06)` | |
| `--color-border` | `#2e2a4a` | 低亮度紫灰 |
| `--color-primary` | `#22d3ee` | 霓虹青 cyan-400 |
| `--color-primary-hover` | `#67e8f9` | |
| `--color-primary-glow` | `rgba(34,211,238,0.35)` | |
| `--color-text-primary` | `#eef0ff` | |
| `--color-text-muted` | `#9d9ec2` | |
| `--color-text-subdued` | `#6f6d94` | |
| `--zt-neon-pink` | `#f472d6` | 品红霓虹（第二强调色） |
| `--zt-neon-violet` | `#a78bfa` | 紫（渐变中转色） |

**OLED 黑**：bg `#08070d`、surface `#100e1a`、border `#242040`，其余同深色。

**浅色（晨雾霓虹）**：霓虹灯在白天的样子——淡丁香底 + 加深至可读的霓虹色。

| 令牌 | 值 |
|------|-----|
| `--color-bg-base` | `#f1eefb` |
| `--color-surface` | `#ffffff` |
| `--color-border` | `#dcd7f0` |
| `--color-primary` | `#0e7490`（cyan-700） |
| `--color-primary-hover` | `#155e75` |
| `--color-primary-glow` | `rgba(14,116,144,0.30)` |
| `--zt-neon-pink` | `#c026d3`（fuchsia-600） |
| `--zt-neon-violet` | `#7c3aed`（violet-600） |
| `--color-text-primary` | `#211f36` |

浅色下文字级强调（优先级 chip、逾期色）沿用基线 theme-light 的深色映射，不发光。

### 1.3 形状 / 阴影 / 动效

- 圆角：card 14px、md 10px、win 18px（比 neo 圆润、比 aurora 利落）
- 阴影：卡面低投影 + **交互态辉光** `0 0 18px var(--color-primary-glow)`
- 动效：hover 辉光淡入 160ms；`--zt-ease-out: cubic-bezier(0.3, 1.2, 0.3, 1)`（霓虹灯通电感）
- motion-off / prefers-reduced-motion：辉光脉冲、按钮发光全部停止，辉光退化为静态描边

### 1.4 组件规范（交互友好的落点）

| 组件 | 行为 |
|------|------|
| 任务卡 hover | 边框亮起 `color-mix(cyan 55%, border)` + 微辉光 |
| 任务卡选中 | 青→品红双色描边（静态，aurora 的流转环在此静音）+ 外辉光 + 底色 `cyan 8%` |
| 主按钮 | 青→紫渐变实底 + 辉光投影；hover 亮度 + 辉光扩散；按下辉光收拢 |
| 次按钮 | 透明底 + 青描边；hover 青字 + 青 8% 底 |
| 输入聚焦 | 青 1.5px 光环 + 品红外晕（双色霓虹） |
| 快速添加胶囊 | 聚焦时双色辉光贯通整圈 |
| 设置导航选中 | 左侧青→品红渐变竖条 + 文字提亮 |
| 页头 | h2 下霓虹渐变下划线（青→品红→透明） |
| 滚动条 | 青→品红渐变 thumb |
| 弹窗 | 顶部 2px 青→品红渐变饰条 + 深卡面 |

### 1.5 可访问性

- 深色正文 `#eef0ff` on `#12101c` ≈ 15:1；muted ≈ 7:1
- 浅色主色 cyan-700 on 白 ≈ 5.6:1（AA）
- 辉光纯装饰，信息永不只靠辉光表达（描边/底色同步变化）
- `:focus-visible` 全局描边保留

## 2. 黵土 Clay —— 软糯膨膨

### 2.1 概念

黏土手办 / Material 3 Expressive 的「软」象限：一切都圆、厚、带弹性的实心表面。
卡片像压出来的软糖——受光面高光、背光面投影；按钮按下会「squish」回弹。
和 aurora 的玻璃不同：**实心不透明**，靠双色对夹阴影制造体积。

### 2.2 色板令牌

**深色（可可软糖）**

| 令牌 | 值 | 说明 |
|------|-----|------|
| `--color-bg-base` | `#211d28` | 暖炭 |
| `--color-surface` | `#2c2735` | |
| `--color-surface-hover` | `rgba(255,255,255,0.06)` | |
| `--color-border` | `#3d3748` | 阴影主导，描边弱化 |
| `--color-primary` | `#ff8a73` | 珊瑚桃 |
| `--color-primary-hover` | `#ffa48e` | |
| `--color-primary-glow` | `rgba(255,138,115,0.30)` | |
| `--color-text-primary` | `#f5efe9` | 暖白 |
| `--color-text-muted` | `#b3a8ba` | |
| `--color-text-subdued` | `#857a90` | |
| `--zt-clay-mint` | `#8fd8b5` | 薄荷（次强调/成功调） |
| `--zt-clay-sun` | `#ffd479` | 奶油黄（警示调） |

**浅色（奶油拿铁，默认）**：`bg #f7f1e8`、`surface #fffdf8`、`border #e7dccd`、
`primary #c2532f`（赤陶，hover `#a84526`）、`text #33291f`；同一对夹阴影换为暖光/暖影。

### 2.3 形状 / 阴影 / 动效

- 圆角：**card 24px、md 16px、win 28px**、按钮恒胶囊；crisp 档收敛为 14/10（仍软）
- 对夹膨膨阴影（体积感的全部来源）：
  - 浅色卡：`8px 8px 20px rgba(59,42,30,0.16), -6px -6px 16px rgba(255,255,255,0.9)` + `inset 0 2px 0 rgba(255,255,255,0.6)` 顶高光
  - 深色卡：`10px 10px 24px rgba(0,0,0,0.5), -4px -4px 14px rgba(255,255,255,0.03)`
- 动效：**果冻弹簧** `--zt-ease-spring: cubic-bezier(0.34, 1.8, 0.5, 1)`；
  按钮 hover `scale(1.04)`、按下 `scale(0.95)`；卡片 hover 上浮 2px + 阴影外扩
- motion-off / reduce：缩放/回弹全部退化为纯色变

### 2.4 组件规范

| 组件 | 行为 |
|------|------|
| 任务卡 | 实心软糖卡；分类色条 4px 全高圆头；hover 上浮+膨影；选中 = tonal 底（`primary 14%` 混 surface）+ 桃色描边 |
| 主按钮 | 珊瑚实底白字 + 膨影 + 内顶高光；hover 放大、按下 squish |
| 次按钮 | surface 实底 + 膨影（不是描边）；hover 提亮 |
| 输入聚焦 | 桃色光环 + 膨影加深（无辉光） |
| 快速添加胶囊 | 大胶囊 + 双层膨影；聚焦阴影收紧内推（被「捏住」的手感） |
| 设置导航选中 | tonal 胶囊整块填充（M3 navigation 样式） |
| 标签 chip | tonal 糖果色填充（mint/sun/珊瑚系），全胶囊 |
| 弹窗 | 28px 圆角 + 大膨影，像浮起的软糖托盘 |
| 滚动条 | 全圆头暖砂色 |

### 2.5 可访问性

- 深色正文 15:1+；浅色赤陶 `#c2532f` on 奶油 ≈ 4.8:1（按钮白字 on 赤陶 ≈ 4.6:1，大号粗体 AA）
- 阴影即层级：不依赖颜色深浅区分表面，深浅模式下体积感同源
- squish 幅度 ≤6%，三帧内完成，不产生位移误读

## 3. 实现挂载（与 neo/aurora 同机制）

1. `web/src/themes/synth.css` / `clay.css`：令牌层（`body.zt-skin-synth[.theme-*]` 按
   皮肤×主题组合覆盖，特异性 0-2-1 压过基线主题块）+ 结构层（组件差异规则）
2. `theme.js applyAppearance()`：皮肤白名单扩为 `neo|aurora|synth|clay`，class 统一
   `zt-skin-<name>` 翻转
3. `index.html` boot 脚本：首帧 class 同步扩展
4. `Settings.vue` 外观卡：皮肤 radio 增至四项 + normalize 守卫
5. `settings_manager.py AppearanceSettings.skin` 白名单同步
6. 全部动效遵守既有 `zt-motion-off` / `prefers-reduced-motion` 双停机制

## 4. 交付物清单

| 交付物 | 位置 |
|--------|------|
| 设计方案 | `docs/design/ui-skins-synth-clay-design.md`（本文档） |
| 原型图 | `.superpowers/prototypes/synth-prototype.html`、`clay-prototype.html`（各含浅/深切换） |
| 分支代码 | `feature/ui-skins-synth-clay`（worktree `../my_todo-ui`） |
