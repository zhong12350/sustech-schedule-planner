"""课程组：从 TIS 某一类别中 N 选 1，无需列出全部候选课。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .course_match import normalize_course_name
from .models import Course, CourseGroup, Section
from .scraper import COURSE_TYPES


@dataclass
class GroupConfig:
    """用户配置的一条课程组规则。"""

    name: str
    pick: int = 1
    course_type: str = ""
    category: str = ""
    candidates: list[str] = field(default_factory=list)
    max_courses: int = 80


@dataclass
class GroupExpandResult:
    groups: list[CourseGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def category_matches(section_category: str, query: str) -> bool:
    """类别模糊匹配：query 为「人文」可匹配「人文类」「通识选修-人文」。"""
    if not query:
        return True
    if not section_category:
        return False
    q = query.strip()
    c = section_category.strip()
    return q in c or c in q


def _course_best_rating(course: Course) -> float:
    rated = [s.rating for s in course.sections if s.rating is not None]
    return max(rated) if rated else -1.0


def filter_courses_by_rule(
    all_courses: dict[str, list[Section]],
    *,
    course_type: str = "",
    category: str = "",
    candidate_names: list[str] | None = None,
) -> list[Course]:
    """按选课类型 + 类别或候选名列表筛选课程。"""
    if candidate_names:
        out: list[Course] = []
        for name in candidate_names:
            name = name.strip()
            if not name:
                continue
            if name in all_courses:
                out.append(Course(name=name, sections=list(all_courses[name])))
                continue
            norm = normalize_course_name(name)
            for key, secs in all_courses.items():
                if normalize_course_name(key) == norm or normalize_course_name(key).startswith(norm):
                    out.append(Course(name=key, sections=list(secs)))
                    break
        return out

    matched: list[Course] = []
    for key, sections in all_courses.items():
        if not sections:
            continue
        sample = sections[0]
        if course_type and sample.course_type != course_type:
            continue
        if category and not any(category_matches(sec.category, category) for sec in sections):
            continue
        matched.append(Course(name=key, sections=list(sections)))
    return matched


def cap_group_courses(courses: list[Course], max_courses: int) -> list[Course]:
    """限制组内候选课数量（按最高班评分保留）。"""
    if len(courses) <= max_courses:
        return courses
    ranked = sorted(courses, key=lambda c: (-_course_best_rating(c), c.name))
    return ranked[:max_courses]


def list_categories(
    all_courses: dict[str, list[Section]],
    *,
    course_type: str | None = None,
) -> list[dict]:
    """统计 TIS 目录中的类别及课程数（供配置 course_groups 时查阅）。"""
    counts: dict[tuple[str, str], int] = {}
    for _key, sections in all_courses.items():
        if not sections:
            continue
        sec = sections[0]
        if course_type and sec.course_type != course_type:
            continue
        cat = sec.category or "（未标注类别）"
        slot = (sec.course_type, cat)
        counts[slot] = counts.get(slot, 0) + 1

    result = []
    for (ctype, cat), n in sorted(counts.items(), key=lambda x: (x[0][0], x[0][1])):
        result.append({
            "course_type": ctype,
            "course_type_name": COURSE_TYPES.get(ctype, ctype),
            "category": cat,
            "course_count": n,
        })
    return result


def parse_group_configs(raw: list | None) -> list[GroupConfig]:
    if not raw:
        return []
    configs: list[GroupConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        pick = int(item.get("pick") or 1)
        if pick < 1:
            pick = 1
        candidates = item.get("candidates") or []
        if isinstance(candidates, str):
            candidates = [candidates]
        configs.append(
            GroupConfig(
                name=name,
                pick=pick,
                course_type=str(item.get("course_type") or "").strip(),
                category=str(item.get("category") or "").strip(),
                candidates=[str(c).strip() for c in candidates if str(c).strip()],
                max_courses=int(item.get("max_courses") or 80),
            )
        )
    return configs


def expand_course_groups(
    configs: list[GroupConfig],
    all_courses: dict[str, list[Section]],
) -> GroupExpandResult:
    """将课程组配置展开为含候选课的 CourseGroup 列表。"""
    result = GroupExpandResult()
    for cfg in configs:
        if cfg.candidates:
            courses = filter_courses_by_rule(all_courses, candidate_names=cfg.candidates)
        elif cfg.category or cfg.course_type:
            courses = filter_courses_by_rule(
                all_courses,
                course_type=cfg.course_type,
                category=cfg.category,
            )
        else:
            result.errors.append(f"课程组「{cfg.name}」需指定 category/course_type 或 candidates")
            continue

        if not courses:
            hint = cfg.category or cfg.course_type or "candidates"
            result.errors.append(
                f"课程组「{cfg.name}」未匹配到任何课程（条件: {hint}）。"
                "运行 scripts/export_tis_catalog.py 或 Web 查看可用类别"
            )
            continue

        before = len(courses)
        courses = cap_group_courses(courses, cfg.max_courses)
        if before > len(courses):
            result.warnings.append(
                f"课程组「{cfg.name}」候选 {before} 门，已按评分保留 top {len(courses)}"
            )

        type_label = COURSE_TYPES.get(cfg.course_type, cfg.course_type) or "指定列表"
        result.groups.append(
            CourseGroup(
                name=cfg.name,
                pick=cfg.pick,
                courses=courses,
                course_type=cfg.course_type,
                category=cfg.category,
            )
        )
        result.warnings.append(
            f"课程组「{cfg.name}」: 从 {type_label}"
            + (f"/{cfg.category}" if cfg.category else "")
            + f" 载入 {len(courses)} 门候选课，需选 {cfg.pick} 门"
        )
    return result


def filter_groups_for_solve(
    groups: list[CourseGroup],
    *,
    min_rating: float | None = None,
    max_sections_per_course: int | None = None,
    keep_unrated: bool = True,
) -> list[CourseGroup]:
    """对组内每门候选课应用与固定课相同的剪枝。"""
    from .filters import filter_courses_for_solve

    filtered: list[CourseGroup] = []
    for group in groups:
        courses, _ = filter_courses_for_solve(
            group.courses,
            min_rating=min_rating,
            max_sections_per_course=max_sections_per_course,
            keep_unrated=keep_unrated,
        )
        if courses:
            filtered.append(
                CourseGroup(
                    name=group.name,
                    pick=group.pick,
                    courses=courses,
                    course_type=group.course_type,
                    category=group.category,
                )
            )
    return filtered
