# 数据格式契约 v1（冻结）

> 任何字段变更必须向后兼容新增；改名/删除/改语义属破坏性变更，需用户批准。生成物（chart_*.svg、index.html、latest.md、README.md）由脚本生成，不手工改。

## 1. 每日快照 `data/YYYY-MM-DD.json`

```json
{
  "date": "2026-11-06",
  "fetchedAt": "2026-11-06T18:42:11+08:00",
  "source": "apple.com.cn/shop/refurbished/mac",
  "count": 64,
  "items": [
    {
      "category": "Mac Studio",       // Mac Studio | Mac mini | MacBook Pro
      "model": "Mac Studio",           // 与 category 同值
      "chip": "M4 Max",                // 如 M4 / M4 Pro / M4 Max / M3 Ultra / M5
      "cpuCores": 14,                  // 整数或 null
      "gpuCores": 32,                  // 整数或 null
      "memoryGB": null,                // 整数或 null（详情页补全前可能为空）
      "storage": "",                   // 如 "1TB" / "512GB"，空串表示未知
      "screenInch": null,              // 仅 MacBook 有，整数或 null
      "port": "GbE",                   // "" | "GbE" | "10GbE"
      "price": 15599,                  // 人民币整数
      "title": "翻新 Mac Studio Apple M4 Max 芯片 (配备 14 核中央处理器和 32 核图形处理器)",
      "url": "https://www.apple.com.cn/shop/product/<id>/a?fnode=..."
    }
  ]
}
```

## 2. 汇总表 `history.csv`

列：`date,category,chip,cpuCores,gpuCores,memoryGB,storage,screenInch,port,price,title,url`

## 3. 唯一键

同一日期内按 `(商品 id, price)` 去重；商品 id 取自 `url` 中 `/shop/product/<id>/`。

## 4. 生成物

- `chart_price.svg`：各产品线每日在售最低价
- `chart_stock.svg`：各产品线每日在售数量
- `latest.md`：最新一日在售清单（表格）
- `index.html`：静态页面（同款图表 + 清单），GitHub Pages 首页
- `README.md`：含内嵌 SVG 与说明

## 5. 版本

- v1（2026-11-06）：初始冻结。后续只加字段不改已有字段。
