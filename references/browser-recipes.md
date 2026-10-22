# bu 可复用操作片段

> 在 `mac_computer_use_tool(plane="bu")` 的 cell 里使用，`import aha_browser_use as bu`。
> 选择器是实测值，ERP/遨虾改版会失效；失效时改用 `bu.find("文本", search_type="interaction")` 重新定位 ref，不要死磕 CSS。
> `bu.js()` 只接受表达式字符串：用普通 `(function(){...})()` IIFE，**不要用箭头函数**（会报 must be JSON serializable）；返回值必须可序列化；串内避免字面 `\n`。

## 目录
- 1. 恢复榜单序列（导航→切国家→切类目→翻页）
- 2. 点"找同款"并提取结果页1688 offer链接
- 3. 批量链接采集并读取成功/失败数
- 4. 公共采集箱对账（货源ID）
- 5. 全选+勾选店铺+提交铺货
- 6. 发布记录状态统计与失败原因

## 1. 恢复榜单序列

`back` 会丢国家/类目/翻页状态，每次进入结果页返回后都重跑本序列。国家/类目用 `bu.find` 文本点击兜底，避免写死易变CSS。

```python
import aha_browser_use as bu, time
RANK_URL = "https://aibuy.1688.com/landingpage/outer-rank-similar.html?platformCode=Shopee_ZX&ranking=103&bizType=ERP&customerId=kdzhushou&lang=zh&tabCode=overseas_soaring_list"
def restore(country="马来西亚", category_kw="Kelengkapan", page=2):
    bu.navigate(RANK_URL); bu.wait_for_load(timeout=15); time.sleep(2)
    m = bu.find(country, search_type="interaction", limit=1)
    if m.first: bu.click(m.first); time.sleep(2)
    # 类目：优先按马来语/英文关键词点 listItem；失效时改 bu.find(类目中文名)
    bu.js("(function(){var el=Array.from(document.querySelectorAll('div.listItem--_3EqB62a')).find(function(e){return e.textContent.indexOf('"+category_kw+"')>=0});if(el)el.click();})()")
    time.sleep(2)
    bu.js("(function(){var lis=document.querySelectorAll('.tablePagination--K5FBzz_Y li');for(var i=0;i<lis.length;i++){if(lis[i].textContent.trim()=='"+str(page)+"'){lis[i].click();return;}}})()")
    time.sleep(2)
```

## 2. 点"找同款"并提取结果页offer链接

`idx` 是当前页第几个"找同款"按钮（从0起）。点击后结果页列出候选，**人工挑选匹配项**，不要自动取第一条。

```python
import aha_browser_use as bu, time
def pick_peer(idx):
    bu.js("(function(){var bs=Array.from(document.querySelectorAll('button')).filter(function(b){return b.textContent.trim()==='找同款'});if(bs["+str(idx)+"]){bs["+str(idx)+"].click();return 'ok';}return 'nf';})()")
    time.sleep(3)
    for x in bu.read_all("a", fields=["text","href"], limit=10):
        h = x.get("href","") or ""
        if "detail.1688.com/offer" in h:
            print(x.get("text","")[:32], "=>", h.split("?")[0])
```

## 3. 批量链接采集并读结果

进 `#/cross/moving/productCollection`，切"链接采集"tab；textarea 粘贴（Enter换行），点"开始采集"。

```python
import aha_browser_use as bu, time
urls = [
 "https://detail.1688.com/offer/897422308317.html",
 # ... 追加全部offer
]
m = bu.find("请输入产品链接", search_type="interaction", limit=1)
bu.type(m.first, "\n".join(urls), submit=False); time.sleep(1)
go = bu.find("开始采集", search_type="interaction", limit=1)
bu.click(go.first); time.sleep(15)
print(bu.js("(function(){var m=document.body.innerText.match(/本次共采集[^\\n]*/);return m?m[0]:'pending';})()"))
```

## 4. 公共采集箱对账

进 `#/cross/moving/sharedGoods`，核对条数与货源ID是否等于采集清单。

```python
bu.navigate("https://erp.kuaidizs.cn/index.html#/cross/moving/sharedGoods"); time.sleep(4)
print(bu.js("(function(){var m=document.body.innerText.match(/共\\d+条/);return m?m[0]:'?';})()"))
print(bu.js("(function(){var m=document.body.innerText.match(/货源ID:\\s*\\d+/g);return m?m.join(', '):'none';})()"))
```

## 5. 全选+勾选店铺+提交铺货

提交前**人工确认店铺、结算价模板、库存来源、非预售**。配置窗沿用已保存模板直接"保存"，回到列表再点"开始铺货"。

```python
import aha_browser_use as bu, time
# 全选商品行
print(bu.js("(function(){var cbs=Array.from(document.querySelectorAll('input[type=checkbox]')).filter(function(c){var r=c.closest('tr');return r&&r.textContent.indexOf('货源ID')>=0});cbs.forEach(function(c){if(!c.checked)c.click();});return 'checked '+cbs.length;})()"))
btn = bu.find("铺货至Shopee轻出海", search_type="interaction", limit=1); bu.click(btn.first); time.sleep(3)
shop = bu.find("轻出海", search_type="interaction", limit=1); bu.click(shop.first); time.sleep(1)
print(bu.js("(function(){var m=document.body.innerText.match(/已选\\s*\\d+\\s*个店铺/);return m?m[0]:'na';})()"))
# 配置窗沿用模板：点可见"保存"
bu.js("(function(){var bs=Array.from(document.querySelectorAll('button')).filter(function(x){return x.offsetParent!==null&&x.textContent.trim()==='保存'});if(bs.length)bs[bs.length-1].click();})()")
time.sleep(2)
start = bu.find("开始铺货", search_type="interaction", limit=1); bu.click(start.first); time.sleep(6)
print(bu.js("(function(){var m=document.body.innerText.match(/已提交\\s*\\d+\\s*个商品[^\\n]*/);return m?m[0]:'pending';})()"))
```

## 6. 发布记录状态统计与失败原因

进 `#/cross/fast-upload/shopee-light-record`。按货源ID归类；中间态不计成功。

```python
import aha_browser_use as bu, time
bu.navigate("https://erp.kuaidizs.cn/index.html#/cross/fast-upload/shopee-light-record"); time.sleep(8)
print(bu.js("(function(){var rows=Array.from(document.querySelectorAll('table tbody tr'));var cnt={};var fail=[];for(var i=0;i<rows.length;i++){var t=rows[i].innerText.replace(/\\s+/g,' ');var idm=t.match(/\\d{11}/);var sm=t.match(/发布中|审核中|发布成功|发布失败/);if(!idm)continue;var s=sm?sm[0]:'?';cnt[s]=(cnt[s]||0)+1;if(s==='发布失败'){var f=t.match(/发布失败[\\s\\S]{0,80}/);fail.push(idm[0]+': '+(f?f[0]:'?'));}}return JSON.stringify(cnt)+'\\n'+fail.join('\\n');})()"))
```

- 状态词：`发布中` `审核中` `排队中`=中间态；`发布成功`/`发布失败`=终态。
- 失败文本整句抄录，对照 selection-rules.md 第五节归因。
- 终态异步：首次多为审核中，记录快照后告知用户稍后刷新，不要把审核中算作成功。
