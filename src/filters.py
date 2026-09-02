"""求解前剪枝：按 NCES 评分过滤教学班，并在无解时给出冲突诊断。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Course, Section


@dataclass
class FilterStats:
    removed_low_rating: int = 0
    removed_section_cap: int = 0
    removed_empty_courses: int = 0


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
