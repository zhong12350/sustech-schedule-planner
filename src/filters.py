"""求解前剪枝：按 NCES 评分过滤教学班，并在无解时给出冲突诊断。"""

from __future__ import annotations

from dataclasses import dataclass

from .course_match import group_keys_by_identity, find_matching_course_keys
from .models import Course, Section
from .preferences import SchedulePreferences, filter_sections_for_preferences
from .solver import solve


@dataclass
class FilterStats:
    removed_low_rating: int = 0
    removed_section_cap: int = 0
    removed_empty_courses: int = 0


@dataclass
class FixSuggestion:
    """无解时可尝试的修复建议。"""

    action: str  # drop | switch | relax_preferences
    course_name: str
    recovered_count: int
    message: str
    alternative: str = ""


def sections_conflict(a: Section, b: Section) -> bool:
    """两个教学班是否存在时间冲突。"""
    if not a.time_slots or not b.time_slots:
        return False
    periods_a = a.all_periods()
    periods_b = b.all_periods()
    return bool(periods_a & periods_b)


def filter_courses_for_solve(
    courses: list[Course],
    *,
    min_rating: float | None = None,
    max_sections_per_course: int | None = None,
    keep_unrated: bool = True,
) -> tuple[list[Course], FilterStats]:
    """按评分与每课教学班上限剪枝，缩小搜索空间。"""
    stats = FilterStats()
    filtered: list[Course] = []

    for course in courses:
        sections = list(course.sections)

        if min_rating is not None:
            kept: list[Section] = []
            for section in sections:
                if section.rating is None:
                    if keep_unrated:
                        kept.append(section)
                    continue
                if section.rating >= min_rating:
                    kept.append(section)
                else:
                    stats.removed_low_rating += 1
            sections = kept

        if max_sections_per_course is not None and len(sections) > max_sections_per_course:
            sections.sort(
                key=lambda s: (
                    s.rating is None,
                    -(s.rating or 0.0),
                    -(s.review_count or 0),
                ),
            )
            removed = len(sections) - max_sections_per_course
            stats.removed_section_cap += removed
            sections = sections[:max_sections_per_course]

        if not sections:
            stats.removed_empty_courses += 1
            continue

        filtered.append(Course(name=course.name, sections=sections))

    return filtered, stats


def diagnose_no_solution(courses: list[Course]) -> list[str]:
    """分析为何不存在无冲突方案。"""
    hints: list[str] = []
    valid = [c for c in courses if c.sections]

    for i, left in enumerate(valid):
        for right in valid[i + 1 :]:
            if not left.sections or not right.sections:
                continue
            always_conflict = True
            for sec_l in left.sections:
                for sec_r in right.sections:
                    if not sections_conflict(sec_l, sec_r):
                        always_conflict = False
                        break
                if not always_conflict:
                    break
            if always_conflict:
                hints.append(
                    f"「{left.name}」与「{right.name}」的所有教学班两两时间冲突"
                )

    single_section = [c for c in valid if len(c.sections) == 1]
    if single_section:
        names = "、".join(f"「{c.name}」" for c in single_section)
        hints.append(f"以下课程仅有 1 个教学班，无法通过换班消冲突：{names}")

    return hints


def _count_solutions(
    courses: list[Course],
    *,
    max_results: int,
    preferences: SchedulePreferences | None,
) -> int:
    if len(courses) < 1:
        return 0
    working = list(courses)
    if preferences and preferences.is_active():
        working, _ = filter_sections_for_preferences(working, preferences)
        if not working:
            return 0
    results = solve(working, max_results=max_results, preferences=preferences)
    return len(results)


def _course_from_alternative_keys(
    query: str,
    keys: list[str],
    all_courses: dict[str, list[Section]],
) -> Course | None:
    sections: list[Section] = []
    for key in keys:
        sections.extend(all_courses.get(key, []))
    if not sections:
        return None
    return Course(name=query, sections=sections)


def suggest_fixes(
    courses: list[Course],
    *,
    max_results: int = 100,
    preferences: SchedulePreferences | None = None,
    all_courses: dict[str, list[Section]] | None = None,
) -> list[FixSuggestion]:
    """无解时给出可恢复方案数的修复建议。"""
    if not courses:
        return []

    prefs = preferences or SchedulePreferences()
    baseline = _count_solutions(courses, max_results=max_results, preferences=prefs)
    if baseline > 0:
        return []

    suggestions: list[FixSuggestion] = []

    # 偏好过严：无偏好时其实有解
    if prefs.is_active():
        without_prefs = _count_solutions(
            courses, max_results=max_results, preferences=SchedulePreferences()
        )
        if without_prefs > 0:
            pref_desc = "、".join(prefs.summary_lines()) or "当前偏好"
            suggestions.append(
                FixSuggestion(
                    action="relax_preferences",
                    course_name="",
                    recovered_count=without_prefs,
                    message=(
                        f"关闭或放宽偏好（{pref_desc}）"
                        f"可恢复约 {without_prefs} 个方案"
                    ),
                )
            )

    # 移除单门课
    drop_candidates: list[FixSuggestion] = []
    for i, course in enumerate(courses):
        reduced = courses[:i] + courses[i + 1 :]
        if not reduced:
            continue
        count = _count_solutions(reduced, max_results=max_results, preferences=prefs)
        if count > 0:
            drop_candidates.append(
                FixSuggestion(
                    action="drop",
                    course_name=course.name,
                    recovered_count=count,
                    message=f"移除「{course.name}」可恢复约 {count} 个方案",
                )
            )
    drop_candidates.sort(key=lambda s: (-s.recovered_count, s.course_name))
    suggestions.extend(drop_candidates[:5])

    # 切换歧义身份（需完整 TIS 目录）
    if all_courses:
        all_keys = list(all_courses.keys())
        switch_candidates: list[FixSuggestion] = []
        for i, course in enumerate(courses):
            scored = find_matching_course_keys(course.name, all_keys)
            if not scored:
                continue
            groups = group_keys_by_identity([k for k, _ in scored], query=course.name)
            if len(groups) < 2:
                continue

            current_identities = {s.course_name for s in course.sections}
            for identity, keys in groups.items():
                if identity in current_identities:
                    continue
                alt_course = _course_from_alternative_keys(course.name, keys, all_courses)
                if alt_course is None:
                    continue
                trial = list(courses)
                trial[i] = alt_course
                count = _count_solutions(trial, max_results=max_results, preferences=prefs)
                if count > 0:
                    switch_candidates.append(
                        FixSuggestion(
                            action="switch",
                            course_name=course.name,
                            alternative=identity,
                            recovered_count=count,
                            message=(
                                f"将「{course.name}」换为「{identity}」"
                                f"可恢复约 {count} 个方案"
                            ),
                        )
                    )
        switch_candidates.sort(key=lambda s: (-s.recovered_count, s.course_name))
        suggestions.extend(switch_candidates[:5])

    # 去重：同一 message 只保留一条
    seen: set[str] = set()
    unique: list[FixSuggestion] = []
    for s in suggestions:
        if s.message in seen:
            continue
        seen.add(s.message)
        unique.append(s)
    return unique


def format_suggestions(suggestions: list[FixSuggestion]) -> list[str]:
    return [s.message for s in suggestions]
