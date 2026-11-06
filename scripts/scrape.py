#!/usr/bin/env python3
"""苹果中国官翻库存抓取（Tabbit CLI）。

用法: python3 scripts/scrape.py
产出: data/YYYY-MM-DD.json （当日快照）

数据来源: https://www.apple.com.cn/shop/refurbished/mac/{mac-studio,mac-mini,macbook-pro}
抓取方式: Tabbit Browser CLI 渲染页面后读取商品卡（价格格式为 "RMB 15,599"）。
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
TABBIT = os.path.expanduser('~/.local/bin/tabbit-cli')
TASK = '苹果官翻-' + datetime.now().strftime('%Y%m%d-%H%M')

CATS = {
    'Mac Studio': 'https://www.apple.com.cn/shop/refurbished/mac/mac-studio',
    'Mac mini': 'https://www.apple.com.cn/shop/refurbished/mac/mac-mini',
    'MacBook Pro': 'https://www.apple.com.cn/shop/refurbished/mac/macbook-pro',
}

PROGRAM = r'''
await page.goto(URL, {waitUntil: "domcontentloaded", timeout: 45000});
await page.waitForTimeout(5000);
return await page.evaluate(() => {
  function priceNear(a) {
    let el = a;
    for (let i = 0; i < 6 && el; i++) {
      const t = (el.innerText || "").replace(/\s+/g, " ");
      const m = t.match(/RMB\s*[\d,]+/g);
      if (m && m.length === 1 && t.length < 500) return m[0];
      el = el.parentElement;
    }
    return null;
  }
  const res = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/shop/product/"]')) {
    const href = (a.getAttribute("href") || "");
    const title = (a.innerText || "").replace(/\s+/g, " ").trim();
    if (!title || title.length < 10) continue;
    const price = priceNear(a);
    if (!price) continue;
    const key = href + "|" + title.slice(0, 60);
    if (seen.has(key)) continue;
    seen.add(key);
    res.push({href, title: title.slice(0, 300), price});
  }
  return res;
});
'''


def run_page(url, tag):
    prog = PROGRAM.replace('URL', json.dumps(url))
    rid = f'scrape-{tag}-' + datetime.now().strftime('%H%M%S')
    r = subprocess.run(
        [TABBIT, 'nodejs', '--task', TASK, '--request-id', rid, '--timeout-ms', '180000'],
        input=prog, capture_output=True, text=True, timeout=240,
    )
    if r.returncode != 0:
        raise RuntimeError(f'tabbit-cli exit {r.returncode}: {(r.stderr or r.stdout)[:300]}')
    payload = None
    for line in (r.stdout or '').splitlines():
        line = line.strip()
        if line.startswith('{') and '"result"' in line:
            try:
                payload = json.loads(line)
            except Exception:
                pass
    if not payload:
        raise RuntimeError(f'tabbit-cli 输出无法解析: {(r.stdout or "")[:300]}')
    result = payload.get('result') or {}
    if result.get('resourceId'):
        parts, offset = [], 0
        for _ in range(10):
            rr = subprocess.run(
                [TABBIT, 'resource', '--task', TASK, '--resource', result['resourceId'],
                 '--offset', str(offset), '--max-bytes', '65536'],
                capture_output=True, text=True, timeout=120,
            )
            chunk = json.loads(rr.stdout)
            parts.append(chunk.get('data', ''))
            if chunk.get('eof') or chunk.get('nextOffset') is None:
                break
            offset = chunk['nextOffset']
        data = json.loads(''.join(parts))
    else:
        data = result.get('value')
    if not isinstance(data, list):
        raise RuntimeError(f'{tag} 返回空数据')
    return data


def run_all():
    rows, errors = [], []
    for tag, url in CATS.items():
        try:
            rows.extend(run_page(url, tag.replace(' ', '')))
        except Exception as exc:
            errors.append(f'{tag}: {exc}')
    try:
        subprocess.run([TABBIT, 'finish', '--task', TASK, '--discard'],
                       capture_output=True, text=True, timeout=60)
    except Exception:
        pass
    if not rows:
        raise RuntimeError('; '.join(errors) or '无数据')
    return rows, errors


CHIP_RE = re.compile(r'Apple\s+(M\d+(?:\s*Pro|\s*Max|\s*Ultra)?)\s*芯片')
CPU_RE = re.compile(r'(\d+)\s*核中央处理器')
GPU_RE = re.compile(r'(\d+)\s*核图形处理器')
RAM_RE = re.compile(r'(\d+)\s*GB\s*统一内存')
SSD_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(TB|GB)\s*固态硬盘')
SCREEN_RE = re.compile(r'(\d+)\s*英寸')
PRICE_RE = re.compile(r'RMB\s*([\d,]+)')
ID_RE = re.compile(r'/shop/product/([A-Za-z0-9]+)')


DETAIL_RAM_RE = re.compile(r'(\d+)\s*GB\s*统一内存')
DETAIL_SSD_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(TB|GB)\s*固态硬盘')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')


def fetch_detail(url):
    """抓商品详情页，补 memoryGB / storage。失败返回 (None, '')。"""
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9'})
    with urllib.request.urlopen(req, timeout=25) as resp:
        html = resp.read().decode('utf-8', 'replace')
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    ram = DETAIL_RAM_RE.search(text)
    ssd = DETAIL_SSD_RE.search(text)
    mem = int(ram.group(1)) if ram else None
    storage = (ssd.group(1) + ssd.group(2)) if ssd else ''
    return mem, storage


def enrich(items, workers=8):
    """并发补全缺失的内存/硬盘字段；只填值，不改结构。"""
    todo = []
    seen = set()
    for it in items:
        if it.get('memoryGB') and it.get('storage'):
            continue
        m = ID_RE.search(it.get('url', ''))
        pid = m.group(1) if m else it.get('url')
        if pid in seen:
            continue
        seen.add(pid)
        todo.append((pid, it))
    if not todo:
        return {'filled': 0, 'total': 0}

    def work(pair):
        pid, it = pair
        try:
            mem, storage = fetch_detail(it['url'])
            return pid, mem, storage, None
        except Exception as exc:
            return pid, None, '', str(exc)[:120]

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for pid, mem, storage, err in pool.map(work, todo):
            results[pid] = (mem, storage)
    filled = 0
    for it in items:
        m = ID_RE.search(it.get('url', ''))
        pid = m.group(1) if m else it.get('url')
        mem, storage = results.get(pid, (None, ''))
        if not it.get('memoryGB') and mem:
            it['memoryGB'] = mem
        if not it.get('storage') and storage:
            it['storage'] = storage
        if it.get('memoryGB') and it.get('storage'):
            filled += 1
    return {'filled': filled, 'total': len(items)}


def parse_item(category, href, text, price_text=''):
    price_m = PRICE_RE.search(price_text or '') or PRICE_RE.search(text)
    if not price_m:
        return None
    title = re.sub(r'\s*RMB\s*[\d,]+.*$', '', text).strip()
    if not title.startswith('翻新'):
        return None
    chip = CHIP_RE.search(title)
    cpu = CPU_RE.search(title)
    gpu = GPU_RE.search(title)
    ram = RAM_RE.search(title)
    ssd = SSD_RE.search(title)
    screen = SCREEN_RE.search(title)
    port = '10GbE' if ('10Gb' in title or '万兆' in title) else ('GbE' if '千兆' in title else '')
    item_id = ID_RE.search(href)
    if href.startswith('http'):
        url = href
    else:
        url = 'https://www.apple.com.cn' + href
    return {
        'category': category,
        'model': category,
        'chip': chip.group(1) if chip else '',
        'cpuCores': int(cpu.group(1)) if cpu else None,
        'gpuCores': int(gpu.group(1)) if gpu else None,
        'memoryGB': int(ram.group(1)) if ram else None,
        'storage': (ssd.group(1) + ssd.group(2)) if ssd else '',
        'screenInch': int(screen.group(1)) if screen else None,
        'port': port,
        'price': int(price_m.group(1).replace(',', '')),
        'title': title,
        'url': url,
    }


def main():
    os.makedirs(DATA, exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=8)))
    day = now.strftime('%Y-%m-%d')
    try:
        raw, errors = run_all()
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 2
    items, seen = [], set()
    for row in raw:
        title = row.get('title') or row.get('text') or ''
        category = None
        for name in CATS:
            if name in title:
                category = name
                break
        if not category:
            continue
        item = parse_item(category, row.get('href', ''), title, row.get('price', ''))
        if not item:
            continue
        m = ID_RE.search(item['url'])
        key = ((m.group(1) if m else item['url']), item['price'])
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    items.sort(key=lambda z: (z['category'], z['price']))
    try:
        enriched = enrich(items)
        print(json.dumps({'enrich': enriched}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'enrich_error': str(exc)[:200]}, ensure_ascii=False))
    payload = {
        'date': day,
        'fetchedAt': now.isoformat(timespec='seconds'),
        'source': 'apple.com.cn/shop/refurbished/mac',
        'count': len(items),
        'items': items,
    }
    out = os.path.join(DATA, f'{day}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(json.dumps({'ok': True, 'date': day, 'count': len(items), 'file': out}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
