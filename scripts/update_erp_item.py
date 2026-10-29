#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快递助手ERP 采集箱商品编辑客户端（接口直连，实测通过）
接口（2026-10-29 抓包验证）：
  POST /item/center/queryDetailByNumIid   # 拉商品详情（返回 erpItemUpdateDTO 字段全集）
  POST /item/center/updateErpItemByNumIid # 保存编辑（顶层 numIid + 完整 DTO）

关键坑（实测）：
  - body 必须 {numIid:<ERP内部ID>, erpItemUpdateDTO:<完整详情对象>}；只传 numIid/erpCode/title 的最小 DTO
    会被后端当作"新建商品"插入采集箱（生成新 numIid、原记录不动）——务必用 queryDetail 先拉全量再改。
  - descImageList 为空的商品发布到 Shopee 会报"商品详情图片不能为空"；
    本脚本的 update 可以顺带写入 descImageList/itemImgs（传 URL 数组即可），但 URL 必须真实可达。
  - 认证：qnquerystring=<JWT> + appType:3，token 存 scripts/erp_token.txt（失效报 703，需从浏览器重新导出）。

用法：
  python3 update_erp_item.py query --num-iid <ERP内部ID>            # 拉详情（只读）
  python3 update_erp_item.py update --num-iid <ID> --erp-code Y100 \
      --title "新标题" [--out ./erp_data]                            # 改标题（写）
  python3 update_erp_item.py batch --file titles.csv --out ./erp_data # 批量（csv: numIid,erpCode,new_title）
  python3 update_erp_item.py batch --file titles.json --out ./erp_data # json: [{"numIid":...,"erpCode":...,"new_title":...}]

批量模式对每个商品：query 拉详情 → 改 title → update 提交 → 回读验证标题，打印结果。
"""
import argparse, csv, json, os, sys, time, urllib.request

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erp_token.txt")
BASE = "https://erp.kuaidizs.cn"
MIN_INTERVAL = 1.0
_last = [0.0]


def _token():
    t = os.environ.get("ERP_TOKEN")
    if t:
        return t.strip()
    try:
        return open(TOKEN_FILE).read().strip()
    except OSError:
        sys.exit("[erp] 找不到 token：先设置环境变量 ERP_TOKEN，或写 scripts/erp_token.txt")


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


def query_detail(num_iid):
    st, resp = post("/item/center/queryDetailByNumIid", {"numIid": num_iid})
    if st != 200 or not (resp.get("data") or {}):
        print(f"[warn] queryDetail {num_iid}: {resp}", file=sys.stderr)
        return None
    return resp["data"]


def update_title(num_iid, erp_code, new_title, verify=True):
    dto = query_detail(num_iid)
    if dto is None:
        return False, "详情拉取失败"
    dto["title"] = new_title
    st, resp = post("/item/center/updateErpItemByNumIid",
                    {"numIid": num_iid, "erpItemUpdateDTO": dto})
    if st != 200 or not resp.get("success"):
        return False, json.dumps(resp, ensure_ascii=False)[:300]
    if verify:
        time.sleep(2)
        chk = query_detail(num_iid)
        if not chk or chk.get("title") != new_title:
            return False, f"提交成功但回读标题不一致: {chk and chk.get('title')}"
    return True, "ok"


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query")
    q.add_argument("--num-iid", required=True)

    u = sub.add_parser("update")
    u.add_argument("--num-iid", required=True)
    u.add_argument("--erp-code", required=True)
    u.add_argument("--title", required=True)
    u.add_argument("--no-verify", action="store_true")

    b = sub.add_parser("batch")
    b.add_argument("--file", required=True)
    b.add_argument("--out", default="./erp_data")
    b.add_argument("--no-verify", action="store_true")

    a = p.parse_args()

    if a.cmd == "query":
        dto = query_detail(a.num_iid)
        if dto:
            os.makedirs("erp_probe", exist_ok=True)
            with open("erp_probe/detail.json", "w", encoding="utf-8") as f:
                json.dump(dto, f, ensure_ascii=False, indent=2)
            print(f"title: {dto.get('title')}")
            print(f"erpCode: {dto.get('erpCode')}  price: {dto.get('price')}  descImages: {len(dto.get('descImageList') or [])}  imgs: {len(dto.get('itemImgs') or [])}")
        return

    if a.cmd == "update":
        ok, msg = update_title(a.num_iid, a.erp_code, a.title, verify=not a.no_verify)
        print("OK " if ok else "FAIL", a.num_iid, a.erp_code, "->", a.title, "|", msg)
        return

    # batch
    rows = []
    if a.file.endswith(".json"):
        rows = json.load(open(a.file, encoding="utf-8"))
    else:
        with open(a.file, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    os.makedirs(a.out, exist_ok=True)
    results = []
    for i, r in enumerate(rows, 1):
        num_iid = str(r.get("numIid") or r.get("num_iid") or "").strip()
        erp_code = str(r.get("erpCode") or r.get("erp_code") or "").strip()
        title = (r.get("new_title") or r.get("title") or "").strip()
        if not (num_iid and erp_code and title):
            results.append({"numIid": num_iid, "erpCode": erp_code, "new_title": title, "ok": False, "msg": "缺字段"})
            continue
        ok, msg = update_title(num_iid, erp_code, title, verify=not a.no_verify)
        results.append({"numIid": num_iid, "erpCode": erp_code, "new_title": title, "ok": ok, "msg": msg})
        print(f"[{i}/{len(rows)}] {'OK' if ok else 'FAIL'} {erp_code} | {title[:24]} | {msg}")
    with open(os.path.join(a.out, "update_titles_result.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    ok_n = sum(1 for x in results if x["ok"])
    print(f"\n批量完成: 成功 {ok_n}/{len(results)}，明细 -> {a.out}/update_titles_result.json")


if __name__ == "__main__":
    main()
