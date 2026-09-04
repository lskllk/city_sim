"""dump_codebase —— 把核心代码库(非测试)合并导出为一个带目录的文本文件。

用于把实现代码一次性"喂"给分析/评审工具，开头带目录(每模块起始行)便于索引。

默认只收核心包 src/citysim(**/*.py, 排除含 test 的文件)；可用 --root 追加目录
(如 tools、tests 里想收的除外目录)、--include-data 把 config/*.toml|*.json 数据
文件一并带上。

用法:
  python tools/dump_codebase.py                                  # -> docs/codebase_core.txt
  python tools/dump_codebase.py --root src/citysim --out docs/kb.txt
  python tools/dump_codebase.py --include-data --out docs/all.txt
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNER_LEN = 88


def _is_data(p: Path) -> bool:
    return p.suffix.lower() in (".toml", ".json", ".csv", ".txt", ".md")


def collect_files(roots: list[str], include_data: bool) -> list[Path]:
    """收集待导出文件：--root 目录里的 *.py(排除含 test 的)；可选数据文件。"""
    found: list[Path] = []
    seen: set[Path] = set()
    for r in roots:
        base = Path(r)
        if not base.is_absolute():
            base = ROOT / base
        if not base.exists():
            print(f"[warn] 路径不存在, 跳过: {base}", file=sys.stderr)
            continue
        if base.is_file():
            cands = [base]
        else:
            cands = [p for p in sorted(base.rglob("*"))
                     if p.is_file() and (p.suffix.lower() == ".py" or
                                         (include_data and _is_data(p)))]
        for p in cands:
            name = p.name.lower()
            if p.suffix.lower() == ".py" and ("test" in name or
                                              name == "conftest.py"):
                continue
            if p in seen:
                continue
            seen.add(p)
            found.append(p)
    return sorted(found)


def render(files: list[Path], root_labels: dict[Path, str]) -> str:
    """组装: 目录 + 各文件内容。目录行号 = 各文件 '###' 标注行在成品内的绝对行号。

    两趟: 先拼 body(顺带记录每文件 '###' 行在 body 内的偏移), 再在前面加
    header+目录 —— 前缀行数随目录行数增长, 故按 len(prefix) 推最终行号。
    """
    n_files = len(files)
    texts = [(root_labels[p], p.read_text(encoding="utf-8")) for p in files]

    # 1) 拼 body, 记录每文件 '###' 标注行在 body 中的 0-based 偏移
    body: list[str] = []
    label_at: list[int] = []
    for label, t in texts:
        body.append("=" * BANNER_LEN)
        label_at.append(len(body))           # 下一条即 '### label' 行
        body.append(f"### {label}")
        body.append("=" * BANNER_LEN)
        body.extend(t.splitlines())
        body.append("")

    # 2) header + 目录前缀: 固定 9 行 + 每文件一行
    prefix: list[str] = [
        "# 核心代码库合并导出 (core codebase dump)",
        f"# 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        "# 文件数占位",
        "# 用途: 一次性分析/评审输入; 目录行号 = 本文件内绝对行号(1-based)",
        "",
        "## 目录 (Table of Contents)",
        "",
        "| # | 模块/文件 | 起行 | LOC |",
        "|---|---------|-----|-----|",
    ]
    for i, ((label, t), at) in enumerate(zip(texts, label_at), 1):
        # 最终前缀 = 固定 9 行 + n_files 行目录; '###' 行 = 前缀尾 + body 偏移 +1
        start_line = (9 + n_files) + at + 1  # 成品内 1-based 绝对行
        loc = len(t.splitlines())
        prefix.append(f"| {i} | `{label}` | {start_line} | {loc} |")
    prefix[2] = f"# 文件数: {n_files} · 总行数: {len(prefix) + len(body)}"
    return "\n".join(prefix + body)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", default=[],
                    help="要收集的根/文件(可多次); 默认 src/citysim")
    ap.add_argument("--out", default="docs/codebase_core.txt",
                    help="输出文本路径(默认 docs/codebase_core.txt)")
    ap.add_argument("--include-data", action="store_true",
                    help="连同 config/ 下的 toml/json 数据一起导出")
    a = ap.parse_args()

    roots = a.root or ["src/citysim"]
    if a.include_data:
        roots.append("config")
    files = collect_files(roots, a.include_data)
    if not files:
        print("没有收集到文件", file=sys.stderr)
        sys.exit(1)
    root_labels = {}
    for p in files:
        # 展示名: 相对工程根
        try:
            root_labels[p] = str(p.resolve().relative_to(ROOT.resolve()))
        except ValueError:
            root_labels[p] = str(p)
    text = render(files, root_labels)
    out_path = Path(a.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    nloc = sum(1 for _ in text.splitlines())
    print(f"已导出 {len(files)} 个文件 → {out_path} (含目录, 共 {nloc} 行)")


if __name__ == "__main__":
    main()
