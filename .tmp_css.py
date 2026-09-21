"""换掉美术页 CSS，并删掉已死的 JS 处理器（bNorm / bAll）。"""
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
p = pathlib.Path("wiki/gen.mjs")
t = p.read_text(encoding="utf-8")

start = t.index("/* 美术页 */")
end = t.index("/* 人物页 */")
t = t[:start] + '''/* 美术页 = 场景预览 + 旋钮 —— 只回答「摆一起协不协调」 */
.knobs{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:6px 0 12px}
.kn{display:inline-flex;align-items:center;gap:6px}
.kn>b{font:11px ui-monospace,Consolas,monospace;color:var(--dim);font-weight:600}
.stage{position:relative;overflow:auto;border:1px solid var(--line);border-radius:9px;
  background:#e3dfd3;padding:5px}
.scene{position:relative;transform-origin:top left;overflow:hidden;border-radius:6px;
  background:#6d8a52}
.scene .L{position:absolute}
.scene .tone,.scene .raing{position:absolute;pointer-events:none}
.scene .raing{background-repeat:repeat;background-size:64px 64px}
.scene.gridon::after{content:"";position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(#00000030 1px,transparent 1px),
    linear-gradient(90deg,#00000030 1px,transparent 1px);
  background-size:32px 32px}
.zoom{display:inline-flex;gap:3px}
.zoom button{font:inherit;font-size:11px;padding:2px 9px;border:1px solid var(--line);
  border-radius:999px;background:#fff;cursor:pointer}
.zoom button.on{background:#26221c;color:#f7f5f0;border-color:#26221c}
.arow{display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 14px}
.acell{display:flex;flex-direction:column;align-items:center;gap:4px;
  border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px}
.abox{display:flex;align-items:center;justify-content:center;background:#e9e6da;
  border-radius:5px;overflow:hidden}
.alb{font:10px ui-monospace,Consolas,monospace;color:var(--dim)}
''' + t[end:]

# 删掉死掉的 JS 处理器
for dead in [
'''  /* 全部展开 / 折叠 */
  var ab = document.getElementById("bAll");
  if (ab){ ab.onclick = function(){
    var all = document.querySelectorAll("details");
    var open = !Array.prototype.every.call(all, function(d){ return d.open; });
    Array.prototype.forEach.call(all, function(d){ d.open = open; });
    this.classList.toggle("on", open);
    this.textContent = open ? "全部折叠" : "全部展开";
  };}
''',
'''  /* 统一大小 */
  var nb = document.getElementById("bNorm");
  if (nb) nb.onclick = function(){ this.classList.toggle("on");
    document.body.classList.toggle("norm"); };
''',
'''  /* 格子 */
  var g = document.getElementById("bGrid");
  if (g) g.onclick = function(){ this.classList.toggle("on");
    document.body.classList.toggle("grid"); };
''']:
    assert dead in t, "没找到要删的 JS:" + dead[:40]
    t = t.replace(dead, "", 1)

p.write_text(t, encoding="utf-8")
print("CSS 换新 · 死掉的 JS 处理器已删")
