#!/usr/bin/env python3
"""从 data/*.json 生成 history.csv、chart_price.svg、chart_stock.svg、index.html、README.md。

用法: python3 scripts/render.py

图表按「配置组」聚合：配置 = category + chip + cpuCores + gpuCores + memoryGB + storage。
折线图为每日快照时间序列（某天该配置出现/消失即断点）。
最近一天在售数量 TOP 12 配置组各一条线，其余聚合为「其他」线。
"""
import csv
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
MODELS = ['Mac Studio', 'Mac mini', 'MacBook Pro']
TOP_N = 12
PALETTE = ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2',
           '#db2777', '#65a30d', '#ea580c', '#4f46e5', '#0d9488', '#a16207', '#6b7280']


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


def config_key(r):
    """配置组唯一键：产品线 + 芯片 + CPU/GPU 核数 + 内存 + 硬盘。"""
    return (r.get('category') or '?', r.get('chip') or '?', r.get('cpuCores'),
            r.get('gpuCores'), r.get('memoryGB'), r.get('storage') or '?')


def config_label(key):
    """配置组显示标签：如 MacBook Pro M5 Pro 18/20 24GB/2TB；缺失字段用 ? 占位。"""
    cat, chip, cpu, gpu, mem, sto = key
    return (f"{cat} {chip} "
            f"{cpu if cpu is not None else '?'}/{gpu if gpu is not None else '?'} "
            f"{mem if mem is not None else '?'}GB/{sto}")


def series_by_config(rows):
    """按配置组聚合每日（在售最低价, 在售条目数）。

    排序规则：最近一天在售数量降序 → 历史总次数降序 → 标签字典序。
    TOP 12 各一条线，其余聚合为「其他」（价格取最低、数量求和）。
    """
    dates = sorted({r['date'] for r in rows})
    last = dates[-1] if dates else ''
    price_by = {d: {} for d in dates}
    count_by = {d: {} for d in dates}
    total_count = {}
    for r in rows:
        k = config_key(r)
        d = r['date']
        p = price_by[d].get(k)
        price_by[d][k] = r['price'] if p is None else min(p, r['price'])
        count_by[d][k] = count_by[d].get(k, 0) + 1
        total_count[k] = total_count.get(k, 0) + 1
    last_counts = count_by.get(last, {})
    keys = sorted(total_count,
                  key=lambda k: (-last_counts.get(k, 0), -total_count[k], config_label(k)))
    top, other = keys[:TOP_N], keys[TOP_N:]

    def pick(ks, agg):
        out = {}
        for k in ks:
            label = config_label(k)
            out[label] = {d: agg(price_by[d].get(k), count_by[d].get(k))
                          for d in dates if k in count_by[d]}
        return out

    series_p = pick(top, lambda p, c: p)
    series_c = pick(top, lambda p, c: c)
    if other:
        label = f'其他（{len(other)} 组）'
        series_p[label], series_c[label] = {}, {}
        for d in dates:
            ps = [price_by[d][k] for k in other if k in price_by[d]]
            if ps:
                series_p[label][d] = min(ps)
                series_c[label][d] = sum(count_by[d][k] for k in other if k in count_by[d])
    return dates, series_p, series_c


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


def line_chart(dates, series, title, y_label, out_path, fmt_money=True,
               width=1140, height=420):
    pad_l, pad_r, pad_t, pad_b = 78, 296, 52, 46
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
    # 折线（每种配置一个颜色；当日无在售即断点，不连线）
    for idx, (label, s) in enumerate(series.items()):
        color = PALETTE[idx % len(PALETTE)]
        pts = [(x(i), y(s[d])) for i, d in enumerate(dates) if d in s]
        if len(pts) == 1:
            svg.append(f'<circle cx="{pts[0][0]:.1f}" cy="{pts[0][1]:.1f}" r="4" fill="{color}"/>')
            continue
        seg = None
        for i, d in enumerate(dates):
            if d in s:
                seg = (seg or []) + [(x(i), y(s[d]))]
            else:
                if seg and len(seg) > 1:
                    svg.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>'
                               % (color, ' '.join(f'{a:.1f},{b:.1f}' for a, b in seg)))
                seg = None
        if seg and len(seg) > 1:
            svg.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>'
                       % (color, ' '.join(f'{a:.1f},{b:.1f}' for a, b in seg)))
    # 图例（右侧，带最新值）
    ly = pad_t + 6
    for idx, (label, s) in enumerate(series.items()):
        color = PALETTE[idx % len(PALETTE)]
        svg.append(f'<rect x="{width - pad_r + 10}" y="{ly}" width="10" height="10" rx="2" fill="{color}"/>')
        lastv = s.get(dates[-1]) if dates else None
        suffix = f'¥{lastv:,.0f}' if (fmt_money and lastv is not None) else (
            f'{lastv:,}' if lastv is not None else '—')
        svg.append(f'<text x="{width - pad_r + 26}" y="{ly + 9}" font-size="10" fill="#374151">'
                   f'{esc(label)} {suffix}</text>')
        ly += 20
    svg.append(f'<text x="{pad_l}" y="{height - 10}" font-size="10" fill="#9ca3af">{esc(y_label)}</text>')
    svg.append('</svg>')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(svg))
    return out_path


def item_sort_key(z):
    """产品线 → 芯片 → CPU/GPU → 内存 → 硬盘 → 价格，保证同配置相邻、顺序稳定。"""
    return (MODELS.index(z['category']) if z['category'] in MODELS else 9,
            z.get('chip') or '', z.get('cpuCores') or -1, z.get('gpuCores') or -1,
            z.get('memoryGB') or -1, z.get('storage') or '', z['price'])


def items_sorted(rows):
    last = max((r['date'] for r in rows), default='')
    items = [r for r in rows if r['date'] == last]
    items.sort(key=item_sort_key)
    return items


def cfg_text(r):
    return ' / '.join(x for x in [
        f"{r.get('cpuCores') or '?'}核CPU",
        f"{r.get('gpuCores') or '?'}核GPU",
        f"{r.get('memoryGB') or '?'}GB",
        r.get('storage') or '?',
        (f"{r['screenInch']}英寸" if r.get('screenInch') else ''),
    ] if x)


def latest_table(rows):
    # latest.md 输出当日全部在售条目（index.html 的 60 条上限在 main() 中单独控制）
    last = max((r['date'] for r in rows), default='')
    items = items_sorted(rows)
    lines = ['| 型号 | 芯片 | 配置 | 价格 | 链接 |', '|---|---|---|---|---|']
    for r in items:
        lines.append(f"| {r['category']} | {r.get('chip') or '?'} | {cfg_text(r)} | ¥{r['price']:,} | "
                     f"[商品]({r['url']}) |")
    return last, lines


def main():
    rows = load()
    if not rows:
        print('没有数据，先跑 scripts/scrape.py')
        return 1
    write_history(rows)
    dates, prices, counts = series_by_config(rows)
    line_chart(dates, prices, '苹果官翻 · 在售最低价走势（按配置组 TOP 12 + 其他）',
               '注：按配置分组，仅展示最近一天在售数量 TOP 12，其余聚合为「其他」；'
               '曲线断点表示当日该配置无在售翻新机。',
               os.path.join(ROOT, 'chart_price.svg'))
    line_chart(dates, counts, '苹果官翻 · 在售数量走势（按配置组 TOP 12 + 其他）',
               '注：数量 = 当日该配置组在售条目数；「其他」为 TOP 12 以外配置组的数量之和。',
               os.path.join(ROOT, 'chart_stock.svg'), fmt_money=False)
    last, table = latest_table(rows)
    with open(os.path.join(ROOT, 'latest.md'), 'w', encoding='utf-8') as f:
        f.write(f'### {last} 在售清单\n\n' + '\n'.join(table) + '\n')
    # index.html（静态，GitHub 直接可看；也可作为 GitHub Pages 首页）
    rows_html = ['<table><tr><th>型号</th><th>芯片</th><th>配置</th><th>价格</th><th>链接</th></tr>']
    for r in items_sorted(rows)[:60]:
        cfg = cfg_text(r)
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

## 图表怎么看

- 图表**按配置分组**：配置 = 产品线 + 芯片 + CPU/GPU 核数 + 内存 + 硬盘（如 <code>MacBook Pro M5 Pro 18/20 24GB/2TB</code>），不同颜色各一条折线。
- 为避免图例爆炸，只画**最近一天在售数量 TOP 12** 的配置组，其余配置聚合为一条灰色的「其他」线（价格取最低、数量求和）。TOP 12 每天可能轮换。
- <code>chart_price.svg</code> = 各配置组当日在售最低价；<code>chart_stock.svg</code> = 各配置组当日在售条目数。曲线断点表示当日该配置无在售翻新机。

## 价格走势（在售最低价）

![价格走势](chart_price.svg)

## 在售数量

![在售数量](chart_stock.svg)

## 最新在售清单

见 [latest.md](latest.md)（更新于 {last}）。

## 说明

- 官翻价为苹果官方定价，通常不变；波动主要来自**在售配置更替与补货/售罄**，因此同时记录价格与在售数量。
- 清单按 产品线 → 芯片 → CPU/GPU → 内存 → 硬盘 → 价格 排序，同配置相邻。
- 抓取：Tabbit Browser CLI 渲染页面 → 解析商品卡（价格格式 `RMB 15,599`）。
- 抓取脚本 <code>scripts/scrape.py</code>，渲染脚本 <code>scripts/render.py</code>；纯本地运行，无第三方依赖。
'''
    with open(os.path.join(ROOT, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)
    print(f'rendered: {len(rows)} rows, {len(dates)} days, {len(prices)} series, last={last}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
