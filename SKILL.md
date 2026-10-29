---
name: shopee-light-listing
description: "Shopee 轻出海铺货实操，仅适用于『快递助手ERP跨境版(erp.kuaidizs.cn) + Shopee轻出海』模式：只读接口拉1688遨虾(aibuy)Shopee区域榜单→AI按评分规则自动判定最优商品→接口关键词/图搜自动匹配1688现货→ERP接口批量链接采集→公共采集箱接口对账→接口自动铺货至Shopee轻出海→发布记录接口统计成功/审核中/失败与失败原因。当用户要给Shopee轻出海/Shopee代运营供货铺品、批量上传1688货源到Shopee轻出海、测批量发布成功率、按榜单自动选品采集铺货时使用。不适用于其他ERP、Shopee自营店铺、Lazada/TikTok等其他平台铺货。选品与铺货全自动执行，仅ERP登录/短信验证码/支付由用户接管；硬红线（品牌侵权、动漫卡通/影视IP联名如Hello Kitty/迪士尼/漫威/宝可梦、液体化工、带电、食品保健医疗、宗教、易碎、活体）由AI按标题+主图自动剔除，拿不准的品跳过不发。Step1/2 用只读 mtop 接口取候选、Step3-6 全部用 ERP 接口采集/对账/铺货/统计（个人低频、复用浏览器登录态不绕登录；collect/distribute 写操作仅提交点名清单）。"
---

# Shopee 轻出海铺货（接口取候选 → 1688采集 → 快递助手铺货 → 成功率统计）

## Overview

在快递助手ERP跨境版内，把1688货源批量铺到 Shopee 轻出海（平台代运营、卖家只供货）。

链路分三段：
- **Step1/2 取候选（只读接口）**：用 `scripts/aibuy_rank_client.py` 匿名拉遨虾榜单、检索1688现货，导出候选清单；个人只读、低频、不转售，接口细节见 `references/api-candidates.md`。
- **Step3/4/4.5/5/6 采集/对账/铺货/统计（ERP接口）**：用 `scripts/erp_api_client.py` 直连快递助手ERP后台接口完成链接采集提交（collect，写操作）、采集箱对账（items）、发布记录去重/统计（logs）、店铺预查（shops）、铺货提交（distribute，写操作）；登录态复用浏览器 JWT（`qnquerystring` 头认证），比浏览器点击更快更准；接口细节见 `references/erp-api.md`。
- **Step3-6 兜底（受控浏览器 `bu`，`import aha_browser_use as bu`, `plane="bu"`）**：接口失效/改版/风控时回退浏览器（采集/对账/去重/铺货/统计对应 `browser-recipes.md` 第3/4/7/5/6节），不绕登录、不写账号密码。

接口失效或被风控时，Step1/2 回退 `references/browser-recipes.md` 第1/2节，Step3/4/4.5/5/6 回退第3/4/7/5/6节。

## 适用范围（模式绑定）

**本 Skill 只适用于一种模式：`快递助手ERP跨境版（erp.kuaidizs.cn）+ Shopee 轻出海（平台代运营、卖家供货）`。**

- **适用**：接口拉遨虾榜单 → AI自动判定最优 → 接口检索1688现货自动匹配 → 1688链接采集 → 公共采集箱对账 → 自动铺货至Shopee轻出海 → 发布记录统计成功率。
- **不适用**（会因页面/URL/选择器不同而失效，不得直接套用）：
  - 其他ERP（甩手、芒果店长、店小秘等）；
  - Shopee 自营店铺直接上架（非轻出海代运营模式）；
  - 其他平台铺货（Lazada、TikTok Shop、Amazon等）；
  - 无遨虾(aibuy)榜单入口或不带 `bizType=ERP&customerId=kdzhushou` 参数的选品来源。

所有 URL、选择器、结算价模板、成功率口径、失败归因都基于该模式实测；换模式时需重做链路适配，不能只改参数。

**动作分层（全自动选品铺货，仅登录类人工接管）：**
- **AI自动（Agent直接做，不再停下来问人）**：拉榜单、按评分规则判定最优商品、红线自动剔除、倒挂/拥挤自动过滤、接口匹配1688现货、采集、对账、勾选店铺、沿用模板、提交铺货、发布记录统计。
- **硬红线自动阻断（不发布，直接跳过该品）**：品牌侵权、动漫卡通/影视IP联名（Hello Kitty/迪士尼/漫威/宝可梦/奥特曼等，标题+主图双查）、液体/膏体/化工、电池/带电、食品/保健/医疗、宗教敏感、超重易碎、活物种苗、多规格组合品（卷材/管材/多尺寸类，SKU价差必超7倍）；规则见 selection-rules.md。命中或认不准的品跳过，不提交。
- **人工接管（Agent不得代做）**：ERP登录、短信/验证码、支付。

**接口使用约定（Step1/2 遨虾 + Step3-6 ERP）：**
- 只读命令（items/logs/shops）个人选品/对账、低频（脚本内置间隔：遨虾 ≥0.6s、ERP ≥1s），不批量抓取、不转售数据；collect/distribute 为写操作，仅对用户明确点名的 Step2 清单执行，不扩大范围。
- 接口无 Shopee 销量/GMV/评分/关键词趋势；1688月销是供给侧热度，不等于下游好卖，不得据此推断出单。
- ERP 接口复用浏览器登录态 JWT（`qnquerystring` 头 + `appType:3`），token 失效即重新导出或回退浏览器，不绕登录。
- 接口为未公开内部 mtop/HTTP、无SLA、前端改版会断；报错即回退浏览器兜底，不要反复硬刷。

## 执行前约定

- **接口取候选/采集/对账/铺货（Step1-6）**：Step1/2 先读 `references/api-candidates.md`、Step3-6 先读 `references/erp-api.md`，按脚本命令执行；只读命令不写、不提交、不转售，collect/distribute 仅对用户点名清单执行。
- **浏览器（各步兜底）**：始终先 `bu.snapshot()` / `bu.find()` 观察拿到 ref 再动作；导航或翻页后旧 ref 失效，必须重新观察。
- 所有 ERP 页面都是登录态 + 前端动态渲染。遇到 `blocked=auth`、跳转登录页、验证码，**立即** `interaction.request_action(type="browserControl")` 请用户接管，不要文本求登录、不要绕登录。
- 不存储、不输入任何账号密码；登录态由用户在浏览器里完成。
- 结算价模板（默认 `来源价×130% + 5.00 − 0.00`）由用户在ERP内预先配置，本流程沿用，不每次重算。

## 工作流（6步，标注自动化边界）

### Step 0 登录检查（人工接管，进入Step3前做即可）
- Step1/2 接口取候选匿名即可，不需要登录。到 Step3 进 ERP 前，导航快递助手ERP任意页面，若被重定向到登录页或 `blocked=auth`，调用 `interaction.request_action(type="browserControl")` 请用户登录；返回后重新 `bu.snapshot()` 验证登录态再继续。

### Step 1 接口拉榜单 + AI判定最优商品（全自动，不停下问人）
- 用 `scripts/aibuy_rank_client.py`：`sites` 选站点 → `tabs` 选榜（热销/飙升/新品）→ `categories` 逐层选类目(L1/L2/L3) → `items` 分页导出候选 CSV/JSON。命令与字段见 `references/api-candidates.md` 第2节。
- **榜单默认口径（新店/新账号，2026-10 更新）**：默认选 **飙升榜 `overseas_soaring_list` ＋ 新品榜 `overseas_new_product_list`**（抓刚起量的潜力款，避开已成红海的热销品）；热销榜 `overseas_hot_selling_list_v1` 仅作风向验证。用户明确要求跟热销时除外。
- **输入参数组（Step1 可选，缺省用默认口径，规则见 `references/selection-rules.md` 第七节）**：`--strategy newbie|volume|premium|custom`（默认 `newbie`，展开站点组合：新手=**MY+PH**、放量=ID+VN、精品=SG+TH/MY、自定义=用户站点列表）、`--market blue|red|balanced`（默认 `blue`：蓝海=飙升+新品、红海=热销+飙升、均衡=三榜合并）、`--price-band <客单价带>`、`--budget <数量/预算>`、`--cats <类目白名单>`、`--weight-max <kg>`（默认 1.0，轻小件优先）。用户显式指定参数即覆盖默认口径；未指定按第七节映射展开执行。站点/榜单/类目仍按脚本参数切换，策略只决定"拉哪些站点×榜单×类目的组合"。
- 站点/榜单/类目通过参数切换，不存在浏览器 `back` 丢状态问题；每榜封顶约500条，`cateId` 与 `cateLevel` 必须同层。
- **AI 自动执行筛选与打分（规则见 `references/selection-rules.md`），不向用户请求确认：**
  1. 按 rankId 去重；
  2. 硬红线自动剔除（品牌侵权、动漫/卡通/影视IP联名、液体化工、带电、食品保健医疗/宠物粮、宗教、易碎、活体），标题+主图双查，命中或认不准直接跳过；
  3. 自动剔除倒挂（下游人民币价 ≤ 1688同款中位价）、同款数≥3000 极度拥挤、平价微利；
  4. 按毛利空间（下游价/中位价倍数）、同款数适中区间、类目安全度打分，取最高分的 1 个（或按任务指定数量）进入 Step2；
  5. 在结果里记录选定理由（分数、关键数值），但不暂停等待人工拍板。

### Step 2 接口检索1688现货 + AI自动匹配（全自动，不停下问人）
- 对 Step1 选定的榜单品：`search --keyword`（标题抽核心词）与 `search-image --image-url`（用榜单 oppImageUrl）并行取1688候选，字段：offerId、起批价、1688月销、评分、起订量、供应商、标准offer链接。用法见 `references/api-candidates.md` 第3节。
- **AI 自动匹配，不取第一条：**先过IP/品牌红线（读offer标题+主图，命中知名卡通/影视IP或"正版/联名/授权"即跳过，认不准也跳）；再按同类核对（标题/图与榜单品同类）、月销降序、评分≥4.0、起订量低、现货优先打分，自动选 1 个最优 offer；无合格候选则跳过该榜单品并记录原因，不强行发。
- 记录标准格式URL：`https://detail.1688.com/offer/<offerId>.html`，累积成清单交给 Step3。
- 接口失效时回退 `references/browser-recipes.md` 第1/2节（浏览器切榜、点"找同款"提offer链接），匹配判定规则不变。

### Step 3 批量链接采集（接口优先，浏览器兜底）
- **接口（默认）**：Step2 清单即 offerId，直接提交 `python3 scripts/erp_api_client.py collect --ids <逗号分隔>`（或 `--ids-file <清单文件>`，每行一个，支持纯ID/CSV首列/1688链接；单批≤500自动分批）。输出「成功 X、失败 Y、跳过 Z」，对应页面"本次共采集N个"口径。命令见 `references/erp-api.md` 第3节。
- 失败的逐条核对 offerId（多为无效/已下架链接）后重试或剔除；**已采集过的 offerId 接口幂等算成功**，不会重复入库。
- **浏览器兜底**：接口报错/改版时进「商品采集-链接采集」页，textarea 粘贴URL（Enter换行，单次最多500），点"开始采集"，代码见 `references/browser-recipes.md` 第3节。

### Step 4 公共采集箱对账（接口优先，浏览器兜底）
- **接口（默认）**：`python3 scripts/erp_api_client.py items --size 100 --out ./erp_data`，或只查本次清单 `items --ids <本次货源ID逗号分隔>`；拿返回的 `platNumIid`(货源ID) 与 Step2 清单核对条数与ID一致；不一致先补齐/剔除再铺货。命令与字段见 `references/erp-api.md` 第3节。
- 采集箱内已存在的货源ID不重复粘贴、不重复采集。
- **浏览器兜底**：接口报错/改版时进「公共采集箱」核对，代码见 `references/browser-recipes.md` 第4节。**注意浏览器默认"未认领"筛选会隐藏已认领商品，先删筛选tag再查询。**

### Step 4.5 去重检查（接口优先，提交前最后一道）
对 Step2 清单逐个过两道去重，命中即从铺货清单剔除，不重复上架：
1. **ERP发布记录比对（接口优先）**：`python3 scripts/erp_api_client.py logs --months 3-6 --ids <本次货源ID逗号分隔>`（或全量 `--months 3-6`），取返回的全部历史货源ID（**任意状态**：发布成功/审核中/发布中/发布失败都视为已提交过；中间态也算占用，避免审核期误重发）。命中的剔除。命令见 `references/erp-api.md` 第3节；接口失效时回退 `references/browser-recipes.md` 第7节。
2. **本地已发台账比对**：`scripts/published_ledger.py check --ids <本次offerId逗号分隔> --ledger ./aibuy_data/published_offers.csv`，OCCUPIED 命中的剔除，只对 FREE 的继续。
3. **跨链接同款**：标题归一化（去规格/促销/品牌词）后近似、主图雷同、同款中位价接近的，只保留打分最高的1个，其余剔除。
- 两道都放行的清单才交给 Step5；提交成功后用 `published_ledger.py append` 把本次 offerId 写回台账。

### Step 4.6 标题清洗（接口直连，全自动，不暂停问人）
- **背景**：1688 货源标题常自带"跨境/外贸/亚马逊/ebay/速卖通/海外代购/原单尾单"等营销前缀。这些词在 Shopee 端有两个问题：①其他平台名（亚马逊/ebay 等）违反 Shopee《跨境卖家政策指引手册》1.1.1.4"关键词/品牌、属性滥用"，首次下架、再犯删除扣分；②"跨境/外贸"是中国卖家行话，本地买家从不搜，却堆在标题前 30 字符（吃 70% 搜索权重），把核心词挤出去。
- **接口（默认）**：对 Step4.5 放行的清单逐条清洗标题
  `python3 scripts/clean_title.py clean --num-iid <ERP内部ID>`（单条）
  或批量扫采集箱：`python3 scripts/clean_title.py clean-all --out ./erp_data`。
  自动剔除：平台名（亚马逊/Amazon/ebay/Etsy/wish/速卖通/AliExpress，任意位置）+ 行话前缀（跨境/外贸/出口/海外/原单/尾单/专供/代发，仅开头连续）；保留产品词（90L/大容量/材质/品类名）。
- **先 dry-run 看效果**：`--dry-run` 只显示不写入，确认清洗规则不误删产品词后再正式执行。
- **线上标题边界（重要）**：ERP 采集箱标题改干净后，**已发布到 Shopee 站点的线上标题不会自动同步**（distribute 是创建新任务不是更新已有商品）。已发布商品要改线上标题：在 Shopee 轻出海后台手动编辑（出单品再改，不值得为冗余词重铺）；Step4.6 清洗保证的是"新上架的品标题干净"，不追溯旧品。
- **批量清洗注意**：35 条以上批量跑时，queryDetailByNumIid 连续调用会触发后端静默限流（返回空 data）；脚本已内置 2s 间隔 + 失败自动重试 1 次，仍失败的条目用 `update_erp_item.py update --num-iid <ID> --erp-code <code> --title "<新标题>"` 独立进程补跑。

### Step 5 自动铺货提交（接口直连，全自动，不暂停问人）
- **接口（默认，写操作）**：对已通过 Step4.5 去重的货源ID清单直接提交
  `python3 scripts/erp_api_client.py distribute --ids <本次货源ID逗号分隔> --out ./erp_data`。
  命令内置：采集箱按货源ID取 `numIid`（铺货接口必须用 ERP 内部ID）→ 自动预查并默认选**首个有效轻出海商户店**（`shopType=SHOPEE_MERCHANT`，与浏览器弹窗默认一致）→ 构造 `distribItemVos` → 每批4个串行提交 `POST /item/distribute/batchPublish`。返回「已进入发布队列」即成功。
- 需要指定店铺时 `--shop <轻出海商户店sellerId>`；传普通站点授权店会警告（不参与轻出海铺货，任务不会正常发布）。店铺可用 `shops --platform shopees` 预查（输出含轻出海商户店数）。
- **提交前拦截自检（全自动，命中即剔除/重采/改配置/清洗标题，不提交）**：按 selection-rules 四附四道关卡执行——①选品价差预检（第一节第9条/第三节第4条，卷材/多尺寸/磅数分档类直接换品；标题含"可定制/印logo/刻字"的过四附关卡1可定制品三道检查——规格/模式/交付，定制驱动品跳过、能力标签品按标准款卖）；②采集后主图防盗链/404 检查（sorry 占位图、高度<32、404 先重采刷新再铺；**描述图接口取不到，此类失败后直接换同款，重采幂等不刷新**）；③库存沿用"使用商品来源"，不手填超界值；④标题清洗（Step4.6，剔除平台名+行话前缀）。实测近1个月35条失败中21条（60%，含图片伴生记录为71%）可在此拦下。
- 结算价模板、库存、发货方式沿用 ERP 已保存配置，不每次重算、不暂停确认（接口不传 `publishConfig` 即用默认）。
- **浏览器兜底**：接口报错/改版时进公共采集箱，只勾选本次清单商品行 → 点"铺货至Shopee轻出海" → 弹窗自动勾选首个轻出海店铺 → 沿用模板 → 点"开始铺货"，代码见 `references/browser-recipes.md` 第5节。仅当出现登录/验证码/支付弹窗时才转人工接管。

### Step 6 发布记录统计（接口优先，终态需等待）
- **接口（默认）**：`python3 scripts/erp_api_client.py logs --months 1 --out ./erp_data`，输出按货源ID逐条归类 + 状态分布 + 失败原因（`status`：success=发布成功、fail=发布失败、processing=发布中、examine=审核中）。统计口径见下；命令见 `references/erp-api.md` 第3节。
- **失败自动归因（推荐）**：`python3 scripts/erp_api_client.py logs --months 1 --advice --out ./erp_data`，失败记录自动对照 selection-rules 第五节归因库，附加「严重度/处理建议」列（整品失败=弃品换单规格、可重试=改后重提、单站点=忽略或补站点、撞红线=剔除）；未收录的抄录原文人工归因，CSV/JSON 同写。
- **失败处置策略（按归因级别处置，不要全部进编辑页改；Shopee 校验的是提交的规格/图片/库存数据，改 1688 原品无效，除非重采同步）**：整品失败（规格价差>7倍）→ 直接弃品换单规格offer，不编辑；图片防盗链/404 → 重采刷新即可，不是商品问题；规格结构缺漏（属性为空/层级超2层/映像错乱）→ 编辑采集箱商品规格后保存重提；单站点（层变体名重复）→ 可忽略或补该站点重提；原因为空 → 打开 ERP 发布记录页人工查该货源ID站点级状态再归因，勿盲目重提。判定细则见 selection-rules 第五节处置时机速查。
- **浏览器兜底**：接口报错/改版时进「Shopee轻出海-发布记录」按货源ID逐条归类，代码见 references/browser-recipes.md 第6节。
- 审核/上传为异步，现场等待不改变终态；记录初始快照，告知用户稍后刷新复核。
- 终态回来后用 `published_ledger.py status --ids <offerId> --status 发布成功/发布失败` 更新台账；发布失败的按归因库处理，不在台账里自动删除。

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
- `references/api-candidates.md`：Step1/2 只读接口说明、命令、字段、口径警告与回退方式。取候选前必读。
- `references/erp-api.md`：Step3-6 ERP 接口（采集提交/采集箱/发布记录/店铺/铺货提交）契约、token 维护、命令、已知坑与回退方式。采集/对账/去重/统计/店铺预查/铺货提交前必读。
- `references/selection-rules.md`：AI自动剔除的红线清单、Step1打分规则、Step2同类自动匹配规则、结算价说明、失败原因归因库、第七节=站点策略映射与输入参数组默认口径（--strategy/--market 等）。判定前必读。
- `references/browser-recipes.md`：bu 代码片段；第1/2节为遨虾接口失效兜底，第3-7节为 ERP 采集/对账/铺货/统计/去重比对兜底（Step3-6 默认走接口，接口失效时用），执行时复制并按当前页面调整。
- `scripts/aibuy_rank_client.py`：Step1/2 只读客户端（纯标准库）。
- `scripts/erp_api_client.py`：Step3-6 ERP 接口客户端（纯标准库，token 存 `scripts/erp_token.txt`；含 collect/distribute 写操作命令）。
- `scripts/update_erp_item.py`：采集箱商品编辑（query/update/batch 改标题；batch 读 csv: numIid,erpCode,new_title，内置限速+回读验证）。发布失败需改标题时用。
- `scripts/clean_title.py`：标题清洗（单条 clean / 批量 clean-all；自动剔除平台名亚马逊/ebay/速卖通等+行话前缀跨境/外贸/出口/原单等；支持 --dry-run；写回采集箱并回读验证）。Step4.6 用。
- `scripts/repair_erp_item.py`：发布失败商品结构修复（`--mode`：single_tier 规格层精简到1层并同步清 skuPropertyList / price_cap 删极端价格SKU压价差≤7倍 / fix_imgs 删宽高比超限图 / unify_pic 变体三图字段统一主图；`--keep-title` 防标题被原样回写）。失败归因处置按 selection-rules 第五节速查。
- `scripts/published_ledger.py`：Step4.5 本地已发台账（check/append/list，纯标准库）。
