#!/usr/bin/env python3
"""南科大增量选课工具 - 基于已选课程，挑选不冲突的教学班并提交"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import cas_login, interactive_login
from src.scraper import (
    get_semester_info,
    fetch_all_courses,
    fetch_selected_courses,
    parse_time_slots,
    TIME_PATTERN,
    COURSE_TYPES,
)
from src.models import Section, TimeSlot, Course, WEEKDAY_NAMES, PERIOD_TIMES
from src.selector import select_course

console = Console()


def load_config() -> dict:
    full_path = PROJECT_ROOT / "config.yaml"
    if not full_path.exists():
        full_path = Path("config.yaml")
    if not full_path.exists():
        console.print("[red]config.yaml 不存在[/red]")
        sys.exit(1)
    with open(full_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_occupied(sections: list[Section]) -> set[tuple[int, int]]:
    """从一组教学班中提取所有已占用的时间槽。"""
    occupied: set[tuple[int, int]] = set()
    for sec in sections:
        for ts in sec.time_slots:
            for p in range(ts.start_period, ts.end_period + 1):
                occupied.add((ts.weekday, p))
    return occupied


def has_conflict(section: Section, occupied: set[tuple[int, int]]) -> bool:
    for ts in section.time_slots:
        for p in range(ts.start_period, ts.end_period + 1):
            if (ts.weekday, p) in occupied:
                return True
    return False


def print_current_schedule(selected: list[Section], used_pts: int, remain_pts: int) -> None:
    """展示当前已选课表。"""
    console.print(Panel(
        f"已选 [bold green]{len(selected)}[/bold green] 门课  |  "
        f"已用积分: [yellow]{used_pts}[/yellow]  |  "
        f"剩余积分: [cyan]{remain_pts}[/cyan]",
        title="当前已选课程",
        border_style="blue",
    ))

    # 构建课表网格
    grid: dict[tuple[int, int], str] = {}
    for sec in selected:
        label = sec.course_name
        if len(label) > 8:
            label = label[:7] + "…"
        for ts in sec.time_slots:
            for p in range(ts.start_period, ts.end_period + 1):
                grid[(ts.weekday, p)] = label

    table = Table(show_header=True, header_style="bold", border_style="bright_black", padding=(0, 1))
    table.add_column("节次", style="dim", width=14, justify="center")
    for wd in WEEKDAY_NAMES:
        table.add_column(wd, width=14, justify="center")

    for period in range(1, 12):
        time_str = PERIOD_TIMES.get(period, "")
        cells: list[str] = [f"第{period:>2}节\n{time_str}"]
        for wd in range(5):
            cells.append(grid.get((wd, period), ""))
        table.add_row(*cells)

    console.print(table)

    for sec in selected:
        slots = ", ".join(str(ts) for ts in sec.time_slots) or "时间未知"
        console.print(f"  [green]●[/green] {sec.course_name}  {sec.teacher}  [dim]{slots}[/dim]")
    console.print()


def show_available_sections(
    course_name: str,
    sections: list[Section],
    occupied: set[tuple[int, int]],
) -> list[Section]:
    """展示某门课中与已选课表不冲突的教学班，返回可选列表。"""
    available: list[Section] = []
    conflicted: list[Section] = []

    for sec in sections:
        if not sec.time_slots or not has_conflict(sec, occupied):
            available.append(sec)
        else:
            conflicted.append(sec)

    if not available:
        console.print(f"  [red]该课程所有教学班均与已选课表冲突！[/red]")
        return []

    console.print(f"\n[bold bright_cyan]{course_name}[/bold bright_cyan] - "
                  f"[green]{len(available)}[/green] 个不冲突 / "
                  f"[red]{len(conflicted)}[/red] 个冲突\n")

    table = Table(show_header=True, border_style="bright_black", padding=(0, 1))
    table.add_column("#", style="bold", width=4, justify="right")
    table.add_column("教学班", width=30)
    table.add_column("教师", width=12)
    table.add_column("时间", width=30)

    for i, sec in enumerate(available, 1):
        slots = ", ".join(str(ts) for ts in sec.time_slots) or "时间未知"
        table.add_row(str(i), sec.section_name, sec.teacher, slots)

    console.print(table)
    return available


def main() -> None:
    console.print(Panel(
        "[bold]南科大增量选课工具[/bold]\n"
        "查看已选 → 找不冲突的教学班 → 挑选提交",
        border_style="bright_blue",
        expand=False,
    ))

    # 登录
    config = load_config()
    sid = config.get("student_id", "")
    pwd = config.get("password", "")
    if sid and pwd:
        console.print(f"[*] 登录中（学号: {sid}）...")
        try:
            headers = cas_login(str(sid), str(pwd))
            console.print("[+] 登录成功！\n")
        except Exception as e:
            console.print(f"[red]{e}[/red]")
            headers = interactive_login()
    else:
        headers = interactive_login()

    semester_info = get_semester_info(headers)
    semester_name = {"1": "秋", "2": "春", "3": "夏"}.get(str(semester_info.get("p_xq", "")), "?")
    console.print(f"学期: {semester_info.get('p_xn', '?')} {semester_name}季\n")

    # 获取已选课程
    console.print("[bold]获取已选课程...[/bold]")
    selected, used_pts, remain_pts = fetch_selected_courses(headers, semester_info)
    print_current_schedule(selected, used_pts, remain_pts)
    occupied = get_occupied(selected)

    # 获取全部课程数据
    console.print("[bold]获取全部课程数据...[/bold]")
    all_courses = fetch_all_courses(headers, semester_info)

    # 硬编码补充
    if "数理逻辑导论" not in all_courses:
        all_courses["数理逻辑导论"] = [
            Section(
                course_name="数理逻辑导论",
                section_name="数理逻辑导论-01班-英文 - 陶伊达",
                section_id="CS104-01",
                course_type="zynknjxk",
                time_slots=[TimeSlot(weekday=2, start_period=3, end_period=4)],
                teacher="陶伊达",
            ),
        ]

    wanted = config.get("courses", [])
    wanted = [str(c).strip() for c in wanted if c and str(c).strip()]

    # 已选课程名集合（去重）
    selected_names = {sec.course_name for sec in selected}

    # 主循环
    while True:
        console.print("\n" + "=" * 50)
        console.print("[bold]待选课程列表:[/bold]")
        pending: list[tuple[str, list[Section]]] = []

        for name in wanted:
            # 检查是否已选
            if any(name in sn for sn in selected_names):
                console.print(f"  [dim]✓ {name} (已选)[/dim]")
                continue

            # 匹配课程
            matched_sections: list[Section] = []
            if name in all_courses:
                matched_sections = all_courses[name]
            else:
                for cn, secs in all_courses.items():
                    if name in cn or cn in name:
                        matched_sections.extend(secs)

            if not matched_sections:
                console.print(f"  [red]✗ {name} (未找到)[/red]")
                continue

            avail_count = sum(1 for s in matched_sections if not has_conflict(s, occupied))
            total_count = len(matched_sections)
            console.print(
                f"  [yellow]○ {name}[/yellow]  "
                f"({avail_count}/{total_count} 个教学班不冲突)"
            )
            pending.append((name, matched_sections))

        if not pending:
            console.print("\n[green]所有课程已选完或无可选教学班！[/green]")
            break

        console.print(f"\n输入课程序号(1-{len(pending)})展开选择，[bold]r[/bold] 刷新已选状态，[bold]q[/bold] 退出")

        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd.lower() == "q":
            break

        if cmd.lower() == "r":
            console.print("[*] 刷新已选课程...")
            selected, used_pts, remain_pts = fetch_selected_courses(headers, semester_info)
            print_current_schedule(selected, used_pts, remain_pts)
            occupied = get_occupied(selected)
            selected_names = {sec.course_name for sec in selected}
            continue

        if not cmd.isdigit() or not (1 <= int(cmd) <= len(pending)):
            console.print("[yellow]无效输入[/yellow]")
            continue

        course_name, sections = pending[int(cmd) - 1]
        available = show_available_sections(course_name, sections, occupied)
        if not available:
            continue

        console.print(f"\n输入教学班序号选课，或 [bold]0[/bold] 返回")
        try:
            pick = input(f"选择教学班 (1-{len(available)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            continue

        if not pick.isdigit() or not (1 <= int(pick) <= len(available)):
            continue

        chosen = available[int(pick) - 1]

        # 硬编码课程提示
        if chosen.section_id.startswith("CS104"):
            console.print(f"[yellow]{chosen.course_name} 是手动硬编码课程，需在 TIS 网页手动选课[/yellow]")
            continue

        # 输入积分
        try:
            pts_input = input(f"分配积分 (剩余 {remain_pts}，直接回车=1): ").strip()
        except (EOFError, KeyboardInterrupt):
            continue
        pts = int(pts_input) if pts_input.isdigit() else 1

        slots_str = ", ".join(str(ts) for ts in chosen.time_slots)
        console.print(f"\n即将选课:")
        console.print(f"  课程: [bold]{chosen.course_name}[/bold]")
        console.print(f"  教学班: {chosen.section_name}")
        console.print(f"  时间: {slots_str}")
        console.print(f"  积分: {pts}")

        try:
            confirm = input("确认? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            continue

        if confirm != "y":
            console.print("[dim]已取消[/dim]")
            continue

        console.print("[*] 提交选课请求...", end=" ")
        success, msg = select_course(headers, semester_info, chosen)
        if success:
            console.print(f"[bold green]成功![/bold green] {msg}")
            # 更新本地状态
            selected.append(chosen)
            occupied = get_occupied(selected)
            selected_names.add(chosen.course_name)
            if pts_input.isdigit():
                used_pts += pts
                remain_pts -= pts
        else:
            console.print(f"[bold red]失败[/bold red] {msg}")

    console.print("\n[dim]再见！[/dim]")


if __name__ == "__main__":
    main()
