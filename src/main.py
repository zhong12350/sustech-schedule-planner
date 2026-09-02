#!/usr/bin/env python3
"""南科大课表无冲突组合求解器 - 主入口"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel

# 将项目根目录加入 sys.path，以支持直接运行
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import interactive_login, cas_login
from src.scraper import get_semester_info, get_courses_for_selection, fetch_all_courses
from src.course_selection import prompt_disambiguation, SelectionResult
from src.solver import solve, print_solve_summary
from src.display import display_all_schedules, display_schedule
from src.ratings import enrich_courses_with_ratings, rank_schedules, score_schedule
from src.filters import diagnose_no_solution, filter_courses_for_solve, suggest_fixes, format_suggestions
from src.preferences import SchedulePreferences, filter_sections_for_preferences
from src.course_groups import (
    parse_group_configs,
    expand_course_groups,
    filter_groups_for_solve,
)
from src.selector import select_schedule

console = Console()

BANNER = r"""
  ____  _   _ ____  _____         _
 / ___|| | | / ___||_   _|__  ___| |__
 \___ \| | | \___ \  | |/ _ \/ __| '_ \
  ___) | |_| |___) | | |  __/ (__| | | |
 |____/ \___/|____/  |_|\___|\___|_| |_|

     南科大智能课表规划器 v2.0
"""


def load_config(config_path: str = "config.yaml") -> dict:
    """从配置文件读取完整配置（课程列表 + 可选的登录凭据）。

    Parameters
    ----------
    config_path : str
        配置文件路径，默认为项目根目录下的 config.yaml

    Returns
    -------
    dict
        包含 courses, student_id(可选), password(可选) 的配置字典
    """
    # 先尝试相对于项目根目录
    full_path = PROJECT_ROOT / config_path
    if not full_path.exists():
        # 再尝试相对于当前工作目录
        full_path = Path(config_path)

    if not full_path.exists():
        console.print(f"[red]配置文件 {config_path} 不存在！[/red]")
        console.print(f"请在项目根目录创建 config.yaml，格式如下：\n")
        console.print(
            'courses:\n'
            '  - "高等数学A"\n'
            '  - "线性代数"\n'
            '  - "大学物理A"\n'
        )
        sys.exit(1)

    with open(full_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config:
        console.print("[red]配置文件为空[/red]")
        sys.exit(1)

    courses = config.get("courses") or []
    groups = config.get("course_groups") or []
    if not courses and not groups:
        console.print("[red]配置需至少包含 courses 或 course_groups 之一[/red]")
        sys.exit(1)

    if not isinstance(courses, list):
        console.print("[red]courses 必须是列表[/red]")
        sys.exit(1)

    config["courses"] = [str(c).strip() for c in courses if c]
    return config


def main() -> None:
    """主流程：读取配置 -> 登录 -> 爬取 -> 求解 -> 展示"""
    console.print(Panel(BANNER, border_style="bright_blue", expand=False))

    # 1. 读取配置
    console.print("[bold]步骤 1/4: 读取课程配置[/bold]")
    config = load_config()
    wanted_courses = config["courses"]
    group_configs = parse_group_configs(config.get("course_groups"))
    if wanted_courses:
        console.print(f"[green]已读取 {len(wanted_courses)} 门固定课程:[/green]")
        for i, name in enumerate(wanted_courses, 1):
            console.print(f"  {i}. {name}")
    if group_configs:
        console.print(f"[green]已读取 {len(group_configs)} 个课程组 (N 选 1):[/green]")
        for g in group_configs:
            label = g.category or g.course_type or "candidates"
            console.print(f"  • {g.name}  选 {g.pick} 门  ({label})")
    console.print()

    # 2. 登录 TIS
    console.print("[bold]步骤 2/4: 登录 TIS 系统[/bold]")
    try:
        sid = config.get("student_id", "")
        pwd = config.get("password", "")
        if sid and pwd:
            console.print(f"[*] 使用配置文件中的凭据登录（学号: {sid}）...")
            headers = cas_login(str(sid), str(pwd))
            console.print("[+] 登录成功！")
        else:
            headers = interactive_login()
    except (RuntimeError, ConnectionError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        console.print("[*] 尝试手动登录...")
        try:
            headers = interactive_login()
        except RuntimeError as e2:
            console.print(f"[red]{e2}[/red]")
            sys.exit(1)

    # 3. 获取学期信息和课程数据
    console.print("\n[bold]步骤 3/4: 获取课程数据[/bold]")
    try:
        semester_info = get_semester_info(headers)
        semester_name = {
            "1": "秋季",
            "2": "春季",
            "3": "小学期",
        }.get(str(semester_info.get("p_xq", "")), "未知")
        console.print(
            f"[green]当前学期: {semester_info.get('p_xn', '?')} 学年 "
            f"第 {semester_info.get('p_xq', '?')} 学期 ({semester_name})[/green]\n"
        )
    except Exception as e:
        console.print(f"[red]获取学期信息失败: {e}[/red]")
        sys.exit(1)

    try:
        all_courses = fetch_all_courses(headers, semester_info)

        group_expand = expand_course_groups(group_configs, all_courses)
        for msg in group_expand.warnings:
            console.print(f"  [*] {msg}")
        for msg in group_expand.errors:
            console.print(f"[red]  [!] {msg}[/red]")
        if group_expand.errors and not wanted_courses:
            sys.exit(1)

        selection = get_courses_for_selection(
            headers,
            semester_info,
            wanted_courses,
            all_courses=all_courses,
        ) if wanted_courses else SelectionResult()
        course_groups = group_expand.groups
        while selection.ambiguous:
            resolutions = prompt_disambiguation(selection.ambiguous)
            selection = get_courses_for_selection(
                headers,
                semester_info,
                wanted_courses,
                resolutions=resolutions,
                all_courses=all_courses,
            )
        courses = selection.courses
    except Exception as e:
        console.print(f"[red]获取课程数据失败: {e}[/red]")
        sys.exit(1)

    if not courses and not course_groups:
        console.print("[red]未能获取到任何课程或课程组，请检查配置[/red]")
        sys.exit(1)

    if selection.not_found:
        console.print(
            f"[yellow]警告: {len(selection.not_found)} 门课未找到，将不参与求解[/yellow]"
        )

    # 展示获取到的课程信息
    if courses:
        console.print("\n[bold]已获取的固定课程:[/bold]")
        for course in courses:
            console.print(f"\n  [bright_cyan]{course.name}[/bright_cyan] ({len(course.sections)} 个教学班)")
            for sec in course.sections:
                slots_str = ", ".join(str(ts) for ts in sec.time_slots) or "时间未知"
                console.print(f"    - {sec.section_name}  [dim]{slots_str}[/dim]")

    if course_groups:
        console.print("\n[bold]课程组候选:[/bold]")
        for group in course_groups:
            console.print(
                f"  [bright_cyan]{group.name}[/bright_cyan]: "
                f"选 {group.pick} 门 / {len(group.courses)} 门候选"
            )

    # 4. 获取 NCES 评分
    use_ratings = config.get("use_ratings", True)
    if use_ratings:
        enrich_courses_with_ratings(courses)
        group_flat = [c for g in course_groups for c in g.courses]
        if group_flat:
            enrich_courses_with_ratings(group_flat)

    # 4.5 剪枝
    min_rating = config.get("min_rating")
    if use_ratings and min_rating is None:
        min_rating = 5.0
    max_sections_per_course = config.get("max_sections_per_course", 12)
    max_results = config.get("max_results", 100)
    preferences = SchedulePreferences.from_dict(config.get("preferences"))

    solve_courses, filter_stats = filter_courses_for_solve(
        courses,
        min_rating=min_rating if use_ratings else None,
        max_sections_per_course=max_sections_per_course,
        keep_unrated=True,
    )
    solve_groups = filter_groups_for_solve(
        course_groups,
        min_rating=min_rating if use_ratings else None,
        max_sections_per_course=max_sections_per_course,
        keep_unrated=True,
    )

    if preferences.is_active():
        solve_courses, pref_stats = filter_sections_for_preferences(solve_courses, preferences)
        pref_groups: list = []
        for group in solve_groups:
            filtered_courses, _ = filter_sections_for_preferences(group.courses, preferences)
            if filtered_courses:
                from src.models import CourseGroup
                pref_groups.append(
                    CourseGroup(
                        name=group.name,
                        pick=group.pick,
                        courses=filtered_courses,
                        course_type=group.course_type,
                        category=group.category,
                    )
                )
        solve_groups = pref_groups
        console.print("[bold]已启用课表偏好:[/bold]")
        for line in preferences.summary_lines():
            console.print(f"  • {line}")
    else:
        pref_stats = None

    if not solve_courses and not solve_groups:
        console.print("[red]剪枝后没有可选教学班/课程组，请降低 min_rating 或检查配置[/red]")
        sys.exit(1)

    # 5. 求解
    console.print(f"\n[bold]步骤 5/5: 求解无冲突课表[/bold]")
    console.print(f"[dim]最多保留 {max_results} 种方案（按评分与偏好优先搜索）[/dim]")
    results = solve(
        solve_courses,
        max_results=max_results,
        preferences=preferences,
        course_groups=solve_groups,
    )
    print_solve_summary(
        solve_courses, results, max_results=max_results, course_groups=solve_groups
    )

    if not results:
        hints = diagnose_no_solution(solve_courses)
        if hints:
            console.print("[bold yellow]冲突诊断：[/bold yellow]")
            for hint in hints:
                console.print(f"  • {hint}")
        suggestions = suggest_fixes(
            solve_courses,
            max_results=max_results,
            preferences=preferences,
            all_courses=all_courses,
        )
        if suggestions:
            console.print("[bold yellow]可尝试的调整：[/bold yellow]")
            for msg in format_suggestions(suggestions):
                console.print(f"  • {msg}")
            console.print()

    # 按 NCES 评分排序
    ranked: list[tuple] = []
    if use_ratings and results:
        ranked = rank_schedules(results, preferences=preferences)
        results = [r[0] for r in ranked]
        console.print("[green]已按 NCES 评分总和从高到低排序[/green]\n")
        # 展示前 5 名摘要
        show_top = min(5, len(ranked))
        console.print(f"[bold]评分 TOP {show_top}:[/bold]")
        for i, (_, total, rated, count) in enumerate(ranked[:show_top], 1):
            console.print(
                f"  #{i}  总分 [yellow]{total:.1f}[/yellow]  "
                f"({rated}/{count} 门有评分)"
            )
        console.print()

    # 展示结果并支持选课
    if not results:
        display_all_schedules(results)
        return

    total = len(results)
    console.print(Panel(
        f"共找到 [bold green]{total}[/bold green] 种可行方案\n"
        f"输入 [bold]方案编号[/bold] 查看详情，输入 [bold]s编号[/bold]（如 s1）直接选课，输入 [bold]q[/bold] 退出",
        title="求解结果",
        border_style="green",
    ))

    while True:
        try:
            user_input = input(f"\n请输入操作 (1-{total} 查看 / s1-s{total} 选课 / q 退出): ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() == "q":
            break

        # 选课模式: s1, s2, ...
        if user_input.lower().startswith("s"):
            num_str = user_input[1:]
            if num_str.isdigit():
                idx = int(num_str)
                if 1 <= idx <= total:
                    schedule = results[idx - 1]
                    console.print(f"\n[bold yellow]即将选择方案 {idx}:[/bold yellow]")
                    display_schedule(schedule, idx, total)
                    confirm = input("\n确认选课? 输入 YES 确认，其他取消: ").strip()
                    if confirm == "YES":
                        console.print("\n[bold]开始选课...[/bold]")
                        sel_results = select_schedule(headers, semester_info, schedule)
                        console.print(f"\n[bold]选课完成！[/bold]")
                        ok = sum(1 for _, s, _ in sel_results if s)
                        fail = sum(1 for _, s, _ in sel_results if not s)
                        console.print(f"  成功: [green]{ok}[/green]  失败: [red]{fail}[/red]")
                    else:
                        console.print("[dim]已取消[/dim]")
                    continue

        # 查看模式: 1, 2, ...
        if user_input.isdigit():
            idx = int(user_input)
            if 1 <= idx <= total:
                score_info = ranked[idx - 1] if ranked else None
                if score_info:
                    _, sc, rc, _ = score_info
                    display_schedule(results[idx - 1], idx, total, score=sc, rated_count=rc)
                else:
                    display_schedule(results[idx - 1], idx, total)
                continue

        console.print(f"[yellow]无效输入，请输入 1-{total} 或 s1-s{total}[/yellow]")


if __name__ == "__main__":
    main()
