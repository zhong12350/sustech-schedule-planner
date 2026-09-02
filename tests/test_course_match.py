"""课程名匹配单元测试"""

import unittest

from src.course_match import (
    find_matching_course_keys,
    match_score,
    normalize_course_name,
    pick_best_match_group,
)


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


if __name__ == "__main__":
    unittest.main()
