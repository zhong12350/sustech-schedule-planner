"""数据模型：TimeSlot, Section, Course"""

from __future__ import annotations

from dataclasses import dataclass, field


# 南科大每日 11 节课对应的实际时间
PERIOD_TIMES: dict[int, str] = {
    1: "08:00-08:50",
    2: "09:00-09:50",
    3: "10:20-11:10",
    4: "11:20-12:10",
    5: "14:00-14:50",
    6: "15:00-15:50",
    7: "16:20-17:10",
    8: "17:20-18:10",
    9: "19:00-19:50",
    10: "20:00-20:50",
    11: "21:10-22:00",
}

WEEKDAY_NAMES: list[str] = ["周一", "周二", "周三", "周四", "周五"]

WEEKDAY_MAP: dict[str, int] = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
}


@dataclass
class TimeSlot:
    """一段连续的上课时间"""

    weekday: int  # 0=周一, 4=周五
    start_period: int  # 第几节开始 (1-11)
    end_period: int  # 第几节结束 (1-11)

    def periods(self) -> list[tuple[int, int]]:
        """返回该时间段占用的所有 (weekday, period) 元组"""
        return [(self.weekday, p) for p in range(self.start_period, self.end_period + 1)]

    def __str__(self) -> str:
        wd = WEEKDAY_NAMES[self.weekday] if self.weekday < len(WEEKDAY_NAMES) else f"星期{self.weekday}"
        return f"{wd} 第{self.start_period}-{self.end_period}节"


@dataclass
class Section:
    """一个教学班（同一门课可能有多个教学班）"""

    course_name: str  # 课程名称
    section_name: str  # 教学班名称（通常含教师信息）
    section_id: str  # TIS 系统内部 ID
    course_type: str  # 选课类型代码 (bxxk, xxxk, ...)
    time_slots: list[TimeSlot] = field(default_factory=list)
    teacher: str = ""  # 授课教师
    location: str = ""  # 上课地点
    rating: float | None = None  # NCES 综合评分 (0-10)
    review_count: int = 0  # NCES 评价人数
    rating_source: str = ""  # 评分来源，如 "NCES"
    grading_score: float | None = None  # NCES 给分评分
    gain_score: float | None = None  # NCES 收获评分

    def all_periods(self) -> set[tuple[int, int]]:
        """返回该教学班占用的全部时间槽集合"""
        result: set[tuple[int, int]] = set()
        for ts in self.time_slots:
            result.update(ts.periods())
        return result

    def __str__(self) -> str:
        slots_str = ", ".join(str(ts) for ts in self.time_slots)
        teacher_info = f" ({self.teacher})" if self.teacher else ""
        return f"{self.section_name}{teacher_info} [{slots_str}]"


@dataclass
class Course:
    """一门课程，包含所有可选的教学班"""

    name: str
    sections: list[Section] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.name} ({len(self.sections)} 个教学班)"
