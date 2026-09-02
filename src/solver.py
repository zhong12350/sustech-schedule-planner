"""回溯求解器：枚举所有不冲突的课表组合"""

from __future__ import annotations

from .models import Course, Section, TimeSlot


def _has_conflict(time_slots: list[TimeSlot], occupied: set[tuple[int, int]]) -> bool:
    """检查给定的时间段是否与已占用的时间槽冲突。

    Parameters
    ----------
    time_slots : list[TimeSlot]
        待检查的时间段列表
    occupied : set[tuple[int, int]]
        已占用的 (weekday, period) 集合

    Returns
    -------
    bool
        True 表示存在冲突
    """
    for ts in time_slots:
        for period in range(ts.start_period, ts.end_period + 1):
            if (ts.weekday, period) in occupied:
                return True
    return False


def _occupy(time_slots: list[TimeSlot], occupied: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """将时间段加入占用集合，返回新增的槽位列表（用于回溯释放）。"""
    added: list[tuple[int, int]] = []
    for ts in time_slots:
        for period in range(ts.start_period, ts.end_period + 1):
            key = (ts.weekday, period)
            occupied.add(key)
            added.append(key)
    return added


def _release(added: list[tuple[int, int]], occupied: set[tuple[int, int]]) -> None:
    """从占用集合中释放之前添加的时间槽。"""
    for key in added:
        occupied.discard(key)


def solve(
    courses: list[Course],
    max_results: int = 250,
) -> list[list[Section]]:
    """求解所有不冲突的课表组合。

    对每门课程选择一个教学班，使得所有选中的教学班之间没有时间冲突。

    Parameters
    ----------
    courses : list[Course]
        用户想选的课程列表，每门课包含多个可选教学班
    max_results : int
        最多返回多少个结果（防止组合爆炸），默认 100

    Returns
    -------
    list[list[Section]]
        每个元素是一种可行的选课方案，方案中包含每门课对应的教学班
    """
    if not courses:
        return []

    # 过滤掉没有教学班的课程
    valid_courses = [c for c in courses if c.sections]
    empty_courses = [c for c in courses if not c.sections]
    if empty_courses:
        for c in empty_courses:
            print(f"  [!] 课程 \"{c.name}\" 没有可选的教学班，已跳过")

    if not valid_courses:
        return []

    # 剪枝优化：教学班数量少的课程排在前面（约束传播思想）
    sorted_courses = sorted(valid_courses, key=lambda c: len(c.sections))

    results: list[list[Section]] = []
    occupied: set[tuple[int, int]] = set()
    current_choice: list[Section] = []

    def _backtrack(index: int) -> None:
        # 找到足够多结果时停止
        if len(results) >= max_results:
            return

        # 所有课程都已选择 -> 记录结果
        if index == len(sorted_courses):
            results.append(current_choice.copy())
            return

        course = sorted_courses[index]
        # 优先尝试高评分教学班，更快找到优质方案
        section_candidates = sorted(
            course.sections,
            key=lambda s: (
                s.rating is None,
                -(s.rating or 0.0),
                -(s.review_count or 0),
                s.section_name,
            ),
        )
        for section in section_candidates:
            # 跳过没有时间信息的教学班（无法判断冲突）
            if not section.time_slots:
                # 没有时间信息的教学班视为不冲突，直接加入
                current_choice.append(section)
                _backtrack(index + 1)
                current_choice.pop()
                continue

            # 冲突检测
            if _has_conflict(section.time_slots, occupied):
                continue

            # 选择该教学班
            added = _occupy(section.time_slots, occupied)
            current_choice.append(section)

            _backtrack(index + 1)

            # 回溯：撤销选择
            current_choice.pop()
            _release(added, occupied)

    _backtrack(0)
    return results


def print_solve_summary(
    courses: list[Course],
    results: list[list[Section]],
    max_results: int | None = None,
) -> None:
    """打印求解摘要信息。"""
    print(f"\n{'=' * 50}")
    print(f"求解完成！")
    print(f"  课程数: {len(courses)}")
    total_sections = sum(len(c.sections) for c in courses)
    print(f"  总教学班数: {total_sections}")
    print(f"  可行方案数: {len(results)}")
    if max_results and len(results) >= max_results:
        print(f"  （已达上限 {max_results}，可能还有更多可行方案）")
    print(f"{'=' * 50}\n")
