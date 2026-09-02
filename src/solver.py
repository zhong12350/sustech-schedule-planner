"""回溯求解器：枚举所有不冲突的课表组合（含课程组 N 选 1）"""

from __future__ import annotations

from .models import Course, CourseGroup, Section, TimeSlot
from .preferences import SchedulePreferences, schedule_violates_preferences


def _has_conflict(time_slots: list[TimeSlot], occupied: set[tuple[int, int]]) -> bool:
    for ts in time_slots:
        for period in range(ts.start_period, ts.end_period + 1):
            if (ts.weekday, period) in occupied:
                return True
    return False


def _occupy(time_slots: list[TimeSlot], occupied: set[tuple[int, int]]) -> list[tuple[int, int]]:
    added: list[tuple[int, int]] = []
    for ts in time_slots:
        for period in range(ts.start_period, ts.end_period + 1):
            key = (ts.weekday, period)
            occupied.add(key)
            added.append(key)
    return added


def _release(added: list[tuple[int, int]], occupied: set[tuple[int, int]]) -> None:
    for key in added:
        occupied.discard(key)


def _section_sort_key(section: Section) -> tuple:
    return (
        section.rating is None,
        -(section.rating or 0.0),
        -(section.review_count or 0),
        section.section_name,
    )


def solve(
    courses: list[Course],
    max_results: int = 250,
    preferences: SchedulePreferences | None = None,
    course_groups: list[CourseGroup] | None = None,
) -> list[list[Section]]:
    """求解所有不冲突的课表组合。

    固定课程：每门恰好选 1 个教学班。
    课程组：每组恰好选 pick 门课，每门 1 个教学班。
    """
    course_groups = course_groups or []

    valid_courses = [c for c in courses if c.sections]
    for c in courses:
        if not c.sections:
            print(f"  [!] 课程 \"{c.name}\" 没有可选的教学班，已跳过")

    valid_groups: list[CourseGroup] = []
    for g in course_groups:
        group_courses = [c for c in g.courses if c.sections]
        if len(group_courses) < g.pick:
            print(f"  [!] 课程组 \"{g.name}\" 剪枝后仅剩 {len(group_courses)} 门课，"
                  f"无法满足选 {g.pick} 门")
            continue
        valid_groups.append(
            CourseGroup(
                name=g.name,
                pick=g.pick,
                courses=group_courses,
                course_type=g.course_type,
                category=g.category,
            )
        )

    if not valid_courses and not valid_groups:
        return []

    sorted_courses = sorted(valid_courses, key=lambda c: len(c.sections))
    sorted_groups = sorted(
        valid_groups,
        key=lambda g: sum(len(c.sections) for c in g.courses),
    )

    results: list[list[Section]] = []
    occupied: set[tuple[int, int]] = set()
    current_choice: list[Section] = []

    def _record_if_done() -> None:
        if preferences and schedule_violates_preferences(current_choice, preferences):
            return
        results.append(current_choice.copy())

    def _backtrack_fixed(index: int) -> None:
        if len(results) >= max_results:
            return
        if index == len(sorted_courses):
            _backtrack_group(0)
            return

        course = sorted_courses[index]
        for section in sorted(course.sections, key=_section_sort_key):
            if not section.time_slots:
                current_choice.append(section)
                _backtrack_fixed(index + 1)
                current_choice.pop()
                continue
            if _has_conflict(section.time_slots, occupied):
                continue
            added = _occupy(section.time_slots, occupied)
            current_choice.append(section)
            _backtrack_fixed(index + 1)
            current_choice.pop()
            _release(added, occupied)

    def _backtrack_group(group_index: int) -> None:
        if len(results) >= max_results:
            return
        if group_index == len(sorted_groups):
            _record_if_done()
            return
        group = sorted_groups[group_index]
        _pick_from_group(group, 0, 0, group_index)

    def _pick_from_group(
        group: CourseGroup,
        course_index: int,
        picked: int,
        group_index: int,
    ) -> None:
        if len(results) >= max_results:
            return
        if picked == group.pick:
            _backtrack_group(group_index + 1)
            return
        if course_index >= len(group.courses):
            return

        # 跳过本门候选课
        _pick_from_group(group, course_index + 1, picked, group_index)

        if picked >= group.pick:
            return

        course = group.courses[course_index]
        for section in sorted(course.sections, key=_section_sort_key):
            if not section.time_slots:
                current_choice.append(section)
                _pick_from_group(group, course_index + 1, picked + 1, group_index)
                current_choice.pop()
                continue
            if _has_conflict(section.time_slots, occupied):
                continue
            added = _occupy(section.time_slots, occupied)
            current_choice.append(section)
            _pick_from_group(group, course_index + 1, picked + 1, group_index)
            current_choice.pop()
            _release(added, occupied)

    if sorted_courses:
        _backtrack_fixed(0)
    else:
        _backtrack_group(0)

    return results


def print_solve_summary(
    courses: list[Course],
    results: list[list[Section]],
    max_results: int | None = None,
    course_groups: list[CourseGroup] | None = None,
) -> None:
    """打印求解摘要信息。"""
    course_groups = course_groups or []
    print(f"\n{'=' * 50}")
    print("求解完成！")
    print(f"  固定课程: {len(courses)}")
    if course_groups:
        for g in course_groups:
            print(f"  课程组: {g.name}（选 {g.pick} / {len(g.courses)} 候选）")
    total_sections = sum(len(c.sections) for c in courses)
    total_sections += sum(len(c.sections) for g in course_groups for c in g.courses)
    print(f"  总教学班数: {total_sections}")
    print(f"  可行方案数: {len(results)}")
    if max_results and len(results) >= max_results:
        print(f"  （已达上限 {max_results}，可能还有更多可行方案）")
    print(f"{'=' * 50}\n")
