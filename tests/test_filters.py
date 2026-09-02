"""剪枝与冲突诊断单元测试"""

from __future__ import annotations

import unittest

from src.filters import diagnose_no_solution, filter_courses_for_solve, sections_conflict
from src.models import Course, Section, TimeSlot


def _sec(name: str, weekday: int, start: int, end: int, rating: float | None = None) -> Section:
    return Section(
        course_name=name,
        section_name=name,
        section_id=name,
        course_type="bxxk",
        time_slots=[TimeSlot(weekday=weekday, start_period=start, end_period=end)],
        teacher="",
        rating=rating,
    )


class FilterTests(unittest.TestCase):
    def test_remove_low_rating(self):
        courses = [
            Course(
                name="测试课",
                sections=[
                    _sec("A", 0, 1, 2, rating=8.0),
                    _sec("B", 1, 1, 2, rating=3.0),
                    _sec("C", 2, 1, 2, rating=None),
                ],
            )
        ]
        filtered, stats = filter_courses_for_solve(courses, min_rating=5.0)
        self.assertEqual(stats.removed_low_rating, 1)
        self.assertEqual(len(filtered[0].sections), 2)

    def test_cap_sections_per_course(self):
        courses = [
            Course(
                name="体育",
                sections=[
                    _sec(f"s{i}", i % 5, 1, 2, rating=float(i))
                    for i in range(20)
                ],
            )
        ]
        filtered, stats = filter_courses_for_solve(
            courses,
            max_sections_per_course=5,
        )
        self.assertEqual(len(filtered[0].sections), 5)
        self.assertEqual(stats.removed_section_cap, 15)

    def test_diagnose_always_conflict_pair(self):
        courses = [
            Course(name="A", sections=[_sec("A1", 0, 1, 2)]),
            Course(name="B", sections=[_sec("B1", 0, 1, 2)]),
        ]
        hints = diagnose_no_solution(courses)
        self.assertTrue(any("A" in h and "B" in h for h in hints))

    def test_sections_conflict(self):
        self.assertTrue(sections_conflict(_sec("x", 0, 1, 2), _sec("y", 0, 2, 3)))
        self.assertFalse(sections_conflict(_sec("x", 0, 1, 2), _sec("y", 1, 1, 2)))


if __name__ == "__main__":
    unittest.main()
