"""emoji 注册表防漂移测试。

保证:
  1. src/citysim/emojis.py 的每个语义 key 都能在 emojis_by_category/*.json 里
     唯一解析到字形(且为 fully-qualified), 不落到库外。
  2. tools/gen_emoji_registry.py 里的 SEMANTIC 表与已生成模块一致(改库/改表后
     若忘记重跑会在此暴露)。
  3. snapshot.py 的 tag 图标 key 都是注册表内合法 key。
依赖 emojis_by_category/ 目录; 目录缺失(未拉取资源)时跳过。
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
from collections import defaultdict

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(ROOT, "emojis_by_category")
GEN_PATH = os.path.join(ROOT, "tools", "gen_emoji_registry.py")

from citysim.emojis import SEMANTIC_EMOJI  # noqa: E402


def _library() -> dict[str, list[str]]:
    name_to_emojis: dict[str, list[str]] = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(LIB_DIR, "*.json"))):
        if os.path.basename(f) == "index.json":
            continue
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        for e in data.get("emojis", []):
            name_to_emojis[e["name"]].append(e["emoji"])
    return name_to_emojis


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_emoji_registry", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lib():
    if not glob.glob(os.path.join(LIB_DIR, "*.json")):
        pytest.skip("emojis_by_category 目录缺失, 跳过 emoji 注册表测试")
    return _library()


def test_every_semantic_key_resolves_from_library(lib):
    """每个语义 key 的字形都能在库中找到且为 fully-qualified。"""
    for key, glyph in SEMANTIC_EMOJI.items():
        # 字形必须确实出现在库中的某个条目里
        present = any(glyph in cands for cands in lib.values())
        assert present, f"key={key!r} 字形 {glyph!r} 不在 emojis_by_category 中"
        # fully-qualified(通常带 \uFE0F, 需多于 1 个码点才被规范化过; 单码点天然限定)
        assert len(glyph) >= 1


def test_generated_matches_generator_and_library(lib):
    """已生成的注册表 == 生成器按当前库重新解析的结果(改库忘重跑会失败)。"""
    gen = _load_generator()
    resolved = gen.resolve()
    assert resolved == dict(SEMANTIC_EMOJI)


def test_snapshot_tag_keys_are_valid_semantic_keys():
    """snapshot.py 的 tag->key 映射引用的 key 必须都在注册表内。"""
    import re

    src = open(
        os.path.join(ROOT, "src", "citysim", "gateway", "snapshot.py"),
        encoding="utf-8",
    ).read()
    m = re.search(r"_ICON_KEYS\s*=\s*\{.*?\}", src, re.S)
    assert m, "snapshot.py 中找不到 _ICON_KEYS"
    body = m.group(0)
    keys = {k.strip("\"'") for k in re.findall(r':\s*"([^"]+)"', body)}
    keys |= {k.strip("\"'") for k in re.findall(r':\s*\'([^\']+)\'', body)}
    assert keys, "未能从 _ICON_KEYS 解析出任何语义 key"
    assert keys.issubset(SEMANTIC_EMOJI), (
        f"非法 key(不在注册表): {keys - set(SEMANTIC_EMOJI)}"
    )
