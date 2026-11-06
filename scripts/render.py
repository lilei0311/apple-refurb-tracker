#!/usr/bin/env python3
"""从 data/*.json 生成 history.csv、chart_price.svg、chart_stock.svg、index.html、README.md。

用法: python3 scripts/render.py
"""
import csv
import glob
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
MODELS = ['Mac Studio', 'Mac mini', 'MacBook Pro']
COLORS = {'Mac Studio': '#2563eb', 'Mac mini': '#059669', 'MacBook Pro': '#d97706'}


def load():
    rows = []
    for path in sorted(glob.glob(os.path.join(DATA, '*.json'))):
        with open(path, encoding='utf-8') as f:
            doc = json.load(f)
        for it in doc.get('items', []):
            it['date'] = doc.get('date') or os.path.basename(path)[:-5]
            rows.append(it)
    return rows


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def write_history(rows):
    path = os.path.join(ROOT, 'history.csv')
    cols = ['date', 'category', 'chip', 'cpuCores', 'gpuCores', 'memoryGB', 'storage',
            'screenInch', 'port', 'price', 'title', 'url']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in sorted(rows, key=lambda z: (z['date'], z['category'], z['price'])):
            w.writerow({k: r.get(k) for k in cols})
    return path


def series_by_date(rows):
    dates = sorted({r['date'] for r in rows})
    prices, counts = {}, {}
    for model in MODELS:
        prices[model], counts[model] = {}, {}
        for d in dates:
            vals = [r['price'] for r in rows if r['date'] == d and r['category'] == model]
            if vals:
                prices[model][d] = min(vals)
                counts[model][d] = len(vals)
    return dates, prices, counts


def line_chart(dates, series, title, y_label, out_path, fmt_money=True, width=920, height=380):
    pad_l, pad_r, pad_t, pad_b = 78, 130, 52, 46
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    vals = [v for s in series.values() for v in s.values()]
    if not vals or not dates:
        vmin, vmax = 0, 1
    else:
        vmin, vmax = min(vals), max(vals)
        span = max(vmax - vmin, vmax * 0.08, 1)
        vmin, vmax = vmin - span * 0.15, vmax + span * 0.15
    n = max(len(dates) - 1, 1)

    def x(i):
        return pad_l + (plot_w * i / n if len(dates) > 1 else plot_w / 2)

    def y(v):
        return pad_t + plot_h * (1 - (v - vmin) / (vmax - vmin))

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<text x="{pad_l}" y="26" font-size="15" font-weight="600" fill="#111827">{esc(title)}</text>',
           f'<text x="{width - pad_r + 8}" y="26" font-size="11" fill="#6b7280">更新 {dates[-1] if dates else "-"}</text>']
    # y 网格
    steps = 5
    for k in range(steps + 1):
        v = vmin + (vmax - vmin) * k / steps
        yy = y(v)
        label = f'¥{v:,.0f}' if fmt_money else f'{v:,.0f}'
        svg.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{pad_l + plot_w}" y2="{yy:.1f}" stroke="#eef2f7"/>')
        svg.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" font-size="10" fill="#6b7280" text-anchor="end">{label}</text>')
    # x 标签
    step = max(1, len(dates) // 8)
    for i, d in enumerate(dates):
        if i % step == 0 or i == len(dates) - 1:
            svg.append(f'<text x="{x(i):.1f}" y="{pad_t + plot_h + 20}" font-size="10" fill="#6b7280" '
                       f'text-anchor="middle">{esc(d[5:])}</text>')
    # 折线
    for model, s in series.items():
        pts = [(x(i), y(s[d])) for i, d in enumerate(dates) if d in s]
        if len(pts) == 1:
            svg.append(f'<circle cx="{pts[0][0]:.1f}" cy="{pts[0][1]:.1f}" r="4" fill="{COLORS[model]}"/>')
            continue
        seg = None
        for i, d in enumerate(dates):
            if d in s:
                seg = (seg or []) + [(x(i), y(s[d]))]
            else:
                if seg and len(seg) > 1:
                    svg.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>'
                               % (COLORS[model], ' '.join(f'{a:.1f},{b:.1f}' for a, b in seg)))
                seg = None
        if seg and len(seg) > 1:
            svg.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>'
                       % (COLORS[model], ' '.join(f'{a:.1f},{b:.1f}' for a, b in seg)))
        svg.append(f'<text x="{pad_l + 10}" y="{pad_t + plot_h - 6}" font-size="1" fill="none">{esc(model)}</text>')
    # 图例
    ly = pad_t + 6
    for model in MODELS:
        svg.append(f'<rect x="{width - pad_r + 10}" y="{ly}" width="10" height="10" rx="2" fill="{COLORS[model]}"/>')
        last = series.get(model, {})
        lastv = last.get(dates[-1]) if dates else None
        text = f'{model} ¥{lastv:,.0f}' if lastv else f'{model} —'
        svg.append(f'<text x="{width - pad_r + 26}" y="{ly + 9}" font-size="10" fill="#374151">{esc(text)}</text>')
        ly += 20
    svg.append(f'<text x="{pad_l}" y="{height - 10}" font-size="10" fill="#9ca3af">{esc(y_label)}</text>')
    svg.append('</svg>')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(svg))
    return out_path


def items_sorted(rows):
    last = max((r['date'] for r in rows), default='')
    items = [r for r in rows if r['date'] == last]
    items.sort(key=lambda z: (MODELS.index(z['category']) if z['category'] in MODELS else 9, z['price']))
    return items


def latest_table(rows, limit=30):
    last = max((r['date'] for r in rows), default='')
    items = [r for r in rows if r['date'] == last]
    items.sort(key=lambda z: (MODELS.index(z['category']) if z['category'] in MODELS else 9, z['price']))
    lines = ['| 型号 | 芯片 | 配置 | 价格 | 链接 |', '|---|---|---|---|---|']
    for r in items[:limit]:
        cfg = ' / '.join(x for x in [
            f"{r.get('cpuCores') or '?'}核CPU",
            f"{r.get('gpuCores') or '?'}核GPU",
            f"{r.get('memoryGB') or '?'}GB",
            r.get('storage') or '?',
            (f"{r['screenInch']}英寸" if r.get('screenInch') else ''),
        ] if x)
        lines.append(f"| {r['category']} | {r.get('chip') or '?'} | {cfg} | ¥{r['price']:,} | "
                     f"[商品]({r['url']}) |")
    return last, lines


def main():
    rows = load()
    if not rows:
        print('没有数据，先跑 scripts/scrape.py')
        return 1
    write_history(rows)
    dates, prices, counts = series_by_date(rows)
    line_chart(dates, prices, '苹果官翻 · 在售最低价走势（按产品线）',
               '注：官翻价格为苹果官方定价；曲线断点表示当日该产品线无在售翻新机。',
               os.path.join(ROOT, 'chart_price.svg'))
    line_chart(dates, counts, '苹果官翻 · 在售数量走势（按产品线）',
               '注：数量 = 当日该产品线在售翻新机条目数，反映补货/售罄节奏。',
               os.path.join(ROOT, 'chart_stock.svg'), fmt_money=False)
    last, table = latest_table(rows)
    with open(os.path.join(ROOT, 'latest.md'), 'w', encoding='utf-8') as f:
        f.write(f'### {last} 在售清单\n\n' + '\n'.join(table) + '\n')
    # index.html（静态，GitHub 直接可看；也可作为 GitHub Pages 首页）
    rows_html = ['<table><tr><th>型号</th><th>芯片</th><th>配置</th><th>价格</th><th>链接</th></tr>']
    for r in items_sorted(rows)[:60]:
        cfg = ' / '.join(x for x in [
            f"{r.get('cpuCores') or '?'}核CPU",
            f"{r.get('gpuCores') or '?'}核GPU",
            f"{r.get('memoryGB') or '?'}GB",
            r.get('storage') or '?',
            (f"{r['screenInch']}英寸" if r.get('screenInch') else ''),
        ] if x)
        rows_html.append(f"<tr><td>{esc(r['category'])}</td><td>{esc(r.get('chip') or '?')}</td>"
                         f"<td>{esc(cfg)}</td><td>¥{r['price']:,}</td>"
                         f"<td><a href='{esc(r['url'])}'>商品</a></td></tr>")
    rows_html.append('</table>')
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>苹果官翻库存追踪</title>
<style>body{{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#111827}}
img{{max-width:100%;border:1px solid #e5e7eb;border-radius:10px;margin:12px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #e5e7eb;padding:6px 8px;text-align:left}}
th{{background:#f9fafb}}code{{background:#f3f4f6;padding:1px 4px;border-radius:4px}}</style></head>
<body><h1>苹果中国官翻库存追踪</h1>
<p>每日 19:00 自动抓取 Mac Studio / Mac mini / MacBook Pro 的苹果官方翻新在售机型与价格。数据见 <a href="history.csv">history.csv</a> 与 <code>data/</code>。</p>
<h2>价格走势</h2><img src="chart_price.svg" alt="价格走势">
<h2>在售数量</h2><img src="chart_stock.svg" alt="在售数量">
<h2>最新在售清单</h2>
{''.join(rows_html)}
</body></html>"""
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    readme = f'''# 苹果中国官翻库存追踪（Mac Studio / Mac mini / MacBook Pro）

每日 **19:00** 自动抓取 [苹果中国官方翻新商店](https://www.apple.com.cn/shop/refurbished/mac) 的在售机型与价格，记录成时间序列。

- 数据：<code>data/YYYY-MM-DD.json</code>（每日快照）、<code>history.csv</code>（汇总）
- 生成物：<code>chart_price.svg</code> / <code>chart_stock.svg</code>（GitHub 内嵌渲染）、<code>index.html</code>

## 价格走势（在售最低价）

![价格走势](chart_price.svg)

## 在售数量

![在售数量](chart_stock.svg)

## 最新在售清单

见 [latest.md](latest.md)（更新于 {last}）。

## 说明

- 官翻价为苹果官方定价，通常不变；波动主要来自**在售型号更替与补货/售罄**，因此同时记录价格与在售数量。
- 抓取：Tabbit Browser CLI 渲染页面 → 解析商品卡（价格格式 `RMB 15,599`）。
- 抓取脚本 <code>scripts/scrape.py</code>，渲染脚本 <code>scripts/render.py</code>；纯本地运行，无第三方依赖。
'''
    with open(os.path.join(ROOT, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)
    print(f'rendered: {len(rows)} rows, {len(dates)} days, last={last}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
