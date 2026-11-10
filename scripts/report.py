#!/usr/bin/env python3
"""从每日快照生成 ≤8 行的中文简报（stdout 只输出简报正文）。

用法:
  python3 scripts/report.py [--data-dir DIR]

对比口径：今日 = date 最大的快照；基准 = 最近一个早于今日的快照（非硬性"昨天"）。
配置聚合：配置 = category + chip + cpuCores + gpuCores + memoryGB + storage（缺字段用 ?）。
"""
import argparse
import glob
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(ROOT, 'data')
MODELS = ['Mac Studio', 'Mac mini', 'MacBook Pro']
MAX_LIST = 5  # 新上架/下架最多展示的条数
MIN_MAJOR_CHANGE = 2  # 配置级变化达到该数量才算"明显"（可调，但默认 2）


def parse_date(s):
    try:
        return date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def fmt_money(v):
    return f"¥{v:,}" if isinstance(v, (int, float)) else '?'


def config_key(it):
    """配置唯一键：产品线 + 芯片 + CPU/GPU 核数 + 内存 + 硬盘；缺字段用 ?。"""
    def num(v):
        return v if v is not None else '?'
    return (it.get('category') or '?', it.get('chip') or '?', num(it.get('cpuCores')),
            num(it.get('gpuCores')), num(it.get('memoryGB')), it.get('storage') or '?')


def config_label(key):
    """配置显示标签，如 Mac Studio M4 Max 14/32 36GB/512GB。"""
    cat, chip, cpu, gpu, mem, sto = key
    return f"{cat} {chip} {cpu}/{gpu} {mem}GB/{sto}"


def sort_key(key):
    """稳定的配置排序：产品线 → 芯片 → CPU/GPU → 内存 → 硬盘。"""
    cat, chip, cpu, gpu, mem, sto = key
    return (MODELS.index(cat) if cat in MODELS else 9, str(chip),
            cpu if isinstance(cpu, (int, float)) else -1,
            gpu if isinstance(gpu, (int, float)) else -1,
            mem if isinstance(mem, (int, float)) else -1, str(sto))


def group_by_config(items):
    """按配置聚合：返回 key -> {'count': n, 'min': 最低价, 'max': 最高价}。"""
    out = {}
    for it in items:
        k = config_key(it)
        g = out.setdefault(k, {'count': 0, 'min': None, 'max': None})
        g['count'] += 1
        p = it.get('price')
        if isinstance(p, (int, float)):
            g['min'] = p if g['min'] is None else min(g['min'], p)
            g['max'] = p if g['max'] is None else max(g['max'], p)
    return out


def model_counts(grouped):
    """型号级聚合：型号键 = (category, chip)，型号条数 = 该型号下所有配置的 count 之和。"""
    counts = {}
    for (cat, chip, _cpu, _gpu, _mem, _sto), g in grouped.items():
        key = (cat, chip)
        counts[key] = counts.get(key, 0) + g['count']
    return counts


def model_list(models):
    """型号显示名列表（category + ' ' + chip），最多列 2 个，多了写"等共 N 款"。"""
    names = [f"{cat} {chip}" for cat, chip in sorted(models)]
    txt = '、'.join(names[:2])
    if len(names) > 2:
        txt += f" 等共 {len(names)} 款"
    return txt


def price_text(g):
    """配置价格区间；只有一条/单一价格时只写一个价。"""
    lo, hi = g['min'], g['max']
    if lo is None:
        return '价格未知'
    if lo == hi:
        return fmt_money(lo)
    return f"{fmt_money(lo)}~{hi:,}"


def load_snapshots(data_dir):
    """读取 data-dir 下所有 *.json，返回 [(date_str, items, error)]，按 date 排序。

    损坏/非 JSON 文件不抛出，记为带 error 的条目。
    """
    snaps = []
    for path in sorted(glob.glob(os.path.join(data_dir, '*.json'))):
        dstr = os.path.basename(path)[:-5]
        try:
            with open(path, encoding='utf-8') as f:
                doc = json.load(f)
            d = parse_date(doc.get('date')) or parse_date(dstr)
            dstr = d.isoformat() if d else dstr
            items = doc.get('items')
            snaps.append((dstr, items if isinstance(items, list) else [], None))
        except Exception as e:  # noqa: BLE001 - 降级优先，不让单文件拖垮简报
            snaps.append((dstr, [], f'{type(e).__name__}: {e}'))
    # 同一 date 多次出现时保留最后读到的（文件名排序靠后者覆盖）
    by_date = {}
    for dstr, items, err in snaps:
        if dstr not in by_date or not err:
            by_date[dstr] = (items, err)
    return sorted((d, it, er) for d, (it, er) in by_date.items())


def category_counts(items):
    counts = {}
    for it in items:
        counts[it.get('category') or '?'] = counts.get(it.get('category') or '?', 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def build_report(data_dir):
    if not os.path.isdir(data_dir):
        return [f"数据目录不可读：{data_dir}（请先确认路径，或运行 scripts/scrape.py 抓取）"]

    snaps = load_snapshots(data_dir)
    if not snaps:
        return [f"数据目录 {data_dir} 暂无快照，请先运行 scripts/scrape.py 抓取。"]

    broken = [d for d, _, err in snaps if err]
    today_str, today_items, _ = snaps[-1]
    today = parse_date(today_str)
    base_str, base_items = None, None
    for dstr, items, err in reversed(snaps[:-1]):
        if not err:
            base_str, base_items = dstr, items
            break

    cat_txt = ' / '.join(f"{c} {n} 条" for c, n in category_counts(today_items)) or '无在售条目'

    if base_str is None:
        # 基线日：只有 1 天数据，明确说明、不编造
        lines = [
            f"**{today_str[5:]}** 在售 {len(today_items)} 条（按条数降序）：{cat_txt}（基线日，无对比）",
            '新上架：无对比数据（基线日）',
            '下架：无对比数据（基线日）',
            '价格变化：无对比数据（基线日）',
            '判断：平稳（基线日，待次日数据对比）',
        ]
    else:
        base = parse_date(base_str)
        gap = (today - base).days if (today and base) else None
        base_note = f"对比基准：{base_str[5:]}" + (f"，间隔 {gap} 天" if gap and gap > 1 else '')

        cur = group_by_config(today_items)
        prev = group_by_config(base_items)
        new_keys = sorted(set(cur) - set(prev), key=sort_key)
        gone_keys = sorted(set(prev) - set(cur), key=sort_key)

        def listing(keys, with_price):
            parts = []
            for k in keys[:MAX_LIST]:
                txt = config_label(k)
                if with_price:
                    g = cur[k]
                    txt += f" {price_text(g)}"
                    if g['count'] > 1:
                        txt += f"（{g['count']} 条）"
                parts.append(txt)
            if len(keys) > MAX_LIST:
                parts.append(f"等共 {len(keys)} 款")
            return '；'.join(parts) if parts else '无'

        changes = []
        for k in sorted(set(cur) & set(prev), key=sort_key):
            a, b = prev[k]['min'], cur[k]['min']
            if a is not None and b is not None and a != b:
                diff = b - a
                word = '↑' if diff > 0 else '↓'
                changes.append(f"{config_label(k)} {fmt_money(a)}→{fmt_money(b)}（{word} {abs(diff):,}）")
        if len(changes) > MAX_LIST:
            changes = changes[:MAX_LIST] + [f"等共 {len(changes)} 款"]
        change_txt = '；'.join(changes) if changes else '无'

        # 一句话判断：先型号级（型号在售归零/新上架 = 强信号），再配置级（数量 ≥2 才算明显）
        cur_mc = model_counts(cur)
        prev_mc = model_counts(prev)
        vanished_models = sorted(k for k in prev_mc if cur_mc.get(k, 0) == 0)
        appeared_models = sorted(k for k in cur_mc if prev_mc.get(k, 0) == 0)

        note = None
        if vanished_models or appeared_models:
            if len(appeared_models) > len(vanished_models):
                verdict = '偏补货'
                note = f"{model_list(appeared_models)} 型号新上架"
            elif len(vanished_models) > len(appeared_models):
                verdict = '偏售罄'
                note = f"{model_list(vanished_models)} 型号在售归零"
            else:
                verdict = '平稳'
                note = f"{model_list(vanished_models + appeared_models)} 型号有进出"
        else:
            if len(new_keys) >= MIN_MAJOR_CHANGE and len(new_keys) > len(gone_keys):
                verdict = '偏补货'
            elif len(gone_keys) >= MIN_MAJOR_CHANGE and len(gone_keys) > len(new_keys):
                verdict = '偏售罄'
            else:
                verdict = '平稳'
                if new_keys or gone_keys:
                    note = '配置小幅变动'
                elif changes:
                    note = '价格有变动'

        extra = []
        if new_keys:
            extra.append(f"新上架 {len(new_keys)} 款")
        if gone_keys:
            extra.append(f"下架 {len(gone_keys)} 款")
        if changes:
            extra.append(f"{len(changes)} 款调价")
        if note is None:
            reason = '，'.join(extra) if extra else '配置与价格均无变化'
        elif note in ('配置小幅变动', '价格有变动'):
            reason = note + ('：' + '，'.join(extra) if extra else '')
        else:  # 型号级说明：逗号衔接，保留原计数信息
            reason = note + ('，' + '，'.join(extra) if extra else '')

        lines = [
            f"**{today_str[5:]}** 在售 {len(today_items)} 条（按条数降序）：{cat_txt}（{base_note}）",
            f"新上架：{listing(new_keys, True)}",
            f"下架：{listing(gone_keys, False)}",
            f"价格变化：{change_txt}",
            f"判断：{verdict}（{reason}）",
        ]

    if broken:
        lines.append(f"注：{len(broken)} 个快照文件读取失败（{'、'.join(broken)}），已跳过。")
    return lines[:8]


def main():
    ap = argparse.ArgumentParser(description='生成苹果官翻每日简报（≤8 行 markdown）')
    ap.add_argument('--data-dir', default=os.environ.get('REPORT_DATA_DIR', DEFAULT_DATA),
                    help='快照目录（默认仓库 data/，也可用环境变量 REPORT_DATA_DIR）')
    args = ap.parse_args()
    try:
        lines = build_report(args.data_dir)
    except Exception as e:  # noqa: BLE001 - 任何意外都降级为可读说明，退出码仍 0
        lines = [f"简报生成失败：{type(e).__name__}: {e}"]
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
