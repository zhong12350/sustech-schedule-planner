"""课程匹配与 TIS 数据获取的辅助函数。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .course_match import CourseMatchResult, resolve_course_match
from .models import Course, Section
from .aliases import log_match_miss


@dataclass
class SelectionResult:
    """批量课程匹配的结果。"""

    courses: list[Course] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    ambiguous: list[CourseMatchResult] = field(default_factory=list)
    match_log: list[str] = field(default_factory=list)


def match_courses_from_catalog(
    wanted_course_names: list[str],
    all_courses: dict[str, list[Section]],
    *,
    resolutions: dict[str, str] | None = None,
    semester_label: str = "",
) -> SelectionResult:
    """从已拉取的 TIS 课程目录中匹配用户输入。

    Parameters
    ----------
    wanted_course_names : list[str]
        用户想选的课程名
    all_courses : dict[str, list[Section]]
        TIS 课程 key -> 教学班列表
    resolutions : dict[str, str] | None
        歧义消解：用户输入 -> 选定的课程 identity
    """
    resolutions = resolutions or {}
    all_keys = list(all_courses.keys())
    result = SelectionResult()

    for name in wanted_course_names:
        name = name.strip()
        if not name:
            continue

        match = resolve_course_match(
            name,
            all_keys,
            section_meta=all_courses,
            chosen_identity=resolutions.get(name),
        )

        if match.status == "ambiguous":
            result.ambiguous.append(match)
            continue

        if match.status == "not_found":
            result.not_found.append(name)
            log_match_miss(name, match.near_misses, semester=semester_label)
            if match.near_misses:
                result.match_log.append(f"\"{name}\" 未找到，最接近的候选：")
                for key, score in match.near_misses[:3]:
                    result.match_log.append(f"  - {key}  (相似度 {score:.0%})")
                result.match_log.append(
                    "  提示: 可在 tis_course_aliases.yaml 添加别名，"
                    "或运行 scripts/export_tis_catalog.py 查正式课名"
                )
            continue

        # exact / matched / alias
        all_sections: list[Section] = []
        for key in match.keys:
            all_sections.extend(all_courses[key])

        if match.status == "alias":
            result.match_log.append(
                f"别名匹配: \"{name}\" -> \"{match.alias_target}\" "
                f"({len(all_sections)} 个教学班)"
            )
        elif match.status == "exact":
            result.match_log.append(f"精确匹配: \"{name}\" ({len(all_sections)} 个教学班)")
        else:
            identities = {s.course_name for s in all_sections[:1]}
            display = next(iter(identities), match.keys[0])
            result.match_log.append(
                f"相似度匹配 ({match.score:.0%}): \"{name}\" -> \"{display}\" "
                f"({len(all_sections)} 个教学班)"
            )

        result.courses.append(Course(name=name, sections=all_sections))

    return result


def prompt_disambiguation(ambiguous: list[CourseMatchResult]) -> dict[str, str]:
    """CLI 交互式歧义消解。"""
    resolutions: dict[str, str] = {}
    for match in ambiguous:
        print(f"\n[?] \"{match.query}\" 匹配到多个不同课程，请选择：")
        for i, opt in enumerate(match.options, 1):
            teachers = "、".join(opt.teachers[:3]) if opt.teachers else "教师未知"
            print(
                f"  {i}. {opt.identity}  "
                f"({opt.section_count} 个教学班, 相似度 {opt.score:.0%}, 教师: {teachers})"
            )
        while True:
            try:
                choice = input(f"请输入序号 (1-{len(match.options)}): ").strip()
            except (EOFError, KeyboardInterrupt):
                raise SystemExit(0) from None
            if choice.isdigit() and 1 <= int(choice) <= len(match.options):
                resolutions[match.query] = match.options[int(choice) - 1].identity
                break
            print("  无效输入，请重试")
    return resolutions
