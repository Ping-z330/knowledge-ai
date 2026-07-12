# DESIGN.md

> 深绿学术风 + 亮色强调，知识库工具应有的专业感与克制。

## 1. Visual Theme & Atmosphere

**Style**: Academic Green（深绿学术）
**Keywords**: 专业、安静、学术、克制、纸张感、工具感、暗侧栏
**Tone**: 像大学图书馆阅览室——深木色、暖灯光、白纸黑字 — NOT 炫技、霓虹、娱乐化
**Feel**: 如同一本打开的硬壳笔记本，侧栏是书架，主区域是书页

**Interaction Tier**: L1 精致静态（优雅 hover + 柔和入场）
**Dependencies**: CSS only（Ant Design Vue 内置动效）

## 2. Color Palette & Roles

```css
:root {
  /* Backgrounds */
  --bg: #eef1ec;                                /* 页面背景，浅绿网格纸感 */
  --surface: rgba(255, 255, 255, 0.84);         /* 卡片/面板 */
  --surface-alt: #f8faf5;                       /* 交替区域（输入框、检索结果） */
  --surface-hover: rgba(255, 255, 255, 0.95);   /* 面板 hover */
  --surface-dark: #15231f;                      /* 暗色表面（侧栏、回答区） */

  /* Borders */
  --border: rgba(35, 48, 43, 0.09);             /* 面板边框 */
  --border-light: #dfe6dc;                      /* 浅边框（输入框） */
  --border-hover: rgba(216, 243, 107, 0.45);    /* 侧栏 item hover 边框 */

  /* Text */
  --text: #1f2a25;                              /* 标题 */
  --text-secondary: #65726c;                    /* 正文、描述 */
  --text-tertiary: #8a968f;                     /* 标签、辅助 */
  --text-on-dark: #f7fbf4;                      /* 暗底文字 */
  --text-on-dark-secondary: #cfdad3;            /* 暗底次要文字 */

  /* Accent */
  --accent: #2f6f5e;                            /* 主强调（按钮、链接、图标） */
  --accent-hover: #245a4c;                      /* 强调 hover */
  --accent-glow: #d8f36b;                       /* 亮黄绿（高亮、强调标记、badge） */

  /* RGB variants for rgba() */
  --bg-rgb: 238, 241, 236;
  --accent-rgb: 47, 111, 94;
  --accent-glow-rgb: 216, 243, 107;
  --surface-dark-rgb: 21, 35, 31;

  /* Semantic */
  --success: #2f6f5e;
  --error: #b42318;
  --warning: #d97706;
  --info: #1677ff;
}
```

**Color Rules:**
- 所有颜色通过 CSS 变量引用，禁止硬编码 hex（除 Ant Design token 配置）
- 暗色表面（`--surface-dark`）仅用于侧栏和回答区，不扩散到其他卡片
- 亮黄绿 `--accent-glow` 只用于强调——badge、高亮词、侧栏 active 态，不做大面积背景
- 一个 section 内最多一个强调色
- 侧栏文字用浅色系，主内容区用深色系，两者对比不混用

## 3. Typography Rules

**Font Stack:**
```css
font-family: Aptos, 'Segoe UI', sans-serif;
```

| Role | Font | Size | Weight | Line Height | Letter Spacing |
|------|------|------|--------|-------------|----------------|
| Page H2 | Aptos | 34px | 780 | 1.08 | — |
| Panel H3 | Aptos | 18px | 760 | 1.2 | — |
| Panel H4 | Aptos | 14px | 720 | 1.35 | — |
| Body | Aptos | 15px | 400 | 1.72 | — |
| Small / Label | Aptos | 13px | 640 | 1.55 | — |
| Caption | Aptos | 11px | 640 | 1.35 | 0.06em |
| Sidebar | Aptos | 14px | 760 | — | — |
| Mono/Code | JetBrains Mono | 13px | 400 | 1.6 | — |

**Typography Rules:**
- 中文正文行高 ≥ 1.7
- 标题 weight ≥ 700
- 侧栏 uppercase label 用 `letter-spacing: 0.12em`
- **NEVER use**: 中华细黑、华文行楷、Comic Sans、装饰性字体

**Text Decoration:**
- 标题：无渐变、无投影（克制风格）
- 强调文字：用 `--accent-glow` 背景高亮（如检索结果中的匹配词高亮）
- 答案区引用标记 `[1]`：亮色前景，hover 变白

## 4. Component Stylings

### Buttons
```css
/* Primary */
.ant-btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 8px 20px rgba(var(--accent-rgb), 0.12);
}
.ant-btn-primary:hover { background: var(--accent-hover); }

/* Ghost on dark surface (sidebar) */
.sidebar .ant-btn { color: #b7c5bd; }
.sidebar .ant-btn:hover { color: #dbe6df; }
```

### Cards / Panels
```css
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 16px 44px rgba(22, 35, 30, 0.07);
}
```

### Input Area
```css
.ask-box, .conv-input-area {
  background: var(--surface-alt);
  border: 1px solid var(--border-light);
  border-radius: 8px;
}
```

### Answer Block
```css
.answer-block, .answer-main {
  background: var(--surface-dark);
  border-radius: 8px;
  padding: 16px 20px;
  color: var(--text-on-dark);
}
```

### Tags / Badges
- 状态 ready：`color="success"`（绿色）
- 引用标记：`color="blue"`（蓝色）
- Agentic badge：渐变浅蓝底 + 蓝色文字 + 蓝色边框

### Source Cards
```css
.source-card {
  background: #fff;
  border: 1px solid #e4e9e5;
  border-radius: 6px;
  padding: 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.source-card:hover {
  border-color: #bccfc2;
  box-shadow: 0 2px 6px rgba(22, 35, 30, 0.04);
}
/* 引用 hover 高亮 */
.source-card.citation-highlight {
  border-color: var(--accent-glow);
  background: rgba(var(--accent-glow-rgb), 0.07);
  box-shadow: 0 0 0 2px rgba(var(--accent-glow-rgb), 0.25);
}
```

### Sidebar Items
```css
.kb-item {
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 7px;
}
.kb-item:hover { transform: translateY(-1px); }
.kb-item.active {
  color: #15231f;
  background: var(--accent-glow);
  border-color: var(--accent-glow);
}
```

### Error/Empty States
```css
/* 全局错误 Toast */
.error-toast {
  background: var(--error);
  color: #fff;
  border-radius: 8px;
}
/* 空状态 */
.empty-state {
  min-height: 120px;
  border: 1px dashed #cdd7cf;
  border-radius: 8px;
}
```

## 5. Layout Principles

**Shell:**
- Sidebar: 320px fixed, sticky top, 100vh
- Workspace: fluid (剩余宽度)

**Spacing Scale:**
- Workspace padding: 28px
- Panel padding: 20px
- Section gap: 16-20px
- Card internal padding: 10-14px

**Grid:**
- 文档管理：全宽单列
- 对话界面：全宽单列
- 历史记录：固定高度列表 + 底部分页

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat | 无阴影 | 文本、边框线 |
| Subtle | `box-shadow: 0 8px 24px rgba(22,35,30,0.04)` | 导航栏 |
| Raised | `box-shadow: 0 16px 44px rgba(22,35,30,0.07)` | 面板卡片 |
| Floating | `box-shadow: 0 18px 50px rgba(22,35,30,0.08)` | 欢迎卡片 |

## 7. Animation & Interaction

**Motion Philosophy**: 克制优雅，只用 opacity 和 transform。不做花哨动效。

**Tier**: L1 — 精致静态

### Entrance Animation
```css
/* 面板淡入 — 无 JavaScript，纯 CSS（Ant Design 内置）*/
```

### Hover & Focus States
```css
/* 侧栏 item hover */
.kb-item:hover { transform: translateY(-1px); transition: 0.18s ease; }

/* 按钮 hover — Ant Design 默认 */
/* 来源卡片 hover */
.source-card:hover { border-color: #bccfc2; }

/* 引用标记 hover（答案文本内） */
.citation-link:hover { color: #fff; text-decoration: underline; }

/* 检索结果折叠栏 hover */
.retrieval-summary-bar:hover { border-color: #bccfc2; background: #f2f6ef; }

/* 流式输出呼吸灯 */
@keyframes streaming-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
.streaming-dot { animation: streaming-pulse 1s ease infinite; }

/* 引用高亮闪烁 */
@keyframes source-flash { 50% { background: rgba(216,243,107,0.18); } }
.source-flash { animation: source-flash-anim 0.6s ease 2; }
```

### Citation Interaction（重点）
```
用户 hover 回答中的 [1] → 对应 .source-card[data-source-citation="1"] 添加 .citation-highlight
用户 click [1] → 右侧来源面板滚动到对应卡片
```

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  .streaming-dot { animation: none; }
  .source-flash { animation: none; }
  .kb-item:hover { transform: none; }
}
```

## 8. Do's and Don'ts

### Do
- 面板使用统一圆角 8px
- 颜色全部引用 CSS 变量
- 侧栏和主内容区配色严格分离（暗 vs 亮）
- 空状态始终显示引导文案
- 所有可点击元素有 hover 反馈
- 错误信息明确告诉用户原因和修复方法
- 长列表固定高度 + overflow scroll，分页固定底部

### Don't
- ❌ 不要在亮底上使用暗底文字色（反之亦然）
- ❌ 不要硬编码 hex 颜色值（Ant Design token config 除外）
- ❌ 不要让空状态区域超过 200px 高度
- ❌ 不要出现横向溢出（所有容器 `min-width: 0`）
- ❌ 不要在答案区外使用 `--surface-dark`
- ❌ 不要吞掉 API 错误静默失败
- ❌ 不要让引用来源和回答分离超过一屏距离
- ❌ 不要让用户猜哪里可以点击

## 9. Responsive Behavior

**Breakpoints:**
| Name | Width | Key Changes |
|------|-------|-------------|
| Desktop | > 1180px | 侧栏 320px + 全宽工作区 |
| Narrow | 820-1180px | 侧栏缩至 280px |
| Tablet | 520-820px | 侧栏变顶部导航，单列布局 |
| Mobile | < 520px | 按钮竖排，输入控件纵向堆叠 |

**Touch Targets:** minimum 44×44px
**Collapsing Strategy:** 窄屏时侧栏变水平导航（当前为 static position + auto height）

```css
@media (max-width: 820px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { position: static; height: auto; }
  .answer-layout { grid-template-columns: 1fr; }
}
@media (max-width: 520px) {
  .ask-actions { flex-direction: column; }
  .retrieval-toolbar { flex-wrap: wrap; }
}
```
