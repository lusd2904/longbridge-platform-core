# Core Workspace Shell Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `apps/web-portal` 的核心工作台页面建立统一的 hero、指标条和分区标题骨架，改善移动端信息节奏，并让 Web / Android / iOS / macOS 共用同一套内容结构。

**Architecture:** 保留三个页面现有的数据获取与业务逻辑，只抽离重复的展示层骨架组件。通过新增轻量公共组件 `PageHero`、`MetricStrip`、`SectionCardHeader` 收口首屏和卡片头部，再在页面内部用更紧凑的移动端布局替换原来冗长块状结构。

**Tech Stack:** Vue 3, Vite, Element Plus, Sass, Vitest, Vue Test Utils

---

### Task 1: 建立最小单测底座并锁定公共组件行为

**Files:**
- Modify: `apps/web-portal/package.json`
- Modify: `apps/web-portal/vite.config.js`
- Create: `apps/web-portal/tests/unit/page-shell.spec.js`

- [ ] Step 1: 添加单测依赖与命令
- [ ] Step 2: 写 `page-shell.spec.js`，先描述 `PageHero / MetricStrip / SectionCardHeader` 的核心渲染行为
- [ ] Step 3: 运行单测，确认因为组件缺失或输出不符而失败

### Task 2: 新增公共页面骨架组件

**Files:**
- Create: `apps/web-portal/src/components/common/PageHero.vue`
- Create: `apps/web-portal/src/components/common/MetricStrip.vue`
- Create: `apps/web-portal/src/components/common/SectionCardHeader.vue`

- [ ] Step 1: 用最小实现让测试通过
- [ ] Step 2: 补齐响应式样式和 slot 能力
- [ ] Step 3: 再次运行单测确认通过

### Task 3: 替换 Dashboard / Trading / MarketData 首屏

**Files:**
- Modify: `apps/web-portal/src/views/Dashboard.vue`
- Modify: `apps/web-portal/src/views/Trading.vue`
- Modify: `apps/web-portal/src/views/MarketData.vue`
- Modify: `apps/web-portal/src/styles/experience.scss`

- [ ] Step 1: 接入 `PageHero` 和 `MetricStrip`，统一三个页面的首屏骨架
- [ ] Step 2: 接入 `SectionCardHeader`，收口关键卡片头部
- [ ] Step 3: 压缩移动端首屏和分区节奏，避免超长页面首屏
- [ ] Step 4: 运行单测与构建，确认替换未破坏现有行为

### Task 4: 完整验证跨端构建

**Files:**
- Verify only

- [ ] Step 1: 运行 `npm run test:unit`
- [ ] Step 2: 运行 `npm run build`
- [ ] Step 3: 运行 `node ./desktop/smoke.mjs`
- [ ] Step 4: 运行 `npm run android:build`
- [ ] Step 5: 运行 `npm run ios:build`
- [ ] Step 6: 运行 `npm run desktop:mac`
