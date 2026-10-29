# Step1/2 只读接口取候选（mtop 轻客户端）

> 配套脚本：`scripts/aibuy_rank_client.py`（纯标准库，免登录、免付费 key，仅做 mtop token 握手）。
> 仅用于个人选品浏览与候选整理；低频（内置 ≥0.6s 间隔）、不转售。接口为未公开内部 mtop，无 SLA，前端改版会断，失效时回退 `browser-recipes.md` 的浏览器兜底流程。

## 0. 合规与边界（先读）

- 只读、个人用、低频；**不要**批量抓取、不要转售数据。
- 接口给的是**遨虾前端同源快照**，不是 Shopee 站内全量：无 Shopee 销量件数/GMV/评分/收藏/关键词搜索量/历史趋势。
- `monthSold`（检索接口）是 **1688 供给侧月销**，不是 Shopee 销量，不得用来推断下游好卖。
- `matchItmMedPrice` 是 1688 同款**中位价**，不是网页卡片的"站内平均售价"，口径不同，不要直接等同。
- 红线判定（含品牌侵权、动漫/卡通/影视IP联名，标题+主图双查）、同类匹配、倒挂/拥挤复核、打分选最优均由 AI 按 selection-rules.md 自动执行，脚本只负责取数不判定；拿不准的品（尤其IP形象认不准）跳过不发。

## 1. 接口族（匿名可读，appKey=12574478，标准 mtop sign 握手）

公共 body：`bizType=ERP, customerId=kdzhushou, language=zh, currency=CNY, version=v2`（缺 version=v2 会报 F9998/P0001）。

| 用途 | api 后缀 | 关键入参 |
|---|---|---|
| 平台列表 | `opprank.platformlist` | 无 |
| 站点列表 | `opprank.countrylist` | `platformCode` |
| 榜单列表 | `opprank.tablist` | `platformCode, siteCode` |
| 类目树(三层) | `opprank.categorylist` | `platformCode,siteCode,tabCode,cateId,cateLevel(1/2/3)` |
| 榜单商品 | `opprank.getitemlist` | `platformCode,siteCode,tabCode,cateId,cateLevel,pageNo,pageSize=50` |
| 1688关键词搜 | `crossBorder.lp.keywordSearch` | `searchParam={keyword,beginPage,pageSize}` |
| 以图搜款 | `crossBorder.lp.imageSearch` | `searchParam={imageAddress:榜单图URL,beginPage,pageSize}` |

- platformCode：`Shopee_ZX`（SG/BR/MY/VN/TW/ID/PH/MX/TH）、`TikTok_XS`、`Amazon_XS`（仅作风向参考，非本链路铺货平台）。
- tabCode：`overseas_hot_selling_list_v1` 热销、`overseas_soaring_list` 飙升、`overseas_new_product_list` 新品。
- **默认口径（新店/新账号，2026-10 更新）**：候选优先 `overseas_soaring_list`（飙升）＋ `overseas_new_product_list`（新品），抓"刚起量"品、避开红海；热销榜仅作风向验证。用户明确要求跟热销时例外。
- **站点默认口径（--strategy 展开，规则见 selection-rules.md 第七节）**：`--strategy newbie` 默认展开为 **MY + PH** 两站（新手练手：均衡稳 + 低门槛高潜）；`volume`=ID+VN、`premium`=SG+TH/MY、`custom`=用户站点列表；`--market blue|red|balanced` 决定榜单组合（blue=飙升+新品、red=热销+飙升、balanced=三榜合并）。用户显式传 `--site` 指定站点时以用户为准，不套策略映射。
- 限制：每榜 total 封顶约 500；pageSize=50 可用、=100 返回空；必须先选类目；`cateId` 与 `cateLevel` 必须同层，错层返回成功但 0 条；检索 totalRecords 封顶约 2000。

## 2. Step1 拉榜单 + AI自动判定最优（自动取数，自动打分）

```bash
SK=scripts/aibuy_rank_client.py
# 站点/榜单/类目逐层确定
python3 $SK sites
python3 $SK tabs --platform Shopee_ZX --site MY
python3 $SK categories --platform Shopee_ZX --site MY --tab overseas_soaring_list
python3 $SK categories --platform Shopee_ZX --site MY --tab overseas_soaring_list --level 2 --parent <一级ID>
# 拉取（--pages 最多10页≈500条；--cate-level 与 --cate-id 同层）
python3 $SK items --platform Shopee_ZX --site MY --tab overseas_soaring_list \
    --cate-id <类目ID> --cate-level 1 --pages 5 --out ./aibuy_data
```

输出 CSV 列：排名、榜单、站点、标题、币种、下游标价、下游人民币价、1688同款数、1688同款中位价、三级类目、图片、下游链接（Shopee 为空）、rankId。

AI 自动过滤+打分（对照 selection-rules.md 第一节红线、第二节过滤与打分）：
1. 按 `rankId/oppItemId` 去重；先剔红线（品牌侵权、动漫/卡通/影视IP联名、液体膏体/带电/食品保健医疗/宠物粮/宗教/超重易碎/活体），标题+主图双查，拿不准直接跳过。
2. 倒挂：`oppRmbPrice` ≤ `matchItmMedPrice` → 毛利为负，剔除。
3. `matchItmCnt` ≥ 3000 极度拥挤 → 剔除；下游价/中位价 < 1.10 平价微利 → 剔除。
4. 剩余按毛利空间倍数、同款数100–1500区间、类目安全、榜内排名打分，取最高分进入 Step2，记录分数与理由，不暂停问人。

## 3. Step2 取1688现货 + AI自动匹配（自动取数，自动选最优）

对 Step1 选定的榜单品，二选一或并用：

```bash
# 关键词：从榜单标题抽核心词（去掉站点前缀、促销词）
python3 $SK search --keyword "adhesive hook" --pages 2 --out ./aibuy_data
# 图搜：直接用榜单行的 oppImageUrl
python3 $SK search-image --image-url "<oppImageUrl>" --pages 1 --out ./aibuy_data
```

输出 CSV 列：offerId、标题、起批价、1688月销、评分、起订量、供应商、源头工厂、标准offer链接、图片。

**AI 自动匹配规则（禁止盲取第一条，结果必混入无关品）：**
0. **IP/品牌一票否决**：读 offer 标题+主图，命中知名动漫/卡通/影视IP（Hello Kitty/迪士尼/漫威/宝可梦/奥特曼等）、"正版/联名/授权"字样，或主图出现知名角色印花，直接跳过；认不准是否IP也跳过。
1. 同类硬过滤：标题/图与榜单品同类（毛巾对毛巾、胶带对胶带），不匹配跳过。
2. 资格线：`compositeScore` ≥ 4.0；月销 `monthSold` 高、源头工厂/现货、起订量低优先；同款最低价明显偏离品类的不选。
3. 在合格候选里按月销降序+评分+价格综合打分，自动选 1 个最优 offer；无合格候选则跳过该榜单品并记录原因。
4. 记录标准 URL：`https://detail.1688.com/offer/<offerId>.html`，累积成清单交给 Step3。

## 4. 回退

接口报错/改版/风控时，改用 `browser-recipes.md` 第1节（浏览器恢复榜单序列）与第2节（点找同款提offer链接），由 AI 按同一套红线/打分规则判断选品；Step3–6 始终走浏览器。

## 5. 站点类目树独立（2026-10-28 实测，重要）

**每个站点有自己独立的类目树与类目 ID**（按站点语言返回：MY=马来语、TH=泰语、SG/PH=英文、BR=葡语、MX=西语、VN=越南语、TW=繁体中文、ID=印尼语）。取数前**必须先用该站点的 `categorylist` 拿本站类目 ID，再 `getitemlist`**；跨站点复用类目 ID 会返回 SUCCESS 但 0 条（拿错钥匙）。

- **全站点实测（匿名即可，无需登录）**：MY/TH/PH/SG/VN/TW/BR/MX/ID 的 `categorylist` 均返回类目树，`getitemlist` 首个类目均返回数据（total 426–500）。**不存在"某站点无数据"**——之前误判 TH 无数据，是因为拿 SG 的类目 ID 去测 TH。
- **踩坑要点**：
  1. 曾观察到 MY 的 `categorylist` 先后返回马来语/英语两套类目名与不同 ID（疑似后端数据源轮换/缓存）；**每次执行先 `categorylist` 重新取当前类目 ID，不要缓存 ID 复用**。
  2. 网页端落地页 URL 里的 `siteCode`/`cateLvl1Id`/`tabCode` 参数可直连 `getitemlist` 验证（用户实测：TH 新品榜 cateId=`163cdd17915b4e62d32547f74b39d89a` 匿名 total=500）。
  3. 已知可用类目 ID 示例（2026-10-28，仅当日有效，执行前仍以 categorylist 为准）：MY 宠物 `30516df0e18347953a9cec3b4f99725d`；TH 新品宠物 `163cdd17915b4e62d32547f74b39d89a`；PH 文具 `c1f85df712d17921ea9353fd94adb086`。
  4. 无 SLA，快照随时可能轮换：执行前用 1 次 `items` 探活，失效即回退浏览器（`browser-recipes.md` 第1节）。
  5. **`--strategy newbie`（默认 MY+PH）多站执行**：先分别对 MY、PH 各调一次 `categorylist` 取本站当前类目 ID（MY 按马来语、PH 按英语），再逐站 `getitemlist`；两站之间及与其他站一律不复用类目 ID（跨站复用返回 SUCCESS 但 0 条）。站点组合由策略映射展开（见 selection-rules.md 第七节），脚本仍一次一个站点执行。
