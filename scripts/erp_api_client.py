#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_api_client.py — 快递助手ERP跨境版 接口客户端（Step3/4/4.5/5/6 用）

链路：Shopee轻出海铺货 Skill 的 ERP 登录态操作，从「浏览器点击」改为「接口直连」。
只读命令：items/logs/shops（低频、个人使用）；collect 为写操作（把 Step2 的 offerId 清单采集进 ERP 采集箱，仅用于用户明确要采集的清单）。

认证（实测）：
  - 请求头必须带  qnquerystring: <JWT token>    （token 登录后写入 sessionStorage/localStorage/Cookie）
  - 请求头必须带  appType: 3                    （跨境/轻出海数据域开关，缺它返回空 list）
  - 不需要 Cookie、无请求签名。错误码 703=token 缺失/失效；707=操作过于频繁（需降频）。

token 获取：
  - 方式A（推荐）：浏览器登录态内执行下面这段（bu.js），把输出存到 erp_token.txt：
      (function(){return sessionStorage.getItem('qnquerystring')||localStorage.getItem('templateUserToken')||'';})()
  - 方式B：python3 erp_api_client.py token --set <token>
  - 方式C：环境变量 ERP_TOKEN

用法：
  python3 erp_api_client.py token --check                     # 校验 token 有效性
  python3 erp_api_client.py items [--page N] [--size N] [--unclaimed] [--ids 1,2,3] [--out DIR]
  python3 erp_api_client.py logs  [--months N] [--status success|fail|processing|examine] [--ids 1,2,3] [--out DIR]
  python3 erp_api_client.py shops [--platform shopees] [--out DIR]   # Step5 铺货前预查店铺
  python3 erp_api_client.py collect --ids 1,2,3 [--out DIR]          # Step3 链接采集（写操作，提交 offerId 清单）
  python3 erp_api_client.py distribute --ids 1,2,3 [--shop SELLERID] [--out DIR]  # Step5 铺货提交（写操作）

输出：每命令在 --out 目录（默认 ./erp_data）写 CSV + JSON。

合规：只读命令不写不提交；collect 为写操作，仅采集用户明确点名的清单、单批 ≤500、不批量抓取、不转售。
接口为未公开内部接口，无 SLA，前端改版会断；报错即回退 references/browser-recipes.md 浏览器流程。
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = "https://erp.kuaidizs.cn"
HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "appType": "3",  # 跨境数据域，缺省返回空
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
}
MIN_INTERVAL = 1.0  # 实测并发触发 707 限流，保持低频
_last_ts = 0.0

# 发布失败原因归因库（与 references/selection-rules.md 第五节一致；顺序=优先级，errorMessage 含任一关键词即命中）
# (关键词列表, 严重度, 处理建议)
_ADVICE_RULES = [
    (("规格之间价格比例不能大于7倍",), "整品失败",
     "SKU规格价差超限（卷材/管材/多尺寸类天然如此）。不要删SKU硬救，直接弃用该品，换同品类单规格offer或换新品类重采；选品阶段按 selection-rules 第一节第9条提前剔除"),
    (("规格选项名称重复", "层变体选项重复"), "单站点",
     "该站点SKU规格名/层变体名重复，仅影响这一个站点；其余站点成功即整品成功。要补该站点需在编辑里把规格名改唯一后重提"),
    (("最多支持2层tier_variations", "tier_variations"), "可重试",
     "规格层级超过Shopee上限(2层tier_variations)。编辑里删减/合并规格层级到2层内后重提；改不了则弃品换单规格offer"),
    (("映像编号不等于", "全局层选项映像不等于第一层"), "可重试",
     "1688多规格转Shopee时变体映射错乱（某规格选项只在部分SKU存在、组合不完整）。编辑里检查并重建规格变体结构（删空选项、补全组合）后重提；改不动则弃品换规格规整的单规格offer"),
    (("get shop available/channels error 10004", "channels error 10004", "10004"), "可忽略",
     "平台该渠道配置问题，非卖家可修；其余站点成功即整品成功"),
    (("No channel can support",), "单站点",
     "个别站点/渠道不支持该类目或属性；单站点失败≠整品失败，记录被拒站点即可"),
    (("库存须 0-500000", "型号的库存应在", "库存应在0-500000"), "可重试",
     "库存数值超界；改回『使用商品来源』或重填合法库存后重提"),
    (("商品规格属性不能为空",), "可重试",
     "商品缺规格属性。编辑里补充规格属性（颜色/尺寸等）后重提；规格本身缺失则弃品"),
    (("创建item失败",), "可重试",
     "平台创建商品被拒且未给具体原因（袋/包装/印刷类常见：属性或图片不合规）。编辑采集箱商品（补规格属性/换图）后重提；重提仍失败则弃品换同款"),
    (("类目",), "撞红线",
     "类目/品牌/合规驳回，大概率撞红线或品牌；剔除该品，勿重复提交（选品红线判定没过）"),
    (("brand", "品牌"), "撞红线",
     "品牌/合规驳回；剔除该品，勿重复提交"),
    (("sorry.com", "image_url", "图像比率超出限制", "图像极其有限"), "可重试",
     "采集时抓到1688防盗链/占位图（图像高度<32或sorry域，非商品问题）。主图：重采刷新即可；collect幂等不刷新图片数据，重采无效（含描述图类）直接换同款另一offer"),
    (("404", "未找到url"), "可重试",
     "1688旧图已删除/迁移；重新采集取新图；仍404则换同款"),
    (("标题", "图片"), "可重试",
     "标题/图片不合规（含违禁词、侵权图）；改标题/图后重提"),
]


def _advice_for(fail_reason):
    """按失败原因文本匹配归因库，返回 (严重度, 处理建议) 或 None。"""
    if not fail_reason:
        return None
    for kws, level, advice in _ADVICE_RULES:
        for kw in kws:
            if kw in fail_reason:
                return level, advice
    return None

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erp_token.txt")


def _load_token(args):
    tok = getattr(args, "token", None) or os.environ.get("ERP_TOKEN") or ""
    if not tok and os.path.exists(TOKEN_FILE):
        tok = open(TOKEN_FILE, "r", encoding="utf-8").read().strip()
    if not tok:
        sys.exit("[erp] 未找到 token：先登录 ERP 后用 bu.js 导出，或 python3 erp_api_client.py token --set <token>")
    return tok


def _post(path, body, args):
    global _last_ts
    now = time.time()
    if now - _last_ts < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - (now - _last_ts))
    _last_ts = time.time()
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    for k, v in HEADERS.items():
        req.add_header(k, v)
    req.add_header("qnquerystring", _load_token(args))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
    except Exception as e:
        sys.exit(f"[erp] 网络错误 {path}: {e}")
    try:
        j = json.loads(raw)
    except Exception:
        sys.exit(f"[erp] 响应非JSON {path}: {raw[:200]}")
    if not j.get("success"):
        code = j.get("errorCode")
        msg = j.get("errorMessage", "")
        if code == 703 or "token" in msg:
            sys.exit(f"[erp] token 失效(703)：请重新登录 ERP 并刷新 erp_token.txt")
        if code == 707:
            sys.exit(f"[erp] 触发限流(707)：{msg}。请等待后再试，或调大 MIN_INTERVAL")
        sys.exit(f"[erp] 接口错误 {path}: code={code} msg={msg}")
    return j.get("data") or {}


def _write_out(args, name, rows, default_dir="erp_data"):
    out_dir = getattr(args, "out", None) or default_dir
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, name + ".csv")
    json_path = os.path.join(out_dir, name + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    if rows:
        cols = []
        for r in rows:
            for k in r.keys():
                if k not in cols:
                    cols.append(k)
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
    return csv_path, json_path


def cmd_distribute(args):
    """Step5 铺货提交（写操作）：把采集箱商品铺货到 Shopee 轻出海店铺。

    接口 POST /item/distribute/batchPublish（curl 直连实测成功，任务真实进入队列）。
    流程：items 拿 numIid → shops 确认有效店铺 → 构造 distribItemVos 分批(每批4个)提交。
    """
    ids = [i.strip() for i in (args.ids or "").split(",") if i.strip()]
    if not ids:
        sys.exit("[erp] distribute 需要 --ids（货源ID清单，逗号分隔）")
    # 1) 采集箱查 numIid（ERP 内部ID）
    d = _post("/item/center/queryErpItemListPage", {"pageNo": 1, "pageSize": 100, "platNumIidList": ids}, args)
    lst = d.get("list") or []
    num_map = {}  # 货源ID -> numIid
    for it in lst:
        pid = it.get("platNumIid") or it.get("erpCode") or ""
        if pid:
            num_map[str(pid)] = it.get("numIid", "")
    missing = [i for i in ids if i not in num_map]
    if missing:
        sys.exit(f"[erp] 以下货源ID不在采集箱（先跑 collect）：{','.join(missing)}")
    # 2) 店铺预查：浏览器弹窗只显示「轻出海商户店」(shopType=SHOPEE_MERCHANT)，
    #    默认目标必须是商户店；普通站点授权店(无shopType)不参与轻出海铺货
    sd = _post("/index/platformShop/getPlatformShops", {"pageNo": 1, "pageSize": 100, "platform": "shopees"}, args)
    shops = []
    for s in sd.get("list") or []:
        ok = (s.get("status") == 1) and (s.get("tokenStatus") == 1) and (s.get("enableStatus") == 1)
        if ok:
            shops.append({
                "sellerId": s.get("sellerId", ""),
                "sellerNick": s.get("sellerNick", "") or s.get("sellerAbbreviation", "") or "",
                "shopType": s.get("shopType", ""),
            })
    merchants = [s for s in shops if s["shopType"] == "SHOPEE_MERCHANT"]
    if not merchants:
        sys.exit("[erp] 无有效轻出海商户店（shopType=SHOPEE_MERCHANT）。普通站点授权店不能轻出海铺货，先在 ERP 检查商户店授权")
    target = None
    if args.shop:
        for s in shops:
            if str(s["sellerId"]) == str(args.shop):
                target = s
                break
        if not target:
            sys.exit(f"[erp] 指定店铺 {args.shop} 不在有效授权列表")
        if target["shopType"] != "SHOPEE_MERCHANT":
            print(f"[erp][警告] 指定店铺 {target['sellerNick']} 不是轻出海商户店(shopType={target['shopType']})，可能铺货失败")
    else:
        target = merchants[0]
    print(f"[erp] 目标店铺: {target['sellerNick']} (sellerId={target['sellerId']}, 轻出海商户店)")
    # 3) 分批提交（每批4个，与前端一致）
    vos = [{"itemId": str(num_map[i]), "sourcePlatform": "kdzs_erp", "targetPlatform": "shopees",
            "sourceSellerId": "", "targetSellerId": str(target["sellerId"]),
            "targetSellerNick": target["sellerNick"], "categoryIds": [], "categoryNames": []}
           for i in ids]
    batch_rows = []
    total = len(vos)
    for x in range(0, total, 4):
        chunk = vos[x:x + 4]
        body = {"distribItemVos": chunk, "distributionTotalNum": total}
        d2 = _post("/item/distribute/batchPublish", body, args)
        batch_rows.append({"批次": x // 4 + 1, "提交数": len(chunk), "成功": d2.get("success", True)})
    csv_path, json_path = _write_out(args, "distribute_result", batch_rows)
    print(f"[erp] 铺货提交: {total} 个商品 → {target['sellerNick']}，任务已进入发布队列")
    print(f"  明细: CSV {csv_path} / JSON {json_path}")
    print(f"  [提示] 终态异步，稍后用 logs --months 1 查状态（success=成功/fail=失败/processing/examine=中间态）")


def cmd_token(args):
    if args.action == "set":
        tok = args.token or ""
        if not tok:
            sys.exit("用法: erp_api_client.py token --set <token>")
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(tok.strip())
        print(f"[erp] token 已保存: {TOKEN_FILE}")
    elif args.action == "check":
        d = _post("/index/platformShop/getPlatformShops", {"pageNo": 1, "pageSize": 5}, args)
        print(f"[erp] token 有效，店铺接口响应: total={d.get('total')} rows={len(d.get('list') or [])}")
    else:
        print("用法: token --set <token> | --check")


def _pick(row, *keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return ""


def cmd_items(args):
    body = {"pageNo": args.page, "pageSize": args.size}
    if args.unclaimed:
        body["claimPlatformList"] = [""]
    if args.ids:
        body["platNumIidList"] = [i.strip() for i in args.ids.split(",") if i.strip()]
    d = _post("/item/center/queryErpItemListPage", body, args)
    lst = d.get("list") or []
    rows = []
    for it in lst:
        src_links = it.get("itemSourceLinks") or []
        rows.append({
            "货源ID": _pick(it, "platNumIid", "erpCode"),
            "ERP内部ID": it.get("numIid", ""),
            "标题": it.get("title", ""),
            "最低价": it.get("priceLow", ""),
            "最高价": it.get("priceTop", ""),
            "来源": it.get("sourceName", ""),
            "认领平台": ",".join(it.get("claimPlatformList") or []),
            "已认领": it.get("claimStatus", ""),
            "采集时间": it.get("gmtCreated", ""),
            "1688链接": (src_links[0].get("sourceLink", "") if src_links else ""),
            "图片": it.get("picUrl", ""),
        })
    csv_path, json_path = _write_out(args, "shared_goods", rows)
    print(f"[erp] 采集箱: total={d.get('total')} 本页={len(rows)}")
    print(f"  CSV : {csv_path}\n  JSON: {json_path}")


def _fetch_log_window(start, end, args, ids):
    """拉一个时间窗口内的全部发布记录（自动翻页）。窗口≤31天（接口限制）。"""
    body = {
        "pageNo": 1,
        "pageSize": 100,
        "startTime": start,
        "endTime": end,
        "fromPlatformList": ["1688"],
        "toPlatformList": ["shopees"],
    }
    if args.status:
        body["status"] = args.status
    if ids:
        body["fromItemIdList"] = ids  # 货源ID(源商品)筛选；toItemIdList 是 Shopee 侧产品ID，勿用
    rows = []
    total = 0
    page = 1
    while True:
        body["pageNo"] = page
        d = _post("/item/distribute/queryLogs", body, args)
        lst = d.get("list") or []
        total = d.get("total", 0)
        for it in lst:
            ext = it.get("extInfo") or {}
            reason = it.get("errorMessage", "") or ""
            # 站点级失败原因合并（errorMessage 为空时从 sitePublishStatusList 提取）
            if not reason:
                site_parts = []
                for sp in (ext.get("sitePublishStatusList") or []):
                    fr = sp.get("failReason") or ""
                    if fr and fr not in site_parts:
                        site_parts.append(fr)
                if site_parts:
                    reason = " | ".join(site_parts)
            rows.append({
                "货源ID": _pick(it, "itemId") or ext.get("ITEM_SOURCE_NUM_IID", ""),
                "状态": it.get("status", ""),
                "标题": _pick(it, "title", "fromTitle"),
                "发布时间": it.get("createTime", ""),
                "店铺": it.get("shopName", ""),
                "平台": it.get("platform", ""),
                "失败原因": reason,
                "任务ID": it.get("taskId", ""),
            })
        if page * 100 >= total or not lst:
            break
        page += 1
        if page > 50:  # 防御：单窗口最多 50 页
            break
    return rows, total


def cmd_logs(args):
    months = max(1, getattr(args, "months", 1))
    ids = [i.strip() for i in (args.ids or "").split(",") if i.strip()]
    all_rows = []
    grand_total = 0
    # 接口限制：查询时间间隔不能大于一个月 → 按月窗口循环，窗口间留 1 秒间隔
    for m in range(months):
        end_ts = time.time() - m * 30 * 86400
        start_ts = end_ts - 30 * 86400
        start = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_ts))
        end = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_ts))
        rows, total = _fetch_log_window(start, end, args, ids)
        all_rows.extend(rows)
        grand_total += total
    # 跨窗口去重（同一任务ID/货源ID+发布时间只留一次）
    seen = set()
    dedup = []
    for r in all_rows:
        key = (r["货源ID"], r["任务ID"], r["发布时间"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    csv_path, json_path = _write_out(args, "publish_logs", dedup)
    # 统计口径（与 SKILL 一致：中间态不计成功）
    cnt = {}
    for r in dedup:
        cnt[r["状态"]] = cnt.get(r["状态"], 0) + 1
    print(f"[erp] 发布记录: 近{months}个月 窗口合计={grand_total} 去重后={len(dedup)}")
    print(f"  状态分布: {json.dumps(cnt, ensure_ascii=False)}")
    # --advice：失败记录自动对照归因库（selection-rules.md 第五节）
    if getattr(args, "advice", False):
        fails = [r for r in dedup if r["状态"] == "fail"]
        stat = {}
        for r in fails:
            reason = r["失败原因"] or ""
            if not reason.strip():
                r["严重度"], r["处理建议"] = "未知", "接口未返回原因文本：检查该记录站点级 failReason（sitePublishStatusList）或 ERP 页面详情；多为商品资料问题，对照 selection-rules 第五节人工归因"
            else:
                hit = _advice_for(reason)
                if hit:
                    r["严重度"], r["处理建议"] = hit
                else:
                    r["严重度"], r["处理建议"] = "未收录", "未收录原因：抄录原文，对照 selection-rules 第五节人工归因；无法归因的按『整品失败弃品 / 单站点忽略 / 可重试』三选一处理"
            stat[r["严重度"]] = stat.get(r["严重度"], 0) + 1
        if fails:
            csv_path, json_path = _write_out(args, "publish_logs", dedup)  # 重写 CSV 带建议列
            print(f"  失败归因: 共 {len(fails)} 条失败 → {json.dumps(stat, ensure_ascii=False)}")
            print(f"  建议已写入 CSV/JSON（列：严重度/处理建议），CSV : {csv_path}")
        else:
            print("  失败归因: 无失败记录")
    print(f"  CSV : {csv_path}\n  JSON: {json_path}")


def cmd_collect(args):
    """Step3 链接采集提交（写操作）：把 offerId 清单采集进 ERP 采集箱。

    接口 POST /item/center/batchPluginCollectItem，body {"itemIdList":[offerId...]}。
    实测行为：已在采集箱的 ID 幂等算成功；无效 ID 计 fail；单批上限 500（页面同口径）。
    """
    ids = []
    if args.ids:
        ids += [i.strip() for i in args.ids.split(",") if i.strip()]
    if args.ids_file:
        with open(args.ids_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 兼容纯 ID 行 / CSV 首列 / 1688 链接三种形式
                m = line.split(",")[0].strip()
                if "detail.1688.com/offer/" in line:
                    m = line.split("detail.1688.com/offer/")[1].split(".")[0].split("/")[0].strip()
                ids.append(m)
    if not ids:
        sys.exit("[erp] collect 需要 --ids 或 --ids-file（offerId 清单）")
    ids = list(dict.fromkeys(ids))  # 去重保序
    # 分批（页面口径单次最多 500）
    batch_rows = []
    total_success = total_fail = total_skip = 0
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        d = _post("/item/center/batchPluginCollectItem", {"itemIdList": chunk}, args)
        total_success += d.get("collectSuccessNum", 0)
        total_fail += d.get("collectFailNum", 0)
        total_skip += d.get("collectSkipNum", 0)
        batch_rows.append({
            "批次": i // 500 + 1,
            "提交数": len(chunk),
            "成功": d.get("collectSuccessNum", 0),
            "失败": d.get("collectFailNum", 0),
            "跳过": d.get("collectSkipNum", 0),
            "跳过原因": json.dumps(d.get("skipReasonCountMap") or {}, ensure_ascii=False),
        })
    csv_path, json_path = _write_out(args, "collect_result", batch_rows)
    print(f"[erp] 采集提交: 清单 {len(ids)} 个offerId，成功 {total_success}、失败 {total_fail}、跳过 {total_skip}")
    print(f"  明细: CSV {csv_path} / JSON {json_path}")
    if total_fail:
        print(f"  [提示] {total_fail} 个采集失败（多为无效/已下架 offerId），可对失败项在浏览器核对")
    return total_fail


def cmd_shops(args):
    body = {"pageNo": 1, "pageSize": 100}
    if getattr(args, "platform", ""):
        body["platform"] = args.platform
    d = _post("/index/platformShop/getPlatformShops", body, args)
    lst = d.get("list") or []
    rows = []
    for s in lst:
        ext = s.get("extendInfo") or {}
        ok = (s.get("status") == 1) and (s.get("tokenStatus") == 1) and (s.get("enableStatus") == 1)
        shop_type = s.get("shopType", "")
        rows.append({
            "店铺名": s.get("sellerNick", "") or s.get("sellerAbbreviation", "") or "",
            "平台": s.get("platform", ""),
            "卖家ID": s.get("sellerId", ""),
            "店铺类型": "轻出海商户" if shop_type == "SHOPEE_MERCHANT" else ("站点店" if not shop_type else shop_type),
            "站点": ext.get("region", ""),
            "授权状态": "有效" if ok else "异常",
            "授权过期": s.get("tokenExpireTime", ""),
            "启用": s.get("enableStatus", ""),
        })
    csv_path, json_path = _write_out(args, "shops", rows)
    valid = [r for r in rows if r["授权状态"] == "有效"]
    merchants = [r for r in valid if r["店铺类型"] == "轻出海商户"]
    print(f"[erp] 店铺: total={d.get('total')} 返回={len(rows)} 有效授权={len(valid)} 轻出海商户={len(merchants)}")
    if merchants:
        first = merchants[0]
        print(f"[erp] 预查(Step5): 默认将勾选首个轻出海商户店 -> {first['店铺名']}")
        print(f"[erp] 预查: 轻出海商户店 {len(merchants)} 家；站点授权店不参与轻出海铺货")
    else:
        print("[erp] 预查(Step5): 无有效轻出海商户店！铺货会失败，先在 ERP 检查店铺授权")
    print(f"  CSV : {csv_path}\n  JSON: {json_path}")


def main():
    p = argparse.ArgumentParser(description="快递助手ERP 只读接口客户端")
    sub = p.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("token", help="token 管理")
    pt.add_argument("action", choices=["set", "check"])
    pt.add_argument("--token", default="")

    pi = sub.add_parser("items", help="公共采集箱列表")
    pi.add_argument("--page", type=int, default=1)
    pi.add_argument("--size", type=int, default=100)
    pi.add_argument("--unclaimed", action="store_true", help="只看未认领(claimPlatformList=[''])")
    pi.add_argument("--ids", default="", help="按货源ID筛选，逗号分隔")
    pi.add_argument("--out", default="")

    pl = sub.add_parser("logs", help="Shopee轻出海发布记录")
    pl.add_argument("--months", type=int, default=1, help="按月循环拉取 N 个月历史（接口单窗限31天），去重比对建议 3-6")
    pl.add_argument("--status", default="", choices=["", "success", "fail", "processing", "examine"])
    pl.add_argument("--ids", default="", help="按货源ID筛选，逗号分隔")
    pl.add_argument("--advice", action="store_true", help="失败记录自动对照归因库，附加严重度/处理建议（selection-rules 第五节）")
    pl.add_argument("--out", default="")

    ps = sub.add_parser("shops", help="店铺列表 + Step5 铺货前预查")
    ps.add_argument("--platform", default="", help="按平台过滤（轻出海=shopees，默认全部）")
    ps.add_argument("--out", default="")

    pc = sub.add_parser("collect", help="Step3 链接采集提交（写操作）")
    pc.add_argument("--ids", default="", help="offerId 清单，逗号分隔")
    pc.add_argument("--ids-file", default="", help="offerId 清单文件（每行一个；支持纯ID/CSV首列/1688链接）")
    pc.add_argument("--out", default="")

    pd = sub.add_parser("distribute", help="Step5 铺货提交（写操作，接口直连）")
    pd.add_argument("--ids", default="", help="货源ID（platNumIid）清单，逗号分隔")
    pd.add_argument("--shop", default="", help="目标店铺 sellerId（默认取首个有效授权店铺）")
    pd.add_argument("--out", default="")

    for sp in (pi, pl, ps, pc, pd):
        sp.add_argument("--token", default="")
    args = p.parse_args()

    if args.cmd == "token":
        cmd_token(args)
    elif args.cmd == "items":
        cmd_items(args)
    elif args.cmd == "logs":
        cmd_logs(args)
    elif args.cmd == "shops":
        cmd_shops(args)
    elif args.cmd == "collect":
        cmd_collect(args)
    elif args.cmd == "distribute":
        cmd_distribute(args)


if __name__ == "__main__":
    main()
