# 快递助手ERP 接口直连（Step3/4/4.5/5/6 用）

> 配套脚本：`scripts/erp_api_client.py`（纯标准库，无需安装依赖）。
> 用途：链接采集提交（Step3）、公共采集箱对账（Step4）、发布记录去重比对（Step4.5）、发布记录统计（Step6）、店铺预查+铺货提交（Step5）全部从「浏览器点击」改为接口直连，更快更准。
> Step5 铺货提交走 `distribute` 命令（写操作，接口直连实测成功）；浏览器仅作兜底（`browser-recipes.md` 第5节）。

## 0. 合规与边界（先读）

- **只读命令**（items/logs/shops）：只做查询，不提交、不铺货、不删除。
- **写操作命令**（collect/distribute）：仅对用户明确点名的清单执行——collect 采集 Step2 的 offerId 清单（原 Step3 链接采集）、distribute 把采集箱内已确认的商品铺到轻出海商户店（原 Step5）；不扩大范围、不批量抓取、不转售；提交前确认清单本身是用户要铺的品。
- **登录态**：接口复用浏览器登录后的 JWT token，不绕登录、不输账号密码；token 失效即提示重新导出或回退浏览器。
- **低频**：客户端内置 ≥1s 请求间隔；实测快速连续请求会触发限流（errorCode 707），拉历史按月循环时天然低频。
- **无 SLA**：接口为未公开内部接口，前端改版会断；报错即回退 `browser-recipes.md` 对应浏览器流程，不反复硬刷。
- **口径**：发布记录 = 已在 ERP 提交过的货源ID（任意状态都算已提交，中间态也算占用），与 SKILL Step4.5 口径一致。

## 1. token 获取与维护

接口认证只需一个请求头：`qnquerystring: <JWT>`。登录后同一 JWT 写在三处（值相同）：
`sessionStorage.qnquerystring` / `localStorage.templateUserToken` / Cookie `templateUserToken`。

**导出（浏览器登录态内，`mac_computer_use_tool(plane="bu")` cell）：**

```python
import aha_browser_use as bu
print(bu.js("(function(){return sessionStorage.getItem('qnquerystring')||localStorage.getItem('templateUserToken')||'';})()"))
```

把输出存到 `scripts/erp_token.txt`（一行），或：
```bash
python3 scripts/erp_api_client.py token set --token <token>   # 保存
python3 scripts/erp_api_client.py token check                 # 校验有效性
```

- 失效表现：`errorCode=703`（token 缺失/失效）→ 重新进 ERP 页面，重新导出 token 覆盖 `erp_token.txt`。
- 也可用环境变量 `ERP_TOKEN` 临时注入，优先级：`--token` > `ERP_TOKEN` > `erp_token.txt`。

## 2. 接口契约（curl 直连实测）

所有接口同源 `https://erp.kuaidizs.cn`，POST JSON。
**必带头**：`Content-Type: application/json;charset=UTF-8`、`qnquerystring: <JWT>`、`appType: 3`。

> **坑① appType:3 必带**：`appType` 把请求切到跨境/轻出海数据域。缺它采集箱/发布记录接口返回**空 list**（`total=0`）但 `success=true`，不易察觉。
> 不需要 Cookie、无请求签名、无 CSRF token。

| 用途 | 路径 | 必带 body 字段 | 备注 |
|---|---|---|---|
| 采集提交（写） | `POST /item/center/batchPluginCollectItem` | `itemIdList:[offerId...]` | **写操作**；单批≤500，已存在ID幂等算成功，无效ID计fail |
| 采集箱列表 | `POST /item/center/queryErpItemListPage` | `pageNo`(从1起) `pageSize`(≤100) | 可选筛选见下 |
| 发布记录 | `POST /item/distribute/queryLogs` | `pageNo` `pageSize` `startTime` `endTime`(`YYYY-MM-DD HH:mm:ss`) `fromPlatformList` `toPlatformList` | **时间间隔≤1个月**，缺时间报"时间不能为空" |
| 店铺列表 | `POST /index/platformShop/getPlatformShops` | `pageNo` `pageSize`；`platform`(可选，轻出海=`shopees`) | 本账号 16 家，其中有效授权 8 家、轻出海商户店 1 家 |
| 铺货提交（写） | `POST /item/distribute/batchPublish` | `distribItemVos` `distributionTotalNum` `publishConfig`(可选) | **写操作**；商品用 `numIid`(ERP内部ID)，目标必须是轻出海商户店；每批≤4个 |
| 店铺铺货配置 | `POST /item/distribute/getPlatformShopPuhuoSetting` | `shopId` `platform` | 弹窗打开时按店查询（单店） |
| 店铺铺货配置(列表) | `POST /item/distribute/getPlatformShopPuhuoSettingList` | `shopIdList` `platform`(按源码推断) | 点「开始铺货」时查询（多店）；实际调用已实测成功 |
| 商品类目树 | `POST /item/distribute/categoryTree` | `platform` `sellerId`(可选 `parentCategory`/`cName`) | 弹窗打开时加载，类目确认用 |
| 发布额度 | `GET /trade/crossItemDistrib/quotaQuery` | `?` 参数 | 弹窗显示"本月已用137/6000"来源 |

**batchPublish body 结构（从前端源码反推 + curl 实测，最小编 body 即成功）：**
```json
{
  "distribItemVos": [{
    "itemId": "<采集箱商品 numIid>",
    "sourcePlatform": "kdzs_erp",
    "targetPlatform": "shopees",
    "sourceSellerId": "",
    "targetSellerId": "<轻出海商户店 sellerId>",
    "targetSellerNick": "<店铺名>",
    "categoryIds": [],
    "categoryNames": []
  }],
  "distributionTotalNum": 1
}
```
- `publishConfig` 可选（`{weight, weightSet, packageLength, packageWidth, packageHeight, packageSet}`，来自「铺货设置」弹窗表单；不传则用 ERP 已保存默认）。
- 每批 4 个（前端 `slice(4)` 循环 + Promise.all 并发；**客户端串行分批**，避免触发 707 限流）。
- 提交成功返回 `{"data":null,"success":true}`，任务异步进入发布队列，终态用 queryLogs 查。

**queryErpItemListPage 可选筛选**：`claimPlatformList:[""]`(只看未认领)、`platNumIidList:[货源ID...]`、`title`、`operatorIdList`、`multiShopS:[{platform,sellerId}]`、`gmtCreatedStart/End`、`itemIds`(逗号分隔)。

**queryLogs 关键入参**：
- `fromPlatformList:["1688"]` + `toPlatformList:["shopees"]` = Shopee轻出海发布记录（`shopees` 是轻出海平台码，实测）。
- `status`：`success` 发布成功 / `fail` 发布失败 / `processing` 发布中 / `examine` 审核中（可选过滤）。
- `fromItemIdList:[货源ID...]`：按货源ID筛（**源商品ID用这个**）；`toItemIdList` 是 Shopee 侧产品ID，别用错——实测 from 命中、to 返回 0。
- 时间窗口最大 31 天（实测 `code=200, msg=查询时间间隔不能大于一个月`），拉更长历史必须按月循环。

**返回字段（关键）**：

queryErpItemListPage.list[]：`platNumIid`(货源ID=1688 offerId)、`numIid`(ERP内部ID)、`erpCode`、`title`、`priceLow/priceTop`、`sourceName`、`claimStatus`、`claimPlatformList`、`gmtCreated`、`itemSourceLinks[].sourceLink`(1688链接)、`picUrl`。

queryLogs.list[]：`status`(success/fail/processing/examine)、`itemId`(货源ID)、`title`/`fromTitle`、`createTime`(发布时间)、`platform`(=shopees)、`shopName`、`errorMessage`(失败原因全文，如"规格之间价格比例不能大于7倍")、`extInfo.ITEM_SOURCE_NUM_IID`、`sitePublishStatusList[]`(站点级状态：status=SUCCESS/FAILED/DRAFT/PENDING_ASYNC + siteCode + failReason)、`taskId`。

getPlatformShops.list[]（Step5 店铺预查）：`platform`(=shopees)、`sellerId`(卖家ID)、`sellerNick`/`sellerAbbreviation`(店铺名，格式「商户名-店铺名-站点」，如 `...-示例店铺-PH`)、`shopType`(店铺类型，**`SHOPEE_MERCHANT`=轻出海商户店**)、`extendInfo.region`(站点，PH/TW/BR/MX/MY/TH/VN…)、`status`(店铺状态 1=正常)、`tokenStatus`(授权token状态 1=有效)、`enableStatus`(启用 1)、`tokenExpireTime`(授权过期时间，每日滚动续期)、`id`(店铺记录ID)、`memberId`、`authTime`/`bindTime`。
> **预查关键①**：`status=1 且 tokenStatus=1 且 enableStatus=1` 才算「有效授权」店铺。实测 16 家中 8 家有效、8 家异常（另一商户的店铺授权未生效）——铺货前不预查就可能勾到异常店铺导致提交失败。
> **预查关键②（铺货目标必须是轻出海商户店）**：弹窗只显示 `shopType=SHOPEE_MERCHANT` 的店铺（本账号 1 家：「商户 - 示例店名」，sellerId=123456789012345）。带站点后缀的普通授权店（`...-示例店铺-PH` 等）**不参与轻出海铺货**，distribute 默认不会选它们。

## 3. 命令用法

```bash
SK=scripts/erp_api_client.py
# Step3 批量链接采集（写操作）：提交 Step2 的 offerId 清单
python3 $SK collect --ids 932606971652,927948469867 --out ./erp_data
# 或从清单文件读（每行一个；支持纯ID / CSV首列 / 1688链接）
python3 $SK collect --ids-file ./aibuy_data/step2_picks.txt --out ./erp_data

# Step4 公共采集箱对账：全量拉取，与 Step2 清单比对货源ID
python3 $SK items --size 100 --out ./erp_data
# 或只查本次清单的货源ID是否在采集箱
python3 $SK items --ids 932606971652,927948469867 --out ./erp_data

# Step4.5 发布记录去重：拉最近 3-6 个月全部已提交货源ID（任意状态），与候选清单比对
python3 $SK logs --months 3 --out ./erp_data
# 或只查本次候选清单是否已提交过
python3 $SK logs --months 6 --ids 932606971652,927948469867 --out ./erp_data

# Step6 发布记录统计：状态分布 + 失败原因（输出即按 SKILL 口径，中间态不计成功）
python3 $SK logs --months 1 --out ./erp_data
# Step6 失败自动归因（推荐）：失败记录对照 selection-rules 第五节归因库，附加严重度/处理建议列
python3 $SK logs --months 1 --advice --out ./erp_data
#   归因分级：整品失败(弃品换单规格) / 可重试(改后重提) / 单站点(忽略或补站点) / 撞红线(剔除) / 未收录/未知(人工判断)

# Step5 铺货提交（写操作）：采集箱商品 → 轻出海商户店（接口直连，自动选首个商户店）
python3 $SK distribute --ids 932606971652,927948469867 --out ./erp_data
# 指定店铺（--shop 传轻出海商户店 sellerId；传非商户店会警告）
python3 $SK distribute --ids 932606971652 --shop 123456789012345 --out ./erp_data

# Step5 选店铺辅助（只读查询，铺货目标预查）
python3 $SK shops --platform shopees --out ./erp_data
# 输出含预查结论：有效授权店铺数 + 轻出海商户店数 + 默认将勾选的首个商户店；无商户店会明确警告

# Step4.6 标题清洗（写操作，基于 queryDetailByNumIid + updateErpItemByNumIid）
python3 scripts/clean_title.py clean --num-iid <ERP内部ID>           # 单条清洗
python3 scripts/clean_title.py clean --num-iid <ID> --dry-run        # 只看不写
python3 scripts/clean_title.py clean-all --size 100 --out ./erp_data # 批量扫采集箱
# 自动剔除：平台名（亚马逊/Amazon/ebay/Etsy/wish/速卖通/AliExpress）+ 行话前缀（跨境/外贸/出口/海外/原单/尾单/专供/代发）
# 保留产品词；标题无变化则跳过；写回后自动回读验证
```

输出：`--out` 目录下 `collect_result.csv/json`、`shared_goods.csv/json`、`publish_logs.csv/json`、`shops.csv/json`、`distribute_result.csv/json`（UTF-8 带 BOM，Excel 直接打开）。

**collect 命令内置行为（写操作，谨慎）**：
- 入参去重保序；单批 ≤500 自动分批（与页面"每次最多采集500个"口径一致）；
- 返回汇总：成功/失败/跳过 + 跳过原因统计，对应页面"本次共采集N个，成功X、失败Y"；
- 已采集过的 offerId 幂等（重复提交算成功，不重复入库）；无效/已下架 ID 计 fail，需核对后重试或剔除。

**distribute 命令内置行为（写操作，谨慎）**：
- 自动完成「items 按货源ID取 numIid → shops 取首个轻出海商户店 → 构造 distribItemVos → 每批4个串行提交 batchPublish」；
- 默认目标 = 首个有效轻出海商户店（与浏览器弹窗默认一致）；`--shop` 可指定，非商户店会警告但允许（风险自负）；
- 清单里不在采集箱的货源ID会直接报错退出（先 collect 再 distribute）；
- 提交即真实进入发布队列（异步终态），用 logs 查结果——**失败原因也随 logs 返回**（如"规格之间价格比例不能大于7倍"）。

**logs 命令内置行为**：
- 按月循环拉取（`--months N`），窗口间自动留 ≥1s 间隔；
- 跨窗口去重（货源ID+任务ID+发布时间 相同只留一条）；
- 末尾打印状态分布，与 SKILL「状态口径」表一致：`success` 计入成功，`fail` 记原因，`processing/examine` 为中间态不计。
- **失败原因提取**：`errorMessage` 为空时自动合并 `extInfo.sitePublishStatusList[].failReason`（站点级原因）；仍为空则归因标注「未知」并提示查页面。
- **`--advice` 归因**：失败记录对照内置于客户端的归因库（与 selection-rules.md 第五节同步），附加「严重度/处理建议」列，按严重度汇总；规则表在客户端 `_ADVICE_RULES`（顺序=优先级，含：规格价差>7倍→整品失败弃品、规格/层变体名重复→单站点改唯一重提、tier_variations超2层→删层级重提、库存超界/规格属性为空→可重试、sorry图/404→重采、类目/品牌→撞红线剔除、10004→可忽略等）。新增真实失败原因时按此表结构扩展。

## 4. 已知坑清单

1. **appType:3 必带**（缺失返回空 list 而非报错）。
2. **时间间隔 ≤1个月**（拉历史按月循环）。
3. **707 限流**：连续快请求触发"操作过于频繁"；客户端已内置 1s 间隔，仍触发说明有其他调用方，等 10s+ 再试。
4. **703 token 失效**：重新导出 token。测试 token 的 `exp` 是 2026-10-31 左右，过期后必须重新导出（从 sessionStorage/localStorage/Cookie）。
5. **未认领筛选坑（与浏览器一致）**：`claimPlatformList:[""]` 会隐藏已认领商品；对账用全量，别加未认领筛选。
6. **status 值不要混**：接口是 `success/fail/processing/examine`，页面中文是"发布成功/发布失败/发布中/审核中"；浏览器兜底段读的是中文，接口段读的是英文，两边统计口径换算时注意。
7. **发布记录不是永久全量**：受查询窗口限制（≤31天/次），去重比对建议 `--months 3-6`；更早的记录 ERP 页面也看不到，属正常。
8. **采集提交传 offerId 不传 URL**：`batchPluginCollectItem` 的 body 是 `itemIdList`（1688 offerId），不是链接；传 URL 会报"采集商品Id列表不能为空"。已存在的 ID 幂等算成功。
9. **collect 是写操作**：提交即入库采集箱，不可撤回（可在采集箱删除）；只提交用户点名要采集的清单，失败项（无效/下架 ID）逐条核对再重试，不要盲目重发。
10. **铺货提交用 numIid 不是货源ID**：`batchPublish` 的 `distribItemVos[].itemId` 必须是采集箱商品的 `numIid`（ERP内部ID，17位长），传货源ID（platNumIid，12位）会导致找不到商品；客户端 distribute 内部自动从 items 接口映射。
11. **铺货目标必须是轻出海商户店**：`targetSellerId` 传普通站点授权店（无 `shopType=SHOPEE_MERCHANT`）虽能提交成功，但目标店铺不参与轻出海铺货，任务不会正常发布；弹窗只显示商户店，客户端默认也只选商户店。
12. **每批 ≤4 个 + 串行**：前端每批4个并发提交；客户端改为串行分批，避免 707 限流。批量铺货（>4个）会自动分批，勿手拆。
13. **distribute 是写操作且不可撤回**：提交即创建发布任务（会真实占用发布额度 137/6000）。只对已通过 Step4.5 去重、确认要铺的清单执行；失败原因通过 logs 回查（多为商品本身问题，如 SKU 价差>7倍、类目不符），不是接口问题。
14. **`success` 也可能带"目标平台店铺商品编码已存在 已自动填充源商品ID为商品编码"附注**：这是 ERP 检测到编码占位后自动填充复用，**不是失败**，按 success 计。真正失败的是带"1、此资料编码在此卖家内已存在,请修改后再提交"前缀的双重冲突记录。
15. **"此资料编码在此卖家内已存在"（重铺撞残留，2026-10 实测）**：同一商品多次铺货（含失败）后 Shopee 侧已占位该编码。处理：先查该货源ID历史 logs 是否有 success（有则已上架不用再铺）；仅残留则用 `updateErpItemByNumIid` 改 `erpCode` 加后缀（`<offerId>-2/-3`）轮换后再 distribute；**每个新编码提交失败也会再次占位，轮换不能无限**，最终需在 Shopee 轻出海后台清理残留。同一批次务必先修完结构（repair_erp_item.py）再换码，避免结构好了但码已被上次失败占用。
16. **collect 后 SKU=0 的品要换款**：详情接口 `skus=[]` 的单规格款提交必报"商品规格属性不能为空"；采集后先验证 SKU>0 再铺货（有属性 SKU ≥1 即可，如"静电除尘干巾-100片"单 SKU 可过）。
17. **queryDetailByNumIid 连续调用限流（2026-10-29 实测）**：同进程内连续两次 queryDetail（如 clean_title.py 先 query 算标题、update 里又 query 拉 dto）即使间隔 1s，后端也可能返回空 data（非 707，是静默空响应）。**对策**：①复用已拉到的 dto 传给 update，不重复 query；②批量模式间隔 ≥2s；③update 失败自动等 3s 重试 1 次；④仍失败则用 `update_erp_item.py update` 独立进程跑（无连续调用包袱）。
18. **改 ERP 采集箱标题 ≠ 改 Shopee 线上标题（2026-10-29 实测）**：`updateErpItemByNumIid` 只改采集箱内的货源标题，已发布到 Shopee 站点的线上商品标题不会自动同步。distribute 是"创建新发布任务"不是"更新已有商品"。已发布商品要改线上标题：①在 Shopee 轻出海后台手动编辑（推荐，出单品再改）；②换 erpCode 后缀重新铺货（创建新商品，旧品仍在，会重复，不推荐）。新铺货商品从采集箱取标题，所以 Step4.6 清洗保证的是"新上架的品标题干净"。

## 5. 回退

接口报错/改版/风控（703/707/非JSON/网络异常）时，对应步骤回退浏览器：
- Step3 → `browser-recipes.md` 第3节（链接采集页粘贴URL）
- Step4 → `browser-recipes.md` 第4节（公共采集箱对账）
- Step4.5 → `browser-recipes.md` 第7节（发布记录去重比对）
- Step5 → `browser-recipes.md` 第5节（勾选商品+店铺+开始铺货）
- Step6 → `browser-recipes.md` 第6节（发布记录统计）
