"""课表可视化输出：用 rich 库在终端渲染漂亮的课表矩阵"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel

from .models import Section, WEEKDAY_NAMES, PERIOD_TIMES

console = Console()

# 为不同课程分配不同颜色
COLORS = [
    "bright_cyan",
    "bright_green",
    "bright_yellow",
    "bright_magenta",
    "bright_red",
    "bright_blue",
    "deep_sky_blue1",
    "spring_green1",
    "gold1",
    "orchid1",
    "salmon1",
    "turquoise2",
]


def _get_color(index: int) -> str:
    """根据课程索引获取颜色。"""
    return COLORS[index % len(COLORS)]


def display_schedule(
    schedule: list[Section],
    scheme_index: int,
    total_schemes: int,
    score: float | None = None,
    rated_count: int | None = None,
) -> None:
    """在终端以课表矩阵的形式展示一种选课方案。

    Parameters
    ----------
    schedule : list[Section]
        一种可行的选课方案（每门课选择了一个教学班）
    scheme_index : int
        方案编号（从 1 开始）
    total_schemes : int
        总方案数
    """
    # 构建课程名到颜色的映射
    course_names = list(dict.fromkeys(s.course_name for s in schedule))
    color_map: dict[str, str] = {
        name: _get_color(i) for i, name in enumerate(course_names)
    }

    # 构建 5x11 的课表网格 (weekday, period) -> 显示文本
    grid: dict[tuple[int, int], tuple[str, str, str]] = {}  # (wd, p) -> (课程名, 教师, 颜色)

    for section in schedule:
        color = color_map.get(section.course_name, "white")
        for ts in section.time_slots:
            for period in range(ts.start_period, ts.end_period + 1):
                grid[(ts.weekday, period)] = (
                    section.course_name,
                    section.teacher,
                    color,
                )

    # 创建 rich Table
    title = f"方案 {scheme_index}/{total_schemes}"
    if score is not None:
        rated_info = f" ({rated_count}/{len(schedule)} 门有评分)" if rated_count is not None else ""
        title += f"  ★ 总分 {score:.1f}{rated_info}"

    table = Table(
        title=title,
        show_header=True,
        header_style="bold",
        border_style="bright_black",
        title_style="bold bright_white",
        padding=(0, 1),
    )

    # 添加列：节次 + 周一到周五
    table.add_column("节次", style="dim", width=14, justify="center")
    for wd_name in WEEKDAY_NAMES:
        table.add_column(wd_name, width=16, justify="center")

    # 添加行：第 1-11 节
    for period in range(1, 12):
        time_str = PERIOD_TIMES.get(period, "")
        row_label = f"第{period:>2}节\n{time_str}"

        cells: list[Text | str] = [row_label]
        for weekday in range(5):
            entry = grid.get((weekday, period))
            if entry:
                course_name, teacher, color = entry
                # 截断过长的课程名
                display_name = course_name if len(course_name) <= 8 else course_name[:7] + "…"
                cell = Text()
                cell.append(display_name + "\n", style=f"bold {color}")
                if teacher:
                    short_teacher = teacher if len(teacher) <= 6 else teacher[:5] + "…"
                    cell.append(short_teacher, style=f"dim {color}")
                cells.append(cell)
            else:
                cells.append("")

        table.add_row(*cells)

    console.print(table)

    # 打印方案详情
    console.print()
    for section in schedule:
        color = color_map.get(section.course_name, "white")
        slots_str = ", ".join(str(ts) for ts in section.time_slots)
        if not slots_str:
            slots_str = "时间未知"
        rating_str = ""
        if section.rating is not None:
            rating_str = f"  [yellow]★{section.rating:.1f}[/yellow]"
            if section.review_count:
                rating_str += f"[dim]({section.review_count}评)[/dim]"
        console.print(
            f"  [{color}]●[/{color}] {section.course_name}"
            f"  {section.teacher or ''}"
            f"{rating_str}"
            f"  [dim]{slots_str}[/dim]"
        )
    console.print()


def display_all_schedules(results: list[list[Section]]) -> None:
    """展示所有可行的选课方案，支持交互式翻页。

    Parameters
    ----------
    results : list[list[Section]]
        所有可行的选课方案
    """
    if not results:
        console.print(Panel(
            "[bold red]没有找到可行的无冲突课表方案！[/bold red]\n\n"
            "可能的原因：\n"
            "  1. 所选课程之间存在不可避免的时间冲突\n"
            "  2. 某些课程只有一个教学班且与其他课程冲突\n"
            "  3. 课程时间信息获取不完整\n\n"
            "建议：减少一些课程后重试",
            title="求解结果",
            border_style="red",
        ))
        return

    total = len(results)

    if total <= 5:
        # 方案少时直接全部展示
        for i, schedule in enumerate(results, 1):
            display_schedule(schedule, i, total)
            if i < total:
                console.print("[dim]─" * 40 + "[/dim]\n")
    else:
        # 方案多时交互式翻页
        console.print(Panel(
            f"共找到 [bold green]{total}[/bold green] 种可行方案\n"
            f"按 [bold]Enter[/bold] 查看下一个，输入 [bold]q[/bold] 退出，输入 [bold]数字[/bold] 跳转到指定方案",
            title="求解结果",
            border_style="green",
        ))

        idx = 0
        while idx < total:
            display_schedule(results[idx], idx + 1, total)

            if idx < total - 1:
                try:
                    user_input = input(
                        f"\n[方案 {idx + 1}/{total}] "
                        f"Enter=下一个 | q=退出 | 数字=跳转: "
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if user_input.lower() == "q":
                    break
                elif user_input.isdigit():
                    target = int(user_input)
                    if 1 <= target <= total:
                        idx = target - 1
                    else:
                        console.print(f"  [yellow]方案编号应在 1-{total} 之间[/yellow]")
                else:
                    idx += 1
            else:
                console.print(f"[dim]已展示全部 {total} 种方案。[/dim]")
                break
