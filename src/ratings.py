"""牛娃课程评价社区 (NCES) 评分数据获取与匹配"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from urllib3.exceptions import InsecureRequestWarning
import warnings

from .models import Course, Section

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

NCES_BASE = "https://nces.cra.moe"
NCES_SEARCH_URL = f"{NCES_BASE}/api/v1/search"


@dataclass
class CourseRating:
    """一门课（特定教师）在 NCES 上的评分"""

    course_name: str
    teacher: str
    rate_average: float
    review_count: int
    nces_id: int | None = None
    difficulty_score: float | None = None
    homework_score: float | None = None
    grading_score: float | None = None
    gain_score: float | None = None


def _normalize_name(name: str) -> str:
    """标准化名称用于模糊匹配。"""
    name = name.strip()
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"[（(].*?[）)]", "", name)
    return name


def _teachers_match(tis_teacher: str, nces_teacher: str) -> bool:
    """判断 TIS 教师名与 NCES 教师名是否匹配。"""
    if not tis_teacher or not nces_teacher:
        return False

    t_norm = _normalize_name(tis_teacher)
    n_norm = _normalize_name(nces_teacher)

    if t_norm == n_norm:
        return True
    if t_norm in n_norm or n_norm in t_norm:
        return True

    # TIS 可能包含多个教师，如 "王晓方, 李传锋"
    t_parts = re.split(r"[,，、/]", tis_teacher)
    for part in t_parts:
        part = _normalize_name(part)
        if part and (part == n_norm or part in n_norm or n_norm in part):
            return True

    return False


def search_course_ratings(course_name: str) -> list[CourseRating]:
    """从 NCES 搜索某门课的所有教师评分。

    Parameters
    ----------
    course_name : str
        课程名称（与 TIS 一致）

    Returns
    -------
    list[CourseRating]
        该课程在 NCES 上所有教师的评分记录
    """
    try:
        resp = requests.get(
            NCES_SEARCH_URL,
            params={"q": course_name},
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  [!] NCES 查询 \"{course_name}\" 失败: {e}")
        return []

    items = data.get("courses", {})
    if isinstance(items, dict):
        items = items.get("items", [])
    elif not isinstance(items, list):
        items = []

    ratings: list[CourseRating] = []
    for item in items:
        name = item.get("name", "")
        # 只保留课程名匹配的结果
        if _normalize_name(course_name) not in _normalize_name(name) and \
           _normalize_name(name) not in _normalize_name(course_name):
            continue

        teacher = item.get("teacher_names", "") or ""
        rate = item.get("rate_average")
        if rate is None:
            continue

        def _to_float(v) -> float | None:
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        ratings.append(CourseRating(
            course_name=name,
            teacher=teacher,
            rate_average=float(rate),
            review_count=int(item.get("review_count", 0)),
            nces_id=item.get("id"),
            difficulty_score=_to_float(item.get("difficulty_score")),
            homework_score=_to_float(item.get("homework_score")),
            grading_score=_to_float(item.get("grading_score")),
            gain_score=_to_float(item.get("gain_score")),
        ))

    return ratings


def match_section_rating(
    section: Section,
    ratings_cache: dict[str, list[CourseRating]],
) -> CourseRating | None:
    """为单个教学班匹配 NCES 评分。

    Parameters
    ----------
    section : Section
        TIS 教学班
    ratings_cache : dict[str, list[CourseRating]]
        课程名 -> NCES 评分列表的缓存

    Returns
    -------
    CourseRating | None
        匹配到的评分，未找到则返回 None
    """
    course_ratings = ratings_cache.get(section.course_name, [])
    if not course_ratings:
        # 尝试用标准化名称查找
        norm = _normalize_name(section.course_name)
        for key, vals in ratings_cache.items():
            if _normalize_name(key) == norm:
                course_ratings = vals
                break

    if not section.teacher:
        # 无教师信息时，若该课只有一个评分记录则使用它
        if len(course_ratings) == 1:
            return course_ratings[0]
        return None

    for rating in course_ratings:
        if _teachers_match(section.teacher, rating.teacher):
            return rating

    return None


def enrich_courses_with_ratings(
    courses: list[Course],
    verbose: bool = True,
) -> dict[str, list[CourseRating]]:
    """为所有课程获取 NCES 评分并写入 Section 对象。

    Parameters
    ----------
    courses : list[Course]
        待选课程列表
    verbose : bool
        是否打印进度信息

    Returns
    -------
    dict[str, list[CourseRating]]
        课程名 -> NCES 评分列表的缓存
    """
    if verbose:
        print("\n[*] 从牛娃课程评价社区 (NCES) 获取评分...")

    cache: dict[str, list[CourseRating]] = {}
    matched = 0
    total = 0

    for course in courses:
        if course.name not in cache:
            cache[course.name] = search_course_ratings(course.name)
            if verbose and cache[course.name]:
                print(f"  [+] {course.name}: 找到 {len(cache[course.name])} 条 NCES 评分")

        for section in course.sections:
            total += 1
            rating = match_section_rating(section, cache)
            if rating:
                section.rating = rating.rate_average
                section.review_count = rating.review_count
                section.rating_source = "NCES"
                section.grading_score = rating.grading_score
                section.gain_score = rating.gain_score
                matched += 1
            else:
                section.rating = None
                section.review_count = 0

    if verbose:
        print(f"[+] NCES 评分匹配: {matched}/{total} 个教学班")

    return cache


def score_schedule(schedule: list[Section]) -> tuple[float, int, int]:
    """计算一个课表方案的总评分。

    Returns
    -------
    tuple[float, int, int]
        (总分, 有评分的课程数, 总课程数)
    """
    total = 0.0
    rated = 0
    for section in schedule:
        if section.rating is not None:
            total += section.rating
            rated += 1
    return total, rated, len(schedule)


def rank_schedules(
    schedules: list[list[Section]],
) -> list[tuple[list[Section], float, int, int]]:
    """按 NCES 评分总和从高到低排序课表方案。

    Returns
    -------
    list[tuple[list[Section], float, int, int]]
        (方案, 总分, 有评分数, 总课程数) 列表，按总分降序
    """
    scored = []
    for schedule in schedules:
        total, rated, count = score_schedule(schedule)
        scored.append((schedule, total, rated, count))

    scored.sort(key=lambda x: (-x[1], -x[2]))
    return scored
