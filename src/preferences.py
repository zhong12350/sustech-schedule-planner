"""课表偏好：硬约束过滤 + 地点邻近软排序。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Course, Section, TimeSlot

TIME_PATTERN = re.compile(r"星期[一二三四五六日]第\d+-\d+节")
WEEK_MARKER = re.compile(r"\{[^}]*\}")

# 南科大常见教学楼 -> 校区分区（用于估算步行距离）
BUILDING_ZONES: list[tuple[str, int]] = [
    ("理学院", 0),
    ("工学院", 1),
    ("学生活动中心", 0),
    ("活动中心", 0),
    ("图书馆", 0),
    ("第一科研楼", 2),
    ("第二科研楼", 2),
    ("科研楼", 2),
    ("创园", 3),
    ("创新园", 3),
    ("慧园", 4),
    ("荔园", 4),
    ("体育馆", 5),
    ("松禾体育馆", 5),
    ("润杨", 6),
    ("致仁", 6),
    ("致新", 6),
    ("致诚", 6),
]

# 分区间近似步行代价（越大越远）
_ZONE_DISTANCE: dict[tuple[int, int], int] = {}
for a in range(7):
    for b in range(7):
        _ZONE_DISTANCE[(a, b)] = abs(a - b)


@dataclass
class SchedulePreferences:
    """用户课表偏好。"""

    no_early_morning: bool = False
    max_consecutive_periods: int | None = None
    min_free_days: int = 0
    prefer_nearby_locations: bool = False
    location_weight: float = 1.0

    @classmethod
    def from_dict(cls, data: dict | None) -> SchedulePreferences:
        if not data:
            return cls()
        max_consec = data.get("max_consecutive_periods")
        if max_consec is not None:
            max_consec = int(max_consec)
            if max_consec <= 0:
                max_consec = None
        min_free = int(data.get("min_free_days") or 0)
        if min_free < 0:
            min_free = 0
        return cls(
            no_early_morning=bool(data.get("no_early_morning", False)),
            max_consecutive_periods=max_consec,
            min_free_days=min_free,
            prefer_nearby_locations=bool(data.get("prefer_nearby_locations", False)),
            location_weight=float(data.get("location_weight", 1.0)),
        )

    def is_active(self) -> bool:
        return (
            self.no_early_morning
            or self.max_consecutive_periods is not None
            or self.min_free_days > 0
            or self.prefer_nearby_locations
        )

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.no_early_morning:
            lines.append("不上早八（第 1 节）")
        if self.max_consecutive_periods is not None:
            lines.append(f"同一天连堂不超过 {self.max_consecutive_periods} 节")
        if self.min_free_days > 0:
            lines.append(f"每周至少 {self.min_free_days} 天空课")
        if self.prefer_nearby_locations:
            lines.append("优先同一天地点相近")
        return lines


@dataclass
class PreferenceFilterStats:
    removed_early_morning: int = 0


def parse_location_from_text(text: str) -> str:
    """从 TIS 时间/地点混合字符串中提取地点。"""
    if not text:
        return ""
    cleaned = WEEK_MARKER.sub("", text)
    cleaned = TIME_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"[;；,，\s]+", " ", cleaned).strip()
    return cleaned


def location_zone(location: str) -> int | None:
    """将地点字符串映射到 campus 分区 ID。"""
    if not location:
        return None
    for prefix, zone in BUILDING_ZONES:
        if prefix in location:
            return zone
    return None


def zone_distance(a: int | None, b: int | None) -> int:
    if a is None or b is None:
        return 0
    return _ZONE_DISTANCE.get((a, b), abs(a - b))


def section_has_early_morning(section: Section) -> bool:
    for ts in section.time_slots:
        if ts.start_period <= 1 <= ts.end_period:
            return True
    return False


def _occupied_by_weekday(schedule: list[Section]) -> dict[int, set[int]]:
    by_day: dict[int, set[int]] = {d: set() for d in range(5)}
    for sec in schedule:
        for wd, period in sec.all_periods():
            if wd < 5:
                by_day.setdefault(wd, set()).add(period)
    return by_day


def max_consecutive_on_day(periods: set[int]) -> int:
    if not periods:
        return 0
    sorted_p = sorted(periods)
    best = 1
    run = 1
    for i in range(1, len(sorted_p)):
        if sorted_p[i] == sorted_p[i - 1] + 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def schedule_max_consecutive(schedule: list[Section]) -> int:
    by_day = _occupied_by_weekday(schedule)
    return max((max_consecutive_on_day(p) for p in by_day.values()), default=0)


def schedule_free_days(schedule: list[Section], weekdays: range = range(5)) -> int:
    by_day = _occupied_by_weekday(schedule)
    return sum(1 for d in weekdays if not by_day.get(d))


def schedule_location_penalty(schedule: list[Section]) -> float:
    """同一天相邻课程的分区距离之和（越小越好）。"""
    by_day: dict[int, list[tuple[int, int | None]]] = {}
    for sec in schedule:
        zone = location_zone(sec.location)
        for ts in sec.time_slots:
            if ts.weekday >= 5:
                continue
            by_day.setdefault(ts.weekday, []).append((ts.start_period, zone))

    penalty = 0.0
    for entries in by_day.values():
        entries.sort(key=lambda x: x[0])
        for i in range(1, len(entries)):
            penalty += zone_distance(entries[i - 1][1], entries[i][1])
    return penalty


def section_violates_preferences(section: Section, prefs: SchedulePreferences) -> bool:
    if prefs.no_early_morning and section_has_early_morning(section):
        return True
    return False


def schedule_violates_preferences(schedule: list[Section], prefs: SchedulePreferences) -> bool:
    if prefs.max_consecutive_periods is not None:
        if schedule_max_consecutive(schedule) > prefs.max_consecutive_periods:
            return True
    if prefs.min_free_days > 0:
        if schedule_free_days(schedule) < prefs.min_free_days:
            return True
    return False


def filter_sections_for_preferences(
    courses: list[Course],
    prefs: SchedulePreferences,
) -> tuple[list[Course], PreferenceFilterStats]:
    """按偏好剔除不可选教学班（如早八）。"""
    if not prefs.no_early_morning:
        return courses, PreferenceFilterStats()

    stats = PreferenceFilterStats()
    filtered: list[Course] = []
    for course in courses:
        kept = [s for s in course.sections if not section_violates_preferences(s, prefs)]
        stats.removed_early_morning += len(course.sections) - len(kept)
        if kept:
            filtered.append(Course(name=course.name, sections=kept))
    return filtered, stats


def preference_sort_key(schedule: list[Section], prefs: SchedulePreferences) -> tuple:
    """排序键：地点惩罚越低越好（仅 soft pref 生效）。"""
    loc_penalty = schedule_location_penalty(schedule) if prefs.prefer_nearby_locations else 0.0
    free_bonus = schedule_free_days(schedule) if prefs.min_free_days > 0 else 0
    return (loc_penalty / max(prefs.location_weight, 0.01), -free_bonus)
