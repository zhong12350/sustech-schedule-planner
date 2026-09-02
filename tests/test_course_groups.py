"""课程组 N 选 1 单元测试"""

from __future__ import annotations

import unittest

from src.course_groups import (
    category_matches,
    expand_course_groups,
    filter_courses_by_rule,
    GroupConfig,
    parse_group_configs,
)
from src.models import Course, Section, TimeSlot
from src.solver import solve


def _sec(name: str, weekday: int, start: int, end: int, *, ctype: str = "xxxk", cat: str = "") -> Section:
    return Section(
        course_name=name,
        section_name=name,
        section_id=name,
        course_type=ctype,
        category=cat,
        time_slots=[TimeSlot(weekday=weekday, start_period=start, end_period=end)],
    )


MOCK_CATALOG: dict[str, list[Section]] = {
    "人文课A-01班": [_sec("人文课A-01班", 0, 3, 4, cat="人文类")],
    "人文课B-01班": [_sec("人文课B-01班", 1, 3, 4, cat="人文类")],
    "社科课C-01班": [_sec("社科课C-01班", 0, 5, 6, cat="社科类")],
    "高数-01班": [_sec("高数-01班", 2, 1, 2, ctype="kzyxk", cat="必修")],
}


class CourseGroupTests(unittest.TestCase):
    def test_category_matches(self):
        self.assertTrue(category_matches("人文类", "人文"))
        self.assertFalse(category_matches("社科类", "人文"))

    def test_filter_by_category(self):
        courses = filter_courses_by_rule(
            MOCK_CATALOG, course_type="xxxk", category="人文"
        )
        self.assertEqual(len(courses), 2)

    def test_expand_group(self):
        configs = [
            GroupConfig(name="人文组", pick=1, course_type="xxxk", category="人文"),
        ]
        result = expand_course_groups(configs, MOCK_CATALOG)
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(len(result.groups[0].courses), 2)

    def test_solve_pick_one_from_group(self):
        group = expand_course_groups(
            [GroupConfig(name="人文", pick=1, course_type="xxxk", category="人文")],
            MOCK_CATALOG,
        ).groups[0]
        fixed = [Course(name="高数", sections=MOCK_CATALOG["高数-01班"])]
        results = solve(fixed, course_groups=[group], max_results=20)
        self.assertEqual(len(results), 2)
        for sched in results:
            self.assertEqual(len(sched), 2)
            names = {s.course_name for s in sched}
            self.assertIn("高数-01班", names)
            self.assertTrue(
                "人文课A-01班" in names or "人文课B-01班" in names
            )

    def test_parse_config(self):
        raw = [{"name": "G", "pick": 1, "course_type": "xxxk", "category": "人文"}]
        configs = parse_group_configs(raw)
        self.assertEqual(configs[0].name, "G")


if __name__ == "__main__":
    unittest.main()
