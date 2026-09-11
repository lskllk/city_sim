"""names —— 中文姓名池 + 生成规则(纯数据, 不依赖 world/渲染)。

规则(docs/naming.md):
- 结构: 姓(1) + 名(1~2) → name; id = npc_<姓拼音>_<名拼音>;
- 池在 config/names/names.json(hanzi + pinyin);
- 由 seed 决定(可复现); 同家族可复用同一个姓(with_surname)。
"""
from __future__ import annotations

import functools
import json
import random
from dataclasses import dataclass
from pathlib import Path

_DIR = Path(__file__).resolve().parents[3] / "config" / "names"


@dataclass(frozen=True)
class PersonName:
    surname: str
    surname_py: str
    given: str
    given_py: str

    @property
    def name(self) -> str:
        return self.surname + self.given

    @property
    def person_id(self) -> str:
        return f"npc_{self.surname_py}_{self.given_py}"

    def with_surname(self, other: "PersonName") -> "PersonName":
        """换成同一个姓(用于兄弟姐妹/子女)。"""
        return PersonName(other.surname, other.surname_py,
                          self.given, self.given_py)


@functools.lru_cache(maxsize=2)
def load_name_pool(directory: str | Path | None = None) -> dict:
    p = (_DIR if directory is None else Path(directory)) / "names.json"
    return json.loads(p.read_text(encoding="utf-8"))


def new_name(seed: int, gender: str = "male",
             directory: str | None = None) -> PersonName:
    """由 seed 决定地取一个姓+名(同一 seed → 同一结果)。"""
    pool = load_name_pool(directory)
    rng = random.Random(seed)
    s = rng.choice(pool["surnames"])
    key = "given_female" if gender == "female" else "given_male"
    g = rng.choice(pool[key])
    return PersonName(s["hz"], s["py"], g["hz"], g["py"])


def clear_cache() -> None:
    load_name_pool.cache_clear()
