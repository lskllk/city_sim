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
# ★ 另一类：字符串字面量里出现 app.xxx —— 模块拆分时改名脚本留下的伤。
#   它【不崩、不报、也不影响 import】，只是让 HTML 属性 / 文案悄悄变错。
#   踩过三次：show("app.editor")、$("app.editor")、" app.selected"
#   （后者让所有 <option> 都没了 selected，浏览器自动选第一个 →
#    "双击进摆放，类型跳到了诊所"）。
#   ★ 必须【先取出字符串字面量再看内容】—— 直接上正则会在代码里跨引号乱匹配，
#     把正常的 app.editor.xxx 全报出来（试过一次，47 条全是误报）。
for p2 in sorted(D.glob("*.js")):
    raw = p2.read_text(encoding="utf-8")
    for sm in re.finditer(r"""'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`""", raw):
        txt = sm.group(0)
        if "app." not in txt or "${" in txt:      # 模板里的 ${} 是真引用，跳过
            continue
        ln = raw[:sm.start()].count("\n") + 1
        # 注释里提到 app.net 是正常的 —— 那份文档就是靠它讲为什么不用 export let
        head = raw.split(chr(10))[ln - 1].lstrip()
        if head.startswith('//') or head.startswith('*') or head.startswith('/*'): continue
        bad.append("%-14s:%-4d  字符串里出现 app. —— 多半是改名脚本改坏的：%s"
                   % (p2.name, ln, txt.strip()[:48]))

print("\n".join("  ✗ " + b for b in bad) if bad else "  ✓ 共享名全都有 import")
print("  （共查 %d 个共享名 × %d 个文件）" % (len(SHARED), len(list(D.glob('*.js')))))
