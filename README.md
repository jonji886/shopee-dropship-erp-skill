# Shopee Dropship ERP Skill

面向 **Shopee 轻出海** 铺货的 AI Agent 技能（Skill）：只读接口拉 1688 遨虾（aibuy）Shopee 区域榜单 → AI 按评分规则自动判定最优商品 → 接口关键词/图搜自动匹配 1688 现货 → **快递助手 ERP 跨境版接口直连**链接采集 → 公共采集箱接口对账 → 接口自动铺货至 Shopee 轻出海 → 发布记录接口统计与失败自动归因。

**全链路接口化架构（Step1-6 默认全部走接口，浏览器仅兜底）**：
- **Step1/2 取候选（遨虾只读接口）**：`scripts/aibuy_rank_client.py` 匿名拉遨虾榜单、检索 1688 现货，导出候选清单；个人只读、低频（≥0.6s 间隔）、不转售。
- **Step3-6 ERP 接口直连**：`scripts/erp_api_client.py` 直连快递助手 ERP 后台接口，完成 链接采集提交（collect）、公共采集箱对账（items）、发布记录去重与统计（logs）、店铺预查与铺货提交（shops + distribute）；认证复用浏览器登录态 JWT（`qnquerystring` 头 + `appType:3`），比浏览器点击更快更准，且失败原因可自动对照归因库（logs --advice）。
- **浏览器兜底**：接口失效/改版/风控时，回退 `references/browser-recipes.md` 对应节（受控浏览器 `aha_browser_use` / `bu`），不绕登录、不写账号密码。

> 说明：Shopee 轻出海是平台代运营、卖家只供货的模式。工具链（选品→采集→铺货）可以跑通，但**铺完 ≠ 快速出单**，出单取决于平台选品与运营；本 Skill 的价值是把供货侧动作标准化并测量发布成功率。接口给的是遨虾前端同源快照（无 Shopee 销量/GMV/评分/趋势），1688 月销是供给侧热度，不得据此推断下游好卖。

## 适用范围（模式绑定）

**本 Skill 仅适用于一种模式：`快递助手 ERP 跨境版（erp.kuaidizs.cn）+ Shopee 轻出海（平台代运营、卖家供货）`。**

- **适用**：接口拉遨虾榜单 → AI 自动判定最优 → 接口检索 1688 现货自动匹配 → ERP 接口链接采集 → 公共采集箱接口对账 → 接口自动铺货至 Shopee 轻出海 → 发布记录接口统计成功率。
- **不适用**（页面/URL/选择器/接口不同会失效，不得直接套用）：
  - 其他 ERP（甩手、芒果店长、店小秘等）；
  - Shopee 自营店铺直接上架（非轻出海代运营模式）；
  - 其他平台铺货（Lazada、TikTok Shop、Amazon 等）。

所有 URL、选择器、接口参数、结算价模板、成功率口径、失败归因均基于该模式实测；换模式需重做链路适配，不能只改参数。

## 流程（6 步，接口直连）

1. **接口拉榜单 + AI 判定最优**（全自动）：`aibuy_rank_client.py` 按站点/榜单/类目拉候选，AI 按红线剔除 → 倒挂/拥挤/平价微利过滤 → 毛利空间/同款数/类目安全打分，取最高分进入下一步，不暂停问人。**默认口径（新店/新账号）**：飙升榜+新品榜（蓝海，避开红海热销）；`--strategy newbie` 默认展开 MY+PH 两站（规则见 selection-rules.md 第七节），可 `--strategy volume|premium|custom --market blue|red|balanced` 覆盖。
2. **接口检索 1688 现货 + AI 自动匹配**（全自动）：关键词搜 + 图搜并行取候选，AI 按同类硬过滤 → 评分/月销/起订量资格线 → 自动选 1 个最优 offer；无合格候选跳过并记录原因。接口失效时回退浏览器"找同款"兜底。
3. **批量链接采集（接口直连）**：`erp_api_client.py collect --ids <offerId清单>` 直接提交采集（`POST /item/center/batchPluginCollectItem`），返回成功/失败/跳过数；已采集过的 ID 幂等算成功。
4. **公共采集箱对账（接口直连）**：`erp_api_client.py items --ids <货源ID>` 核对条数与货源 ID，拿 `platNumIid`（货源ID）与 `numIid`（ERP 内部 ID）映射。
5. **去重 + 标题清洗 + 铺货提交（接口直连）**：`logs --months 3-6` 做发布记录去重（任意状态算占用）→ 本地台账去重（`published_ledger.py`）→ **Step4.6 标题清洗**（`clean_title.py`，剔除平台名/跨境行话前缀，防违规扣分+保搜索权重）→ `distribute --ids <货源ID>` 铺货提交（`POST /item/distribute/batchPublish`，自动映射 numIid、预查并默认选中轻出海商户店 `shopType=SHOPEE_MERCHANT`、每批 4 个串行提交）。**提交前四道拦截自检**（选品价差/主图防盗链/库存来源/标题清洗，实测拦下 60%+ 失败）。仅登录/验证码/支付由用户接管。
6. **发布记录统计 + 失败自动归因（接口直连）**：`erp_api_client.py logs --months 1 --advice` 输出 发布中/审核中（中间态）/发布成功/发布失败，失败记录自动对照归因库（selection-rules.md 第五节）附加「严重度/处理建议」（整品失败=弃品换单规格、可重试=改后重提或 `repair_erp_item.py` 修复结构、单站点=忽略或补站点、撞红线=剔除）。

## 自动化边界

| 环节 | 方式 |
|---|---|
| 拉榜单、打分判定、匹配现货、采集、对账、去重、铺货、统计、失败归因 | **AI 全自动**（不停下问人） |
| 硬红线（品牌侵权/液体化工/带电/食品保健医疗/宗教/易碎/活体） | **AI 自动阻断**，命中或拿不准即跳过不发布 |
| ERP 登录、短信/验证码、支付 | **人工接管** |
| collect / distribute 写操作 | 仅对用户明确点名的 Step2 清单执行，不扩大范围 |

## 状态口径（不可混算）

| 状态 | 性质 | 计入成功 |
|---|---|---|
| 发布中 / 审核中 / 排队中 | 中间态 | 否 |
| 发布成功 | 终态 | 是 |
| 发布失败 | 终态 | 否（记录原因并自动归因） |

- 提交成功率 ≠ 最终发布成功率 ≠ 出单，三个口径分开记录。

## 目录

```
shopee-dropship-erp-skill/
├── SKILL.md                          # 主流程、接口化架构、自动化边界、状态口径
├── scripts/
│   ├── aibuy_rank_client.py          # Step1/2 遨虾只读 mtop 客户端（纯标准库）
│   ├── erp_api_client.py             # Step3-6 ERP 接口客户端：token/items/logs/shops/collect/distribute（含 --advice 归因）
│   ├── clean_title.py                # Step4.6 标题清洗：剔除平台名+跨境行话前缀（clean/clean-all，支持 --dry-run）
│   ├── repair_erp_item.py            # 发布失败商品结构修复（single_tier/price_cap/fix_imgs/unify_pic）
│   ├── update_erp_item.py            # 采集箱商品编辑（query/update/batch 改标题，内置限速+回读验证）
│   └── published_ledger.py           # Step4.5 本地已发台账（check/append/list）
└── references/
    ├── api-candidates.md             # 遨虾接口族、命令、字段口径、限制与回退方式（含站点类目树独立要点）
    ├── erp-api.md                    # ERP 接口契约（含 batchPublish/归因/标题清洗）、token 维护、已知坑
    ├── selection-rules.md            # 红线、AI 过滤项、Step1 打分、Step2 自动匹配、四附拦截自检、失败归因库、站点策略映射
    └── browser-recipes.md            # bu 片段（第1/2节遨虾兜底，第3-7节 ERP 兜底）
```

## 运行要求

- Python 3（纯标准库，无需 pip 安装）。
- ERP 接口认证：登录快递助手 ERP 后导出 JWT 存到 `scripts/erp_token.txt`（一行），客户端自动读取；失效（703）重新导出覆盖。**该文件已在 .gitignore 中，不会随仓库外泄**。
- 受控浏览器环境（`mac_computer_use_tool` + `plane="bu"` + `aha_browser_use`）仅在接口失效兜底时使用。
- 已登录快递助手 ERP（登录由用户接管，本 Skill 不含、不请求任何账号凭据）。
- ERP 内已配置结算价模板（默认 `来源价×130% + 5.00 − 0.00`）。

## 已知局限（正式放量前优化）

- 固定 +5 元不随重量变化，重货会亏；高价品 30% 比例偏重。建议按重量分档、设保本地板，并用真实结算账单回填校准。
- 接口为未公开内部 mtop/HTTP、无 SLA，前端改版会断；报错即回退浏览器兜底，不要反复硬刷。
- ERP 接口低频约定：客户端内置 ≥1s 间隔，实测并发/快速连续请求会触发限流（707）。
- 铺货目标必须是轻出海商户店（`shopType=SHOPEE_MERCHANT`）；普通站点授权店不参与轻出海铺货，提交会失败。
- 选择器为实测值，页面改版会失效；兜底时按 SKILL.md 指引改用文本 `find` 重新定位。
