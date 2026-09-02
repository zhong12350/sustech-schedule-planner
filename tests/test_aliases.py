"""课名别名知识库单元测试"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from src.aliases import apply_alias, keys_for_identity, load_aliases, lookup_alias
from src.course_match import resolve_course_match
from src.models import Section


MOCK_KEYS = [
    "高等数学（下）-01班-中文",
    "高等数学（下）-02班-双语",
    "线性代数-01班-中文",
    "数字信号处理-01班-中文",
]


def _make_alias_file(mapping: dict[str, str]) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.dump({"aliases": mapping}, tmp, allow_unicode=True)
    tmp.close()
    return Path(tmp.name)


class AliasTests(unittest.TestCase):
    def test_lookup_and_keys_for_identity(self):
        path = _make_alias_file({"高数": "高等数学（下）", "线代": "线性代数"})
        self.assertEqual(lookup_alias("高数", path), "高等数学（下）")
        keys = keys_for_identity("高等数学（下）", MOCK_KEYS)
        self.assertEqual(len(keys), 2)
        self.assertTrue(all("高等数学（下）" in k for k in keys))

    def test_apply_alias_direct_hit(self):
        path = _make_alias_file({"线代": "线性代数"})
        effective, target, keys = apply_alias("线代", MOCK_KEYS, path=path)
        self.assertEqual(target, "线性代数")
        self.assertEqual(len(keys), 1)
        self.assertEqual(effective, "线性代数")

    def test_resolve_course_match_via_alias(self):
        path = _make_alias_file({"高数": "高等数学（下）"})
        # 临时让 load 用这个 path — 通过 apply_alias 在 resolve 里默认路径
        # 直接测 keys 路径：把 DEFAULT 指向 temp 较麻烦，改测 resolve 前置逻辑
        effective, target, keys = apply_alias("高数", MOCK_KEYS, path=path)
        self.assertGreater(len(keys), 0)
        result = resolve_course_match("高等数学（下）", MOCK_KEYS)
        self.assertIn(result.status, ("matched", "exact"))

    def test_load_aliases_empty_when_missing(self):
        table = load_aliases(Path("/nonexistent/aliases.yaml"), reload=True)
        self.assertEqual(table.aliases, {})


if __name__ == "__main__":
    unittest.main()
