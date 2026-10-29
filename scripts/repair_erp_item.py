#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集箱商品规格修复（实验）：query 全量 DTO → 修改 skus.skuAttributesList 结构 → update 提交 → 回读。
模式：
  single_tier  只保留第一个属性（pid=1236 规格型号优先），其余层删除 → Shopee 侧单层规格
  fill_pic     保留结构，但为缺图的属性补 skuPicUrl（用商品主图）→ 解决"映像编号错误"
用法：
  python3 repair_erp_item.py --num-iid <ID> --erp-code <code> --mode single_tier|fill_pic [--keep-title <原标题>]
"""
import json, os, sys, time, urllib.request

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erp_token.txt")
BASE = "https://erp.kuaidizs.cn"
_last = [0.0]

def post(path, body):
    now = time.time()
    wait = 1.2 - (now - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(BASE + path, data=json.dumps(body, ensure_ascii=False).encode(), method="POST")
    req.add_header("Content-Type", "application/json;charset=UTF-8")
    req.add_header("qnquerystring", open(TOKEN_FILE).read().strip())
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

def _price(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _jpeg_size(data):
    """从 JPEG 字节流解析宽高（找 SOF0/SOF2 段）"""
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i+1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h = (data[i+5] << 8) | data[i+6]
            w = (data[i+7] << 8) | data[i+8]
            return w, h
        seg_len = (data[i+2] << 8) | data[i+3]
        i += 2 + seg_len
    return None


def _img_ratio(url):
    """下载图片头部解析宽高比；失败返回 None（不拦截）"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-65535"})
        with urllib.request.urlopen(req, timeout=15) as r:
            head = r.read(65536)
        w, h = _jpeg_size(head)
        if w and h and h > 0:
            return w / h
    except Exception:
        pass
    return None


def repair(num_iid, erp_code, mode, keep_title=None):
    dto = query_detail(num_iid)
    if dto is None:
        return False, "详情拉取失败"
    if keep_title:
        dto["title"] = keep_title
    main_pic = (dto.get("picUrl") or (dto.get("itemImgs") or [""])[0] if dto.get("itemImgs") else "")
    if isinstance(main_pic, dict):
        main_pic = main_pic.get("url") or main_pic.get("src") or ""
    skus = dto.get("skus") or []
    changed = 0
    if mode == "fix_imgs":
        # 删除宽高比超限（<0.5 或 >32）的图（Shopee 校验"图像比率极其有限"）
        removed = 0
        for field in ("itemImgs", "descImageList"):
            lst = dto.get(field) or []
            keep = []
            for it in lst:
                url = it if isinstance(it, str) else (it.get("url") or "")
                ratio = _img_ratio(url)
                if ratio is not None and not (0.5 <= ratio <= 32):
                    removed += 1
                    continue
                keep.append(it)
            dto[field] = keep
        changed = removed
    if mode == "price_cap":
        # 删除极端价格 SKU，把 最高/最低 ≤ 7 倍 压进红线（保留尽量多主销规格）
        prices = [_price(s.get("price")) for s in skus]
        valid = [p for p in prices if p is not None]
        if valid:
            ratio = max(valid) / min(valid) if min(valid) > 0 else 1
            while ratio > 7.0 and len(skus) > 1:
                ps = [_price(s.get("price")) for s in skus]
                vp = [p for p in ps if p is not None]
                if not vp or min(vp) <= 0:
                    break
                mid = sum(vp) / len(vp)
                # 删偏离中位更远的一端（高价或低价）
                hi = max(vp)
                lo = min(vp)
                drop_hi = (hi - mid) >= (mid - lo)
                target_price = hi if drop_hi else lo
                idx = next((i for i, s in enumerate(skus) if _price(s.get("price")) == target_price), None)
                if idx is None:
                    break
                del skus[idx]
                ps = [_price(s.get("price")) for s in skus]
                vp = [p for p in ps if p is not None]
                if not vp or min(vp) <= 0:
                    break
                ratio = max(vp) / min(vp)
                changed += 1
        # 同步清理 skuPropertyList 中不再被引用的 valueId
        kept_vids = set()
        for s in skus:
            for a in (s.get("skuAttributesList") or []):
                if a.get("vid"):
                    kept_vids.add(str(a["vid"]))
        spl = dto.get("skuPropertyList") or []
        for prop in spl:
            vals = prop.get("propertyValueInfoList") or []
            prop["propertyValueInfoList"] = [v for v in vals if not v.get("valueId") or str(v["valueId"]) in kept_vids]
    else:
        for s in skus:
            attrs = s.get("skuAttributesList") or []
            if not attrs:
                continue
            if mode == "single_tier":
                # 保留第一个属性（优先 pid=1236 规格型号），删除其余层
                keep = [a for a in attrs if str(a.get("pid")) == "1236"]
                if not keep:
                    keep = [attrs[0]]
                s["skuAttributesList"] = keep
                changed += 1
            elif mode == "fill_pic":
                for a in attrs:
                    if not a.get("skuPicUrl") and main_pic:
                        a["skuPicUrl"] = main_pic
                        changed += 1
        if mode == "single_tier":
            # 同步清理 skuPropertyList：只保留 skus 仍在引用的 valueId；空 property 删除
            kept_vids = set()
            kept_pids = set()
            for s in skus:
                for a in (s.get("skuAttributesList") or []):
                    if a.get("vid"):
                        kept_vids.add(str(a["vid"]))
                    if a.get("pid"):
                        kept_pids.add(str(a["pid"]))
            spl = dto.get("skuPropertyList") or []
            new_spl = []
            for prop in spl:
                vals = prop.get("propertyValueInfoList") or []
                new_vals = [v for v in vals if not v.get("valueId") or str(v["valueId"]) in kept_vids]
                if new_vals and (not prop.get("propertyId") or str(prop["propertyId"]) in kept_pids):
                    prop["propertyValueInfoList"] = new_vals
                    new_spl.append(prop)
            dto["skuPropertyList"] = new_spl
        elif mode == "unify_pic":
            # 变体图统一为主图1（Shopee 要求 tier 选项图必须来自商品图集；
            # 1688 规格图不在主图集时触发"映像编号不等于选项编号/变体选项重复"）
            main_pic = None
            imgs = dto.get("itemImgs") or []
            if imgs:
                main_pic = imgs[0] if isinstance(imgs[0], str) else (imgs[0].get("url") or "")
            if main_pic:
                for s in skus:
                    if s.get("picUrl") != main_pic:
                        s["picUrl"] = main_pic
                        changed += 1
                    for a in (s.get("skuAttributesList") or []):
                        if a.get("skuPicUrl") != main_pic:
                            a["skuPicUrl"] = main_pic
                            changed += 1
                for prop in (dto.get("skuPropertyList") or []):
                    for v in (prop.get("propertyValueInfoList") or []):
                        if v.get("url") and v["url"] != main_pic:
                            v["url"] = main_pic
                            changed += 1
    st, resp = post("/item/center/updateErpItemByNumIid",
                    {"numIid": num_iid, "erpItemUpdateDTO": dto})
    if st != 200 or not resp.get("success"):
        return False, json.dumps(resp, ensure_ascii=False)[:300]
    time.sleep(2)
    chk = query_detail(num_iid)
    if not chk:
        return False, "提交成功但回读失败"
    chg = sum(1 for s in (chk.get("skus") or []) if len(s.get("skuAttributesList") or []) <= 1) if mode == "single_tier" else None
    return True, f"ok (修改SKU数={changed})"

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--num-iid", required=True)
    p.add_argument("--erp-code", required=True)
    p.add_argument("--mode", required=True, choices=["single_tier", "fill_pic", "price_cap", "fix_imgs", "unify_pic"])
    p.add_argument("--keep-title", default=None)
    a = p.parse_args()
    ok, msg = repair(a.num_iid, a.erp_code, a.mode, a.keep_title)
    print("OK " if ok else "FAIL", a.num_iid, a.erp_code, a.mode, "|", msg)

if __name__ == "__main__":
    main()
