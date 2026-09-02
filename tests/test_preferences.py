"""偏好求解与修复建议单元测试"""

from __future__ import annotations

import unittest

from src.filters import suggest_fixes
from src.models import Course, Section, TimeSlot
from src.preferences import (
    SchedulePreferences,
    filter_sections_for_preferences,
    schedule_free_days,
    schedule_max_consecutive,
    schedule_violates_preferences,
    section_has_early_morning,
)
from src.solver import solve


def _sec(
    name: str,
    weekday: int,
    start: int,
    end: int,
    *,
    location: str = "",
    rating: float | None = None,
) -> Section:
    return Section(
        course_name=name,
        section_name=name,
        section_id=name,
        course_type="bxxk",
        time_slots=[TimeSlot(weekday=weekday, start_period=start, end_period=end)],
        teacher="",
        location=location,
        rating=rating,
    )


class PreferenceTests(unittest.TestCase):
    def test_early_morning_detection(self):
        self.assertTrue(section_has_early_morning(_sec("A", 0, 1, 2)))
        self.assertFalse(section_has_early_morning(_sec("B", 0, 3, 4)))

    def test_filter_early_morning_sections(self):
        courses = [
            Course(
                name="课",
                sections=[
                    _sec("早", 0, 1, 2),
                    _sec("晚", 0, 5, 6),
                ],
            )
        ]
        filtered, stats = filter_sections_for_preferences(
            courses, SchedulePreferences(no_early_morning=True)
        )
        self.assertEqual(stats.removed_early_morning, 1)
        self.assertEqual(len(filtered[0].sections), 1)
        self.assertEqual(filtered[0].sections[0].section_id, "晚")

    def test_max_consecutive_violation(self):
        schedule = [
            _sec("A", 0, 1, 2),
            _sec("B", 0, 3, 4),
        ]
        self.assertEqual(schedule_max_consecutive(schedule), 4)
        prefs = SchedulePreferences(max_consecutive_periods=3)
        self.assertTrue(schedule_violates_preferences(schedule, prefs))

    def test_min_free_days(self):
        schedule = [
            _sec("A", 0, 1, 2),
            _sec("B", 2, 1, 2),
        ]
        self.assertEqual(schedule_free_days(schedule), 3)
        prefs = SchedulePreferences(min_free_days=2)
        self.assertFalse(schedule_violates_preferences(schedule, prefs))
        prefs_strict = SchedulePreferences(min_free_days=4)
        self.assertTrue(schedule_violates_preferences(schedule, prefs_strict))

    def test_solve_with_preferences(self):
        courses = [
            Course(name="A", sections=[_sec("A1", 0, 1, 2), _sec("A2", 1, 1, 2)]),
            Course(name="B", sections=[_sec("B1", 2, 3, 4)]),
        ]
        all_results = solve(courses, max_results=10)
        self.assertEqual(len(all_results), 2)

        prefs = SchedulePreferences(no_early_morning=True)
        filtered, _ = filter_sections_for_preferences(courses, prefs)
        pref_results = solve(filtered, max_results=10, preferences=prefs)
        self.assertEqual(len(pref_results), 1)
        self.assertFalse(any(section_has_early_morning(s) for s in pref_results[0]))


class SuggestFixesTests(unittest.TestCase):
    def test_drop_suggestion(self):
        courses = [
            Course(name="A", sections=[_sec("A1", 0, 1, 2)]),
            Course(name="B", sections=[_sec("B1", 0, 1, 2)]),
        ]
        suggestions = suggest_fixes(courses, max_results=50)
        self.assertTrue(any(s.action == "drop" for s in suggestions))
        drop = next(s for s in suggestions if s.action == "drop")
        self.assertGreater(drop.recovered_count, 0)

    def test_relax_preferences_suggestion(self):
        courses = [
            Course(name="A", sections=[_sec("A", 0, 1, 2)]),
            Course(name="B", sections=[_sec("B", 1, 1, 2)]),
            Course(name="C", sections=[_sec("C", 2, 1, 2)]),
            Course(name="D", sections=[_sec("D", 3, 1, 2)]),
            Course(name="E", sections=[_sec("E", 4, 1, 2)]),
        ]
        prefs = SchedulePreferences(min_free_days=1)
        suggestions = suggest_fixes(courses, max_results=50, preferences=prefs)
        actions = {s.action for s in suggestions}
        self.assertIn("relax_preferences", actions)


if __name__ == "__main__":
    unittest.main()
