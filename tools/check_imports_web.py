"""拆模块之后最容易犯的错：用了某个共享名但忘了 import。
这个脚本一次性把它们全找出来。"""
import pathlib, re, sys
sys.stdout.reconfigure(encoding="utf-8")

D = pathlib.Path("src/web/js")
SHARED = {
    "SPEEDS": "zh.js", "SPEED_ZH": "zh.js", "SIGNAL_ZH": "zh.js", "COMPANY_KIND_ZH": "zh.js",
    "BUILD": "core.js", "LS_LAST": "core.js", "toast": "core.js", "setStatus": "core.js",
    "show": "core.js", "esc": "core.js", "ensureAssets": "core.js", "$": "core.js",
    "store": "core.js", "app": "core.js",
    "openSheet": "ui.js", "closeSheet": "ui.js", "renderQueue": "ui.js",
    "infoTabs": "ui.js", "infoPage": "ui.js", "infoSub": "ui.js",
    "personPage": "ui.js", "shopPage": "ui.js", "homePage": "ui.js",
}
STR = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`', re.S)
LINE = re.compile(r"//[^\n]*")
BLOCK = re.compile(r"/\*.*?\*/", re.S)

def strip(t):
    return LINE.sub("", BLOCK.sub("", STR.sub('""', t)))

bad = []
for p in sorted(D.glob("*.js")):
    if p.name in ("core.js", "zh.js"):
        continue
    body = strip(p.read_text(encoding="utf-8"))
    imported = set()
    for m in re.finditer(r"^import\s*\{([^}]*)\}", body, re.M):
        imported |= {x.split(" as ")[-1].strip() for x in m.group(1).split(",") if x.strip()}
    for n, src in SHARED.items():
        if src == p.name:
            continue
        # ★ 裸值也要抓：`... of SPEEDS` 这种后面没有 . ( [ 的（SPEEDS 就是这么漏的）。
        #   排除掉声明处（const/let/var/function 后的那个名字）和对象键（后面跟冒号）。
        m = None
        for mm in re.finditer(r"(?<![\w.$])" + re.escape(n) + r"(?![\w$])", body):
            before = body[max(0, mm.start() - 12):mm.start()]
            after = body[mm.end():mm.end() + 2].lstrip()
            if re.search(r"(?:const|let|var|function|class|import)\s*$", before): continue
            if after.startswith(":"): continue
            m = mm; break
        if m and n not in imported:
            ln = body[:m.start()].count("\n") + 1
            bad.append("%-14s:%-4d  用了 %-14s → 应 import { %s } from \"./%s\""
                       % (p.name, ln, n, n, src))
print("\n".join("  ✗ " + b for b in bad) if bad else "  ✓ 共享名全都有 import")
print("  （共查 %d 个共享名 × %d 个文件）" % (len(SHARED), len(list(D.glob('*.js')))))
