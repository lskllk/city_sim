# -*- coding: utf-8 -*-
"""Split emojikeyboard.json (10 main categories) into per-category files."""
import json
import os
import re

SRC = "d:/sim_city/emojikeyboard.json"
OUT_DIR = "d:/sim_city/emojis_by_category"

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

os.makedirs(OUT_DIR, exist_ok=True)


def slug(name):
    # keep the leading emoji + safe ascii-ish slug
    s = re.sub(r"\s+", "_", name).strip("_")
    s = re.sub(r"[^\w\u4e00-\u9fff\u3000-\u303f\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F-]+", "_", s)
    return s.strip("_")


manifest = []
for i, cat in enumerate(data["categories"], 1):
    cat_name = cat["category"]
    emojis = cat["emojis"]
    base = f"{i:02d}_{slug(cat_name)}"
    # JSON file
    json_path = os.path.join(OUT_DIR, base + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"category": cat_name, "total": len(emojis), "emojis": emojis},
                  f, ensure_ascii=False, indent=2)
    # TXT file: emojis only
    txt_path = os.path.join(OUT_DIR, base + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(" ".join(e["emoji"] for e in emojis))
    manifest.append({"file": os.path.basename(json_path), "category": cat_name, "total": len(emojis)})

with open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8") as f:
    json.dump({"folder": OUT_DIR, "categories": manifest}, f, ensure_ascii=False, indent=2)

print(f"wrote {len(manifest)} category files to {OUT_DIR}")
for m in manifest:
    print(f"  {m['file']}  ({m['total']})")
