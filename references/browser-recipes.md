# bu 可复用操作片段

> 在 `mac_computer_use_tool(plane="bu")` 的 cell 里使用，`import aha_browser_use as bu`。
> 选择器是实测值，ERP/遨虾改版会失效；失效时改用 `bu.find("文本", search_type="interaction")` 重新定位 ref，不要死磕 CSS。
> `bu.js()` 只接受表达式字符串：用普通 `(function(){...})()` IIFE，**不要用箭头函数**（会报 must be JSON serializable）；返回值必须可序列化；串内避免字面 `\n`。
>
> **第1/2节是兜底**：Step1/2 默认走 `scripts/aibuy_rank_client.py` 只读接口（见 api-candidates.md）；仅当接口报错/改版/风控时，才用下面浏览器流程切榜、点找同款。第3-7节同样是兜底：Step3-6 默认走 `scripts/erp_api_client.py` 接口（见 erp-api.md，含 collect/distribute 写操作）；仅当接口失效时才用浏览器流程。

## 目录
- 1.【兜底】恢复榜单序列（导航→切国家→切类目→翻页）
- 2.【兜底】点"找同款"并提取结果页1688 offer链接
- 3. 批量链接采集并读取成功/失败数
- 4. 公共采集箱对账（货源ID）
- 5. 全选+勾选店铺+提交铺货
- 6. 发布记录状态统计与失败原因

## 1.【兜底·接口失效时】恢复榜单序列

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

## 2.【兜底·接口失效时】点"找同款"并提取结果页offer链接

`idx` 是当前页第几个"找同款"按钮（从0起）。点击后结果页列出候选，由 AI 按 selection-rules.md 第三节同类/月销/评分规则自动挑最优，不要盲取第一条。

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

**关键坑：默认"未认领"筛选会隐藏已自动认领的商品。** 新采集商品常已被自动认领，默认只看未认领会显示"共0条"，不是没采到。先删掉顶部"未认领"筛选tag（点其×），再查询，才能看到全部（可能上百条）。

```python
import aha_browser_use as bu, time
# 删除"未认领"筛选tag（找选中项关闭按钮）
bu.js("(function(){var c=document.querySelector('.ant-select-selection-item-content');if(!c)return;var item=c.closest('.ant-select-selection-overflow-item');var x=item&&item.querySelector('svg,button,i');if(x)x.parentNode.click();})()")
time.sleep(1)
q=bu.find("查询",search_type="interaction",limit=1); bu.click(q.first); time.sleep(3)
```

```python
bu.navigate("https://erp.kuaidizs.cn/index.html#/cross/moving/sharedGoods"); time.sleep(4)
print(bu.js("(function(){var m=document.body.innerText.match(/共\\d+条/);return m?m[0]:'?';})()"))
print(bu.js("(function(){var m=document.body.innerText.match(/货源ID:\\s*\\d+/g);return m?m.join(', '):'none';})()"))
```

## 5. 【兜底·接口失效时】勾选本次清单商品+自动选店铺+提交铺货（全自动，不暂停问人）

> 默认走 `scripts/erp_api_client.py distribute`（接口直连，更快更准）；本节约在接口报错/改版时使用。目标店铺默认=首个轻出海商户店（`shopType=SHOPEE_MERCHANT`），与接口逻辑一致。

只勾选 Step2 清单内的货源ID行，**禁止全选采集箱历史商品**。店铺唯一直接勾；多店铺取列表第一个（默认/已绑定轻出海店铺），记录所选店铺名。结算价模板、库存"使用商品来源"、非预售沿用 ERP 已保存配置，不重算、不询问。仅登录/验证码/支付弹窗才转人工接管。

> **操作坑（实测）：公共采集箱翻页会丢失勾选状态**——第1页勾的10个，翻到第2页后第1页勾选全部清空。解决方案：① 优先改每页显示条数为50/100条（底部分页size-changer），让本次商品在同一页内勾选；② 若改不了条数，分两批提交：第1页勾10个→铺货→回来勾第2页→再铺货。不要试图翻页跨页勾选。
>
> **搜索定位法**：采集箱商品多时，用顶部"货源ID"输入框逐个搜ID→点查询→勾选该行→铺货，比翻页可靠。注意搜完一个后要先点"重置"清空搜索条件再搜下一个。

```python
import aha_browser_use as bu, time
TARGETS = ["681683584352"]  # 替换为本次 Step2 的货源ID/offerId 清单
# 只勾选命中本次清单的行，不碰历史商品
print(bu.js("(function(){var rows=Array.from(document.querySelectorAll('table tbody tr'));var n=0;for(var i=0;i<rows.length;i++){var t=rows[i].innerText;var hit="+str(TARGETS)+".some(function(id){return t.indexOf(id)>=0;});if(hit){var cb=rows[i].querySelector('input[type=checkbox]');if(cb&&!cb.checked){cb.click();n++;}}}return 'checked '+n;})()"))
btn = bu.find("铺货至Shopee轻出海", search_type="interaction", limit=1); bu.click(btn.first); time.sleep(3)
# 自动勾选第一个轻出海店铺（唯一店铺直接勾；多店铺取列表首个）
bu.js("(function(){var mod=document.querySelector('.ant-modal-body')||document.body;var cbs=mod.querySelectorAll('input[type=checkbox]');for(var i=0;i<cbs.length;i++){if(cbs[i].closest('label,div')&&cbs[i].offsetParent!==null&&!cbs[i].checked){cbs[i].click();break;}}})()")
time.sleep(1)
print(bu.js("(function(){var m=document.body.innerText.match(/已选\\s*\\d+\\s*个店铺/);return m?m[0]:'na';})()"))
# 沿用已保存模板，直接点"开始铺货"
start = bu.find("开始铺货", search_type="interaction", limit=1); bu.click(start.first); time.sleep(6)
print(bu.js("(function(){var m=document.body.innerText.match(/已提交\\s*\\d+\\s*个商品[^\\n]*/);return m?m[0]:'pending';})()"))
```

## 6. 发布记录状态统计与失败原因

进 `#/cross/fast-upload/shopee-light-record`。按货源ID归类；中间态不计成功。

```python
import aha_browser_use as bu, time
bu.navigate("https://erp.kuaidizs.cn/index.html#/cross/fast-upload/shopee-light-record"); time.sleep(8)
print(bu.js("(function(){var rows=Array.from(document.querySelectorAll('table tbody tr'));var cnt={};var fail=[];for(var i=0;i<rows.length;i++){var t=rows[i].innerText.replace(/\\s+/g,' ');var idm=t.match(/\\d{10,}/);var sm=t.match(/发布中|审核中|发布成功|发布失败/);if(!idm)continue;var s=sm?sm[0]:'?';cnt[s]=(cnt[s]||0)+1;if(s==='发布失败'){var f=t.match(/发布失败[\\s\\S]{0,80}/);fail.push(idm[0]+': '+(f?f[0]:'?'));}}return JSON.stringify(cnt)+'\\n'+fail.join('\\n');})()"))
```

- 状态词：`发布中` `审核中` `排队中`=中间态；`发布成功`/`发布失败`=终态。
- 失败文本整句抄录，对照 selection-rules.md 第五节归因。
- 终态异步：首次多为审核中，记录快照后告知用户稍后刷新，不要把审核中算作成功。

## 7. Step4.5 发布记录去重比对

进 `#/cross/fast-upload/shopee-light-record`，把本次候选货源ID与发布记录全部历史比对；**任意状态（成功/审核中/发布中/排队中/失败）都视为已提交过，命中即剔除**，中间态也算占用。记录有分页时逐页翻完再比。

```python
import aha_browser_use as bu, time
TARGETS = ["681683584352"]  # 本次 Step2 清单
bu.navigate("https://erp.kuaidizs.cn/index.html#/cross/fast-upload/shopee-light-record"); time.sleep(8)
# 逐页收集已提交过的货源ID（含中间态），翻到末页
occupied = set()
while True:
    ids = bu.js("(function(){var rows=Array.from(document.querySelectorAll('table tbody tr'));var s=new Set();for(var i=0;i<rows.length;i++){var m=rows[i].innerText.match(/\\d{10,}/);if(m)s.add(m[0]);}return Array.from(s);})()")
    occupied.update(ids or [])
    nxt = bu.find("下一页", search_type="interaction", limit=1)
    if not nxt.first or bu.js("(function(){var b=Array.from(document.querySelectorAll('li,button,a')).find(function(x){return x.textContent.trim()==='下一页';});return b&&b.className.indexOf('disabled')>=0;})()"):
        break
    bu.click(nxt.first); time.sleep(3)
drop = [t for t in TARGETS if t in occupied]
keep = [t for t in TARGETS if t not in occupied]
print("OCCUPIED_DROP=", drop)
print("KEEP=", keep)
```

- 再叠加本地台账 `scripts/published_ledger.py check --ids <逗号分隔>`，两道都放行才进 Step5。
- 提交成功后 `published_ledger.py append --ids ...` 写回台账。
