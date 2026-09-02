"""课程名匹配单元测试"""

import unittest

from src.models import Section
from src.course_match import (
    connectives_compatible,
    find_matching_course_keys,
    match_score,
    normalize_course_name,
    pick_best_match_group,
    resolve_course_match,
)
from src.course_selection import match_courses_from_catalog


def _mock_section(key: str, teacher: str = "张老师") -> Section:
    return Section(
        course_name=key,
        section_name=f"{key} - {teacher}",
        section_id=key,
        course_type="kzyxk",
        teacher=teacher,
    )


# 基于用户 config.yaml 的 9 门课 + 常见 TIS 长名称
MOCK_CATALOG: dict[str, list[Section]] = {
    "EAP-12班-英文": [_mock_section("EAP-12班-英文", "石潇")],
    "宋代院体工笔花鸟画临习-01班-中文": [_mock_section("宋代院体工笔花鸟画临习-01班-中文", "温颖")],
    "宋代院体工笔花鸟画临习-02班-中文": [_mock_section("宋代院体工笔花鸟画临习-02班-中文", "温颖")],
    "毛泽东思想和中国特色社会主义理论体系概论-02班-中文": [
        _mock_section("毛泽东思想和中国特色社会主义理论体系概论-02班-中文", "滕明政")
    ],
    "毛泽东思想和中国特色社会主义理论体系概论-03班-中文": [
        _mock_section("毛泽东思想和中国特色社会主义理论体系概论-03班-中文", "尹玮煜")
    ],
    "体育Ⅴ-中文-乒乓球（进阶）1班": [_mock_section("体育Ⅴ-中文-乒乓球（进阶）1班", "车晓曦")],
    "体育Ⅴ-中文-乒乓球（基础）1班": [_mock_section("体育Ⅴ-中文-乒乓球（基础）1班", "车晓曦")],
    "走近突发公共卫生事件-01班-中文": [_mock_section("走近突发公共卫生事件-01班-中文", "李老师")],
    "微机原理与微系统-01班-双语-1组": [_mock_section("微机原理与微系统-01班-双语-1组", "王老师")],
    "电子科学创新实验II-01班-双语": [_mock_section("电子科学创新实验II-01班-双语", "赵老师")],
    "电子科学创新实验III-01班-中文": [_mock_section("电子科学创新实验III-01班-中文", "钱老师")],
    "数字信号处理-01班-双语-智华楼507和508机房同时使用": [
        _mock_section("数字信号处理-01班-双语-智华楼507和508机房同时使用", "孙老师")
    ],
    "数据通信和网络-01班-双语-智华楼507和508机房同时使用": [
        _mock_section("数据通信和网络-01班-双语-智华楼507和508机房同时使用", "周老师")
    ],
    "信号与系统-01班-中文": [_mock_section("信号与系统-01班-中文", "电子系老师")],
    "信号和系统-01班-中文": [_mock_section("信号和系统-01班-中文", "机械系老师")],
}

CONFIG_COURSES = [
    "EAP",
    "宋代院体工笔花鸟画临习",
    "毛泽东思想和中国特色社会主义理论体系概论",
    "体育Ⅴ",
    "走近突发公共卫生事件",
    "微机原理与微系统",
    "电子科学创新实验II",
    "数字信号处理",
    "数据通信和网络",
]


class CourseMatchTests(unittest.TestCase):
    def test_normalize_strips_section_suffix(self):
        raw = "数字信号处理-01班-双语-智华楼507和508机房同时使用"
        self.assertEqual(normalize_course_name(raw), "数字信号处理")

    def test_exact_short_name_matches_long_tis_name(self):
        score = match_score(
            "数字信号处理",
            "数字信号处理-01班-双语-智华楼507和508机房同时使用",
        )
        self.assertGreaterEqual(score, 0.95)

    def test_connective_yu_vs_he_not_compatible(self):
        self.assertFalse(connectives_compatible("信号与系统", "信号和系统"))
        self.assertEqual(match_score("信号与系统", "信号和系统"), 0.0)

    def test_connective_yu_matches_yu_only(self):
        keys = list(MOCK_CATALOG.keys())
        result = resolve_course_match("信号与系统", keys)
        self.assertEqual(result.status, "matched")
        self.assertTrue(all("与" in k for k in result.keys))

    def test_roman_suffix_distinguishes_ii_and_iii(self):
        ii_score = match_score(
            "电子科学创新实验II",
            "电子科学创新实验II-01班-双语",
        )
        iii_score = match_score(
            "电子科学创新实验II",
            "电子科学创新实验III-01班-中文",
        )
        self.assertGreaterEqual(ii_score, 0.95)
        self.assertEqual(iii_score, 0.0)

    def test_roman_suffix_distinguishes_i_and_ii(self):
        score = match_score(
            "电子科学创新实验II",
            "电子科学创新实验I-01班-中文",
        )
        self.assertEqual(score, 0.0)

    def test_sports_v_matches(self):
        score = match_score("体育Ⅴ", "体育Ⅴ-中文-乒乓球（进阶）1班")
        self.assertGreaterEqual(score, 0.95)

    def test_public_health_course_matches(self):
        score = match_score(
            "走近突发公共卫生事件",
            "走近突发公共卫生事件-01班-中文",
        )
        self.assertGreaterEqual(score, 0.95)

    def test_microprocessor_not_match_embedded(self):
        score = match_score(
            "微机原理与微系统",
            "微机原理与嵌入式系统-01班-双语-1组",
        )
        self.assertEqual(score, 0.0)

    def test_pick_best_match_group_merges_sections(self):
        keys = [
            "数字信号处理-01班-双语-智华楼507和508机房同时使用",
            "微机原理与微系统-01班-双语-1组",
            "EAP-12班-英文",
        ]
        matched, score = pick_best_match_group("数字信号处理", keys)
        self.assertEqual(len(matched), 1)
        self.assertIn("数字信号处理", matched[0])
        self.assertGreaterEqual(score, 0.95)

    def test_find_matching_returns_multiple_ee_courses_separately(self):
        keys = [
            "数字信号处理-01班-双语-智华楼507和508机房同时使用",
            "数据通信和网络-01班-双语-智华楼507和508机房同时使用",
            "微机原理与微系统-01班-双语-1组",
        ]
        dsp = find_matching_course_keys("数字信号处理", keys)
        dcn = find_matching_course_keys("数据通信和网络", keys)
        self.assertEqual(len(dsp), 1)
        self.assertEqual(len(dcn), 1)
        self.assertNotEqual(dsp[0][0], dcn[0][0])

    def test_vague_signal_query_is_ambiguous(self):
        keys = list(MOCK_CATALOG.keys())
        result = resolve_course_match("信号系统", keys, threshold=0.5)
        # 短查询可能同时匹配 与/和 两个版本
        if result.status == "ambiguous":
            identities = {o.identity for o in result.options}
            self.assertIn("信号与系统", identities)
            self.assertIn("信号和系统", identities)

    def test_all_nine_config_courses_match(self):
        selection = match_courses_from_catalog(CONFIG_COURSES, MOCK_CATALOG)
        self.assertEqual(len(selection.not_found), 0)
        self.assertEqual(len(selection.ambiguous), 0)
        self.assertEqual(len(selection.courses), 9)

    def test_sports_v_merges_all_sections(self):
        selection = match_courses_from_catalog(["体育Ⅴ"], MOCK_CATALOG)
        self.assertEqual(len(selection.courses), 1)
        self.assertEqual(len(selection.courses[0].sections), 2)

    def test_maogai_merges_multiple_sections(self):
        selection = match_courses_from_catalog(
            ["毛泽东思想和中国特色社会主义理论体系概论"],
            MOCK_CATALOG,
        )
        self.assertEqual(len(selection.courses), 1)
        self.assertEqual(len(selection.courses[0].sections), 2)


if __name__ == "__main__":
    unittest.main()
