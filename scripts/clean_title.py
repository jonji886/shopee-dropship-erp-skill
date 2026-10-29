#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shopee 轻出海标题清洗脚本（接口直连，实测通过）

用途：剔除 1688 货源标题里自带的行话前缀和竞品平台名，避免 Shopee
「关键词/品牌、属性滥用」违规扣分，以及浪费标题前 30 字符的搜索权重。

清洗规则（按 Shopee《跨境卖家政策指引手册》1.1.1.4 + 行业实践）：
  A. 任意位置删除的平台/竞品名（合规风险，删无赦）：
     亚马逊 / Amazon / amazon / AMAZON / ebay / Ebay / EBAY /
     Etsy / etsy / WISH / wish / 速卖通 / AliExpress / aliexpress
  B. 仅开头连续删除的行话前缀（本地买家不搜、占权重位）：
     跨境 / 外贸 / 出口 / 海外 / 原单 / 尾单 / 专供 / 一件代发 / 代发 / 销售 / 批发
  C. 清理多余空格、开头结尾的分隔符（| 、- ， , ）。

用法：
  python3 clean_title.py clean --num-iid <ERP内部ID>           # 单条清洗
  python3 clean_title.py clean --num-iid <ID> --dry-run        # 只看不写
  python3 clean_title.py clean-all --size 100 --out ./erp_data  # 批量扫采集箱
  python3 clean_title.py clean-all --dry-run --out ./erp_data

认证同 update_erp_item.py：qnquerystring=<JWT> + appType:3，
token 存 scripts/erp_token.txt 或环境变量 ERP_TOKEN。

已知坑（2026-10-29 实测沉淀）：
  - queryDetailByNumIid 连续快速调用会触发后端限流（返回空 data），
    批量模式间隔设 2s；update 失败后自动等 3s 重试 1 次。
  - updateErpItemByNumIid 必须传完整 DTO（queryDetail 拉全量再改 title），
    只传 {numIid, title} 会被当新建商品。本脚本直接复用已拉到的 dto，
    避免重复 query 触发限流。
"""
import argparse, json, os, re, sys, time, urllib.request

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erp_token.txt")
BASE = "https://erp.kuaidizs.cn"
MIN_INTERVAL = 2.0       # 批量请求间隔（实测 1s 会触发限流）
RETRY_WAIT = 3.0         # 失败后重试等待
MAX_RETRY = 1            # 自动重试次数
_last = [0.0]

# A. 任意位置删除（平台名/竞品名，不区分大小写）
PLATFORM_WORDS = [
    "亚马逊", "Amazon", "amazon", "AMAZON",
    "ebay", "Ebay", "EBAY",
    "Etsy", "etsy", "ETSY",
    "wish", "Wish", "WISH",
    "速卖通", "AliExpress", "aliexpress", "ALIEXPRESS",
]

# B. 仅开头连续删除的行话前缀
PREFIX_WORDS = [
    "一件代发", "代发", "跨境", "外贸", "出口", "海外",
    "原单", "尾单", "专供", "销售", "批发",
]


def _token():
    t = os.environ.get("ERP_TOKEN")
    if t:
        return t.strip()
    try:
        return open(TOKEN_FILE).read().strip()
    except OSError:
        sys.exit("[clean] 找不到 token：先设置 ERP_TOKEN 或写 scripts/erp_token.txt")


def post(path, body):
    now = time.time()
    wait = MIN_INTERVAL - (now - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(BASE + path, data=json.dumps(body, ensure_ascii=False).encode(), method="POST")
    req.add_header("Content-Type", "application/json;charset=UTF-8")
    req.add_header("qnquerystring", _token())
    req.add_header("appType", "3")
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def clean_title(title):
    """返回 (新标题, 被删除的词列表)。无变化时新标题与原标题相同。"""
    if not title:
        return title, []
    removed = []

    # A. 任意位置删除平台/竞品名
    for w in PLATFORM_WORDS:
        if re.search(r'[A-Za-z]', w):
            pat = re.compile(re.escape(w), re.IGNORECASE)
        else:
            pat = re.compile(re.escape(w))
        if pat.search(title):
            removed.append(w)
            title = pat.sub("", title)

    # B. 循环删除开头连续的行话前缀（可能多个连在一起）
    changed = True
    while changed:
        changed = False
        stripped = title.lstrip(" |-–,，.。、：:　")
        for w in PREFIX_WORDS:
            if stripped.startswith(w):
                removed.append(w)
                stripped = stripped[len(w):]
                title = stripped
                changed = True
                break

    # C. 清理多余空格和开头/结尾的分隔符
    title = re.sub(r'[ \t　]+', ' ', title)
    title = re.sub(r'^[ |\-–,，.。、：:]+', '', title)
    title = re.sub(r'[ |\-–,，.。、：:]+$', '', title)
    title = title.strip()

    return title, removed


def query_detail(num_iid):
    st, resp = post("/item/center/queryDetailByNumIid", {"numIid": num_iid})
    if st != 200 or not (resp.get("data") or {}):
        return None
    return resp["data"]


def update_title(num_iid, new_title, dto=None):
    """写回新标题。dto 可选——调用方已拉过则直接复用，避免重复 query 触发限流。"""
    if dto is None:
        dto = query_detail(num_iid)
    if dto is None:
        return False, "详情拉取失败"
    dto["title"] = new_title

    for attempt in range(MAX_RETRY + 1):
        st, resp = post("/item/center/updateErpItemByNumIid",
                        {"numIid": num_iid, "erpItemUpdateDTO": dto})
        if st == 200 and resp.get("success"):
            time.sleep(3)  # 等后端落库再回读
            chk = query_detail(num_iid)
            if chk and chk.get("title") == new_title:
                return True, "ok"
            if chk is None and attempt < MAX_RETRY:
                time.sleep(RETRY_WAIT)
                continue
            return False, f"回读不一致: {chk and chk.get('title')}"
        if attempt < MAX_RETRY:
            time.sleep(RETRY_WAIT)
            # 重试时重新拉 dto（可能后端状态已变）
            dto = query_detail(num_iid)
            if dto is not None:
                dto["title"] = new_title
    return False, json.dumps(resp, ensure_ascii=False)[:300]


def clean_one(num_iid, dry_run=False):
    dto = query_detail(num_iid)
    if dto is None:
        return {"numIid": num_iid, "ok": False, "msg": "详情拉取失败"}
    old = dto.get("title", "")
    new, removed = clean_title(old)
    if new == old:
        return {"numIid": num_iid, "erpCode": dto.get("erpCode"),
                "old": old, "new": new, "changed": False, "msg": "无需清洗"}
    if dry_run:
        return {"numIid": num_iid, "erpCode": dto.get("erpCode"),
                "old": old, "new": new, "changed": True,
                "removed": removed, "msg": "dry-run"}
    ok, msg = update_title(num_iid, new, dto=dto)  # 复用 dto，不重复 query
    return {"numIid": num_iid, "erpCode": dto.get("erpCode"),
            "old": old, "new": new, "changed": True,
            "removed": removed, "ok": ok, "msg": msg}


def list_all_items(size=100):
    """分页拉采集箱全量。"""
    items = []
    page = 1
    while True:
        st, resp = post("/item/center/queryErpItemListPage",
                        {"pageNo": page, "pageSize": size})
        if st != 200 or not resp.get("success"):
            break
        data = resp.get("data") or {}
        lst = data.get("list") or []
        if not lst:
            break
        items.extend(lst)
        total = data.get("total", 0)
        if len(items) >= total or page >= 20:
            break
        page += 1
    return items


def main():
    p = argparse.ArgumentParser(description="Shopee 轻出海标题清洗")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clean", help="单条清洗")
    c.add_argument("--num-iid", required=True)
    c.add_argument("--dry-run", action="store_true")

    ca = sub.add_parser("clean-all", help="批量扫采集箱清洗")
    ca.add_argument("--size", type=int, default=100)
    ca.add_argument("--dry-run", action="store_true")
    ca.add_argument("--out", default="./erp_data")

    a = p.parse_args()

    if a.cmd == "clean":
        r = clean_one(a.num_iid, dry_run=a.dry_run)
        print(f"numIid: {r['numIid']}  erpCode: {r.get('erpCode','')}")
        print(f"  原标题: {r.get('old','')}")
        print(f"  新标题: {r.get('new','')}")
        if r.get("removed"):
            print(f"  删除词: {r['removed']}")
        print(f"  状态:   {r.get('msg','')}")
        return

    # clean-all：列表已含 title，直接算，无需逐条 query；只在 update 时拉 dto
    items = list_all_items(size=a.size)
    print(f"[clean-all] 采集箱共 {len(items)} 条")
    results = []
    changed_n = 0
    for i, it in enumerate(items, 1):
        num_iid = str(it.get("numIid") or "")
        old_title = it.get("title") or ""
        new, removed = clean_title(old_title)
        if new == old_title:
            continue
        changed_n += 1
        print(f"[{i}/{len(items)}] {it.get('erpCode','')}")
        print(f"  原: {old_title}")
        print(f"  新: {new}  (删除: {removed})")
        if a.dry_run:
            results.append({"numIid": num_iid, "erpCode": it.get("erpCode"),
                            "old": old_title, "new": new, "removed": removed,
                            "ok": None, "msg": "dry-run"})
        else:
            # 列表页不含完整 DTO，需要 query 一次再 update
            ok, msg = update_title(num_iid, new)
            print(f"  -> {'OK' if ok else 'FAIL'} {msg}")
            results.append({"numIid": num_iid, "erpCode": it.get("erpCode"),
                            "old": old_title, "new": new, "removed": removed,
                            "ok": ok, "msg": msg})

    os.makedirs(a.out, exist_ok=True)
    out_path = os.path.join(a.out, "clean_title_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    ok_n = sum(1 for x in results if x.get("ok") is True)
    print(f"\n批量完成: 需清洗 {changed_n} 条"
          f"{' (dry-run 未写入)' if a.dry_run else f'，成功更新 {ok_n} 条'}")
    print(f"明细 -> {out_path}")


if __name__ == "__main__":
    main()
