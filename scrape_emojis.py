# -*- coding: utf-8 -*-
"""Scrape https://emojikeyboard.top/ emojis grouped by category (headings)."""
import html as html_mod
import json
import re
import urllib.request

URL = "https://emojikeyboard.top/"
OUT_JSON = "d:/sim_city/emojikeyboard_all.json"
OUT_TXT = "d:/sim_city/emojikeyboard_all.txt"
OUT_MAIN_JSON = "d:/sim_city/emojikeyboard.json"

html = urllib.request.urlopen(
    urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=60
).read().decode("utf-8", "ignore")


def clean(t):
    return html_mod.unescape(re.sub(r"<[^>]+>", "", t)).replace("\u200d", "").strip()


def lis_in(block):
    """Extract [(name, emoji)] from an html block."""
    out = []
    for title, content in re.findall(r'<li[^>]*title="([^"]*)"[^>]*>(.*?)</li>', block, flags=re.S):
        emoji = clean(content)
        if emoji:
            out.append((title, emoji))
    return out


def heading_blocks(container_html):
    """Split a container by inner <h2 ...> ... content up to next h2."""
    parts = re.split(r'<h2[^>]*>', container_html)
    heads = re.findall(r'<h2[^>]*>(.*?)</h2>', container_html, flags=re.S)
    blocks = []
    for i, head in enumerate(heads):
        title = clean(head)
        body = parts[i + 1] if i + 1 < len(parts) else ""
        blocks.append((title, body))
    return blocks


categories = []

# 1) top-level category sections emojis-1..10 (each has inner <h2>title</h2>)
top_sections = re.findall(
    r'<section[^>]*id="emojis-(1[0]|[1-9])"[^>]*>(.*?)</section>', html, flags=re.S
)
seen_cats = set()
for num, body in top_sections:
    m = re.search(r'<h2[^>]*>(.*?)</h2>', body, flags=re.S)
    title = clean(m.group(1)) if m else f"Category {num}"
    if title in seen_cats:
        continue
    seen_cats.add(title)
    emojis = [{"name": n, "emoji": e} for n, e in lis_in(body)]
    categories.append({"category": title, "emojis": emojis})

# 2) container sections (emojis-15, emojis-11) -> inner h2 sub-categories
for secid in ("emojis-15", "emojis-11"):
    m = re.search(r'<section[^>]*id="%s"[^>]*>(.*?)</section>' % secid, html, flags=re.S)
    if not m:
        continue
    for title, body in heading_blocks(m.group(1)):
        emojis = [{"name": n, "emoji": e} for n, e in lis_in(body)]
        if not emojis:
            continue
        categories.append({"category": title, "emojis": emojis})

total = sum(len(c["emojis"]) for c in categories)
data = {"source": URL, "total_emojis": total, "categories": categories}

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(f"# Emoji Keyboard ({URL})  total={total}\n\n")
    for c in categories:
        f.write(f"## {c['category']}  ({len(c['emojis'])})\n")
        f.write(" ".join(e["emoji"] for e in c["emojis"]) + "\n\n")

# Main categories only (10 top-level, no skin-tone/gender split)
main_cats = categories[:10]
main_total = sum(len(c["emojis"]) for c in main_cats)
with open(OUT_MAIN_JSON, "w", encoding="utf-8") as f:
    json.dump({"source": URL, "total_emojis": main_total, "categories": main_cats},
              f, ensure_ascii=False, indent=2)

print(f"ALL: categories={len(categories)} total={total}")
for c in categories:
    print(f"  {c['category']}: {len(c['emojis'])}")
print(f"\nMAIN(10): total={main_total} -> {OUT_MAIN_JSON}")
