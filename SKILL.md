---
name: shopee-light-listing
description: "Shopee 轻出海铺货实操：从1688遨虾(aibuy)Shopee区域榜单选品→点找同款挑1688现货→快递助手ERP跨境版链接采集→公共采集箱全选→铺货至Shopee轻出海→发布记录统计成功/审核中/失败与失败原因。当用户要给Shopee轻出海/Shopee代运营供货铺品、批量上传1688货源到Shopee、测批量发布成功率、按榜单选品采集铺货时使用。选品匹配与红线判定保留人工确认，登录由用户接管。基于受控浏览器(aha_browser_use / bu)操作，不做无头爬虫。"
---

# Shopee 轻出海铺货（遨虾选品 → 1688采集 → 快递助手铺货 → 成功率统计）

## Overview

在快递助手ERP跨境版内，把1688货源批量铺到 Shopee 轻出海（平台代运营、卖家只供货）。
整条链路用受控浏览器 `bu`（`import aha_browser_use as bu`, `plane="bu"`）完成，不写无头爬虫、不调用未公开API。

**三类动作分层：**
- **自动（Agent直接做）**：批量采集、公共采集箱对账、全选、勾选店铺、提交、发布记录统计。
- **人工确认（Agent给候选，人拍板后再继续）**：图搜挑同款匹配、红线判定、提交前核对店铺与结算价。
- **人工接管（Agent不得代做）**：登录、短信/验证码、支付。

## 执行前约定

- 始终先 `bu.snapshot()` / `bu.find()` 观察拿到 ref 再动作；导航或翻页后旧 ref 失效，必须重新观察。
- 所有页面都是登录态 + 前端动态渲染。遇到 `blocked=auth`、跳转登录页、验证码，**立即** `interaction.request_action(type="browserControl")` 请用户接管，不要文本求登录、不要绕登录。
- 不存储、不输入任何账号密码；登录态由用户在浏览器里完成。
- 结算价模板（默认 `来源价×130% + 5.00 − 0.00`）由用户在ERP内预先配置，本流程沿用，不每次重算。

## 工作流（6步，标注自动化边界）

### Step 0 登录检查（人工接管）
- 导航快递助手ERP任意页面，若被重定向到登录页或 `blocked=auth`，调用 `interaction.request_action(type="browserControl")` 请用户登录；返回后重新 `bu.snapshot()` 验证登录态再继续。

### Step 1 遨虾榜单选品（半自动，人工确认候选）
- 榜单基础URL（Shopee海外飙升榜）：
  `https://aibuy.1688.com/landingpage/outer-rank-similar.html?platformCode=Shopee_ZX&ranking=103&bizType=ERP&customerId=kdzhushou&lang=zh&tabCode=overseas_soaring_list`
- 切目标国家（如"马来西亚"）、切目标类目、翻页浏览。**`back` 会丢失国家/类目/翻页状态，禁止靠后退恢复**；用 references/browser-recipes.md 的"恢复榜单序列"。
- 红线筛选规则、图搜挑货规则见 references/selection-rules.md。
- **人工确认点**：Agent 列出候选品（标题、同款数、下游价/站内价），由用户确认哪些进入采集；Agent 不自行拍板品牌/合规/倒挂判断。

### Step 2 找同款取1688 URL（半自动，人工确认匹配）
- 榜单品的"找同款"是按钮，`oppItemId/rankId` 点击时前端生成、HTML里抓不到，必须真实点击导航，不能预构造URL。
- 结果页噪声大（混入无关品），**禁止自动取第一条**；优先选带"销量最高/发货最快"标签且与榜单品匹配的1688现货，向用户展示候选后确认。
- 记录标准格式URL：`https://detail.1688.com/offer/<offerId>.html`，累积成清单。

### Step 3 批量链接采集（自动）
- 进 ERP「商品采集-链接采集」页，textarea 一次粘贴多个URL（Enter换行，单次最多500），点"开始采集"。
- 读取"本次共采集N个，成功X、失败Y"，失败的逐条核对URL后重试或剔除。代码见 references/browser-recipes.md。

### Step 4 公共采集箱对账（自动）
- 进「公共采集箱」，核对条数与货源ID与Step2清单一致；不一致先补齐/剔除再铺货。

### Step 5 铺货提交（半自动，人工确认店铺与模板）
- 全选行 checkbox → 点"铺货至Shopee轻出海" → 勾选目标店铺。
- **人工确认点**：提交前向用户确认店铺正确、结算价模板沿用、库存"使用商品来源"、发货方式"非预售"。
- 配置窗可沿用已保存模板直接"保存"；弹窗回到列表后再点"开始铺货"，直到出现"已提交N个商品"提示。

### Step 6 发布记录统计（自动，终态需等待）
- 进「Shopee轻出海-发布记录」，按货源ID逐条归类。统计口径见下；代码见 references/browser-recipes.md。
- 审核/上传为异步，现场等待不改变终态；记录初始快照，告知用户稍后刷新复核。

## 状态口径（务必区分，不可混算）

| 状态 | 性质 | 是否计入成功 |
|---|---|---|
| 发布中 / 审核中 / 排队中 | 中间态 | 否 |
| 发布成功 | 终态成功 | 是 |
| 发布失败 | 终态失败 | 否，需记原因 |

- **提交成功率** = 进入发布队列数 / 采集数（Step5完成即得）。
- **最终发布成功率** = 发布成功数 / 提交数（等平台审核后才可得）。
- **出单** 是更后置的真实订单结果，与发布成功率无关，不得用"铺完"推断"会出单"。

## References
- `references/selection-rules.md`：选品红线清单、图搜挑货规则、结算价说明、失败原因归因库。选品/判定前必读。
- `references/browser-recipes.md`：bu 可复用代码片段（恢复榜单序列、批量采集、对账、铺货提交、状态统计）。执行时复制并按当前页面调整。
