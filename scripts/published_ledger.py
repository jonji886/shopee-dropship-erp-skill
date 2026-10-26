#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地已发清单台账（shopee-light-listing Step4.5 去重检查用，纯标准库）。

用途：跨次/跨天记录已提交铺货的 1688 offerId，避免同一链接重复上架。
与 ERP「发布记录」比对互补：发布记录只覆盖近期翻页，本台账持久保存全部历史。

CSV 默认路径 ./aibuy_data/published_offers.csv，列：
  offerId,rankId,title,submitted_at,shop,status,site

子命令：
  check   --ids 681683584352,xxx   输出已在台账中（占用）的 offerId；未占用的放行
  append  --ids 681683584352 --rank-id R --title "标题" --shop "店铺" --site MY --status submitted
  status  --ids 681683584352 --status 发布成功   更新已有记录的终态
  list                              列出台账全部记录

状态口径：submitted/审核中/发布中/排队中/发布成功 都视为占用，发布失败可重提（默认仍保留记录，不自动删）。
"""
import argparse, csv, os, sys, datetime

FIELDS = ["offerId", "rankId", "title", "submitted_at", "shop", "status", "site"]


def default_ledger():
    return os.path.join("aibuy_data", "published_offers.csv")


def load(path):
    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("offerId"):
                    rows.append(r)
    return rows


def cmd_check(args):
    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    occupied = {r["offerId"] for r in load(args.ledger)}
    hit = [i for i in ids if i in occupied]
    free = [i for i in ids if i not in occupied]
    print("OCCUPIED=" + ",".join(hit))
    print("FREE=" + ",".join(free))


def cmd_append(args):
    rows = load(args.ledger)
    existing = {r["offerId"] for r in rows}
    os.makedirs(os.path.dirname(args.ledger) or ".", exist_ok=True)
    new = []
    for oid in [x.strip() for x in args.ids.split(",") if x.strip()]:
        if oid in existing:
            continue
        new.append({
            "offerId": oid,
            "rankId": args.rank_id or "",
            "title": args.title or "",
            "submitted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "shop": args.shop or "",
            "status": args.status or "submitted",
            "site": args.site or "",
        })
    if new:
        write_header = not os.path.exists(args.ledger)
        with open(args.ledger, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if write_header:
                w.writeheader()
            w.writerows(new)
    print("APPENDED=" + ",".join(r["offerId"] for r in new))


def cmd_status(args):
    rows = load(args.ledger)
    targets = {x.strip() for x in args.ids.split(",") if x.strip()}
    changed = []
    for r in rows:
        if r["offerId"] in targets:
            r["status"] = args.status
            changed.append(r["offerId"])
    if rows:
        os.makedirs(os.path.dirname(args.ledger) or ".", exist_ok=True)
        with open(args.ledger, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
    print("STATUS_UPDATED=" + ",".join(changed))


def cmd_list(args):
    for r in load(args.ledger):
        print(",".join(r.get(k, "") for k in FIELDS))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default=default_ledger())
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check")
    c.add_argument("--ids", required=True)
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("append")
    a.add_argument("--ids", required=True)
    a.add_argument("--rank-id", default="")
    a.add_argument("--title", default="")
    a.add_argument("--shop", default="")
    a.add_argument("--site", default="")
    a.add_argument("--status", default="submitted")
    a.set_defaults(func=cmd_append)

    s = sub.add_parser("status")
    s.add_argument("--ids", required=True)
    s.add_argument("--status", required=True)
    s.set_defaults(func=cmd_status)

    l = sub.add_parser("list")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
