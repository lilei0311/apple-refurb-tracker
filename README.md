# 苹果中国官翻库存追踪（Mac Studio / Mac mini / MacBook Pro）

每日 **19:00** 自动抓取 [苹果中国官方翻新商店](https://www.apple.com.cn/shop/refurbished/mac) 的在售机型与价格，记录成时间序列。

- 数据：<code>data/YYYY-MM-DD.json</code>（每日快照）、<code>history.csv</code>（汇总）
- 生成物：<code>chart_price.svg</code> / <code>chart_stock.svg</code>（GitHub 内嵌渲染）、<code>index.html</code>

## 价格走势（在售最低价）

![价格走势](chart_price.svg)

## 在售数量

![在售数量](chart_stock.svg)

## 最新在售清单

见 [latest.md](latest.md)（更新于 2026-11-06）。

## 说明

- 官翻价为苹果官方定价，通常不变；波动主要来自**在售型号更替与补货/售罄**，因此同时记录价格与在售数量。
- 抓取：Tabbit Browser CLI 渲染页面 → 解析商品卡（价格格式 `RMB 15,599`）。
- 抓取脚本 <code>scripts/scrape.py</code>，渲染脚本 <code>scripts/render.py</code>；纯本地运行，无第三方依赖。
