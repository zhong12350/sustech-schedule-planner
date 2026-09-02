"""课程数据爬取模块：从 TIS 系统获取课程信息并解析时间"""

from __future__ import annotations

import re
import json
import warnings
from collections import defaultdict

import requests
from urllib3.exceptions import InsecureRequestWarning

from .models import Course, Section, TimeSlot, WEEKDAY_MAP
from .preferences import parse_location_from_text
from .course_match import find_matching_course_keys
from .course_selection import SelectionResult, match_courses_from_catalog, prompt_disambiguation

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

TIS_BASE = "https://tis.sustech.edu.cn"
QUERY_SEMESTER_URL = f"{TIS_BASE}/Xsxk/queryXkdqXnxq"
QUERY_COURSES_URL = f"{TIS_BASE}/Xsxk/queryKxrw"

# 六种选课类型
COURSE_TYPES: dict[str, str] = {
    "bxxk": "通识必修选课",
    "xxxk": "通识选修选课",
    "kzyxk": "培养方案内课程",
    "zynknjxk": "非培养方案内课程",
    "cxxk": "重修选课",
    "jhnxk": "计划内选课新生",
}

# 时间正则：匹配 "星期一第1-2节" 这种格式
TIME_PATTERN = re.compile(r"星期([一二三四五六日])第(\d+)-(\d+)节")

LOCATION_FIELDS = ("jxdd", "skdd", "cdmc", "jxbdd", "jsmc")

# 正方 TIS 常见类别字段
CATEGORY_FIELDS = (
    "kclbmc",
    "tsxxlbmc",
    "xkmlmc",
    "kcxzmc",
    "lbmc",
    "kclb",
)


def extract_category_from_item(item: dict) -> str:
    """从 TIS 原始条目提取课程子类/类别名。"""
    for fld in CATEGORY_FIELDS:
        val = item.get(fld)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _extract_time_and_location(item: dict) -> tuple[str, str]:
    """从 TIS 课程条目提取上课时间与地点。"""
    time_str = ""
    location = ""
    for field in LOCATION_FIELDS:
        val = item.get(field)
        if val:
            location = str(val).strip()
            break

    for time_field in ["sksj", "sksjms", "sksjStr", "sksjdd"]:
        if item.get(time_field):
            time_str = str(item[time_field])
            if not location and time_field == "sksjdd":
                location = parse_location_from_text(time_str)
            break

    if not time_str:
        item_str = json.dumps(item, ensure_ascii=False)
        if TIME_PATTERN.search(item_str):
            time_str = item_str
            if not location:
                location = parse_location_from_text(item_str)

    if not location:
        location = parse_location_from_text(time_str)
    return time_str, location


def fetch_selected_courses(
    headers: dict[str, str],
    semester_info: dict,
) -> tuple[list[Section], int, int]:
    """获取当前已选课程列表和积分信息。

    Returns
    -------
    tuple[list[Section], int, int]
        (已选课程教学班列表, 已用积分, 剩余积分)
    """
    # 用 bxxk 类型查询，返回中包含 yxkcList（已选课程）和积分信息
    data = {
        "cxsfmt": 0,
        "p_pylx": 1,
        "p_xn": semester_info["p_xn"],
        "p_xq": semester_info["p_xq"],
        "p_xnxq": semester_info["p_xnxq"],
        "p_xkfsdm": "bxxk",
    }
    resp = requests.post(
        QUERY_COURSES_URL,
        data=data,
        headers=headers,
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()

    selected: list[Section] = []
    yxkc_list = raw.get("yxkcList", [])
    if isinstance(yxkc_list, list):
        for item in yxkc_list:
            course_name = item.get("rwmc", "未知")
            section_id = item.get("id", "")
            teacher = item.get("dgjsmc", "") or ""
            points = item.get("xkxs", "?")

            time_str = ""
            for tf in ["sksj", "sksjms", "sksjStr", "sksjdd"]:
                if item.get(tf):
                    time_str = str(item[tf])
                    break
            if not time_str:
                item_str = json.dumps(item, ensure_ascii=False)
                if TIME_PATTERN.search(item_str):
                    time_str = item_str

            _, location = _extract_time_and_location(item)
            time_slots = parse_time_slots(time_str)
            sec = Section(
                course_name=course_name,
                section_name=f"{course_name} - {teacher}" if teacher else course_name,
                section_id=section_id,
                course_type=item.get("p_xkfsdm", ""),
                time_slots=time_slots,
                teacher=teacher,
                location=location,
            )
            selected.append(sec)

    # 积分信息
    xsxk_page = raw.get("xsxkPage", {})
    xkgz = xsxk_page.get("xkgzszOne", {})
    total_points = int(float(xkgz.get("jfxs", 0))) if xkgz else 0
    used_points = 0
    for item in yxkc_list:
        xkxs = item.get("xkxs")
        if xkxs is not None:
            used_points += int(float(xkxs))
    remaining_points = total_points

    return selected, used_points, remaining_points


def get_semester_info(headers: dict[str, str]) -> dict:
    """获取当前学期信息。

    Returns
    -------
    dict
        包含 p_xn, p_xq, p_xnxq 等字段的字典
    """
    resp = requests.post(
        QUERY_SEMESTER_URL,
        data={"mxpylx": 1},
        headers=headers,
        verify=False,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "p_xn" not in data:
        raise RuntimeError(f"获取学期信息失败，返回数据异常: {resp.text[:200]}")
    return data


def parse_time_slots(time_str: str) -> list[TimeSlot]:
    """从时间描述字符串中解析出 TimeSlot 列表。

    支持的格式示例：
        "星期一第1-2节"
        "星期三第3-4节 星期五第1-2节"（多个时间段）

    Parameters
    ----------
    time_str : str
        包含上课时间信息的字符串

    Returns
    -------
    list[TimeSlot]
    """
    slots: list[TimeSlot] = []
    seen: set[tuple[int, int, int]] = set()
    for match in TIME_PATTERN.finditer(time_str):
        weekday_char = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))
        weekday = WEEKDAY_MAP.get(weekday_char)
        if weekday is not None:
            key = (weekday, start, end)
            if key not in seen:
                seen.add(key)
                slots.append(TimeSlot(weekday=weekday, start_period=start, end_period=end))
    return slots


def fetch_all_courses(
    headers: dict[str, str],
    semester_info: dict,
) -> dict[str, list[Section]]:
    """从 TIS 抓取当前学期所有课程信息。

    Returns
    -------
    dict[str, list[Section]]
        课程名 -> 该课程所有教学班列表
    """
    course_map: dict[str, list[Section]] = defaultdict(list)

    for c_type, c_name in COURSE_TYPES.items():
        print(f"  [*] 获取 {c_name} 列表...")

        page_num = 1
        page_size = 500  # TIS 服务端分页上限为 500
        total_fetched = 0

        while True:
            data = {
                "p_xn": semester_info["p_xn"],
                "p_xq": semester_info["p_xq"],
                "p_xnxq": semester_info["p_xnxq"],
                "p_pylx": 1,
                "mxpylx": 1,
                "p_xkfsdm": c_type,
                "pageNum": page_num,
                "pageSize": page_size,
            }

            try:
                resp = requests.post(
                    QUERY_COURSES_URL,
                    data=data,
                    headers=headers,
                    verify=False,
                    timeout=30,
                )
                resp.raise_for_status()
                raw = resp.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                print(f"  [!] 获取 {c_name} 第{page_num}页失败: {e}")
                break

            course_list = raw.get("kxrwList", {})
            if isinstance(course_list, dict):
                course_list = course_list.get("list", [])
            elif not isinstance(course_list, list):
                course_list = []

            if not course_list:
                break

            for item in course_list:
                course_name = item.get("rwmc", "未知课程")
                section_name = item.get("rwmc", course_name)
                section_id = item.get("id", "")
                teacher = item.get("dgjsmc", "") or ""

                time_str, location = _extract_time_and_location(item)
                category = extract_category_from_item(item)

                time_slots = parse_time_slots(time_str)

                # 构建教学班显示名：课程名 + 教师
                display_name = section_name
                if teacher:
                    display_name = f"{section_name} - {teacher}"

                section = Section(
                    course_name=course_name,
                    section_name=display_name,
                    section_id=section_id,
                    course_type=c_type,
                    category=category,
                    time_slots=time_slots,
                    teacher=teacher,
                    location=location,
                )
                course_map[course_name].append(section)

            total_fetched += len(course_list)

            # 如果本页数量不足 page_size，说明已经是最后一页
            if len(course_list) < page_size:
                break

            # 还有更多页，继续获取
            page_num += 1
            print(f"  [*] {c_name}: 已获取 {total_fetched} 个，继续获取第 {page_num} 页...")

        if total_fetched > 0:
            print(f"  [+] {c_name}: 共获取到 {total_fetched} 个教学班")

    total = sum(len(secs) for secs in course_map.values())
    print(f"[+] 课程信息获取完毕，共 {len(course_map)} 门课程，{total} 个教学班")
    return dict(course_map)


def get_courses_for_selection(
    headers: dict[str, str],
    semester_info: dict,
    wanted_course_names: list[str],
    *,
    resolutions: dict[str, str] | None = None,
    all_courses: dict[str, list[Section]] | None = None,
) -> SelectionResult:
    """获取用户想选的课程及其所有教学班。

    Parameters
    ----------
    headers : dict[str, str]
        已登录的请求头
    semester_info : dict
        学期信息
    wanted_course_names : list[str]
        用户想选的课程名列表
    resolutions : dict[str, str] | None
        歧义消解：用户输入 -> 选定的课程 identity
    all_courses : dict | None
        已缓存的 TIS 课程目录（避免重复拉取）

    Returns
    -------
    SelectionResult
        匹配结果，含 courses / not_found / ambiguous
    """
    if all_courses is None:
        print("[*] 从 TIS 获取课程数据...")
        all_courses = fetch_all_courses(headers, semester_info)

    # 硬编码：TIS API 无法查到但确实存在的课程
    _HARDCODED: dict[str, list[Section]] = {
        "数理逻辑导论": [
            Section(
                course_name="数理逻辑导论",
                section_name="数理逻辑导论-01班-英文 - 陶伊达",
                section_id="CS104-01",
                course_type="zynknjxk",
                time_slots=[TimeSlot(weekday=2, start_period=3, end_period=4)],
                teacher="陶伊达",
            ),
        ],
    }
    for hc_name, hc_sections in _HARDCODED.items():
        if hc_name not in all_courses:
            all_courses[hc_name] = hc_sections
            print(f"  [*] 补充硬编码课程: {hc_name}")

    selection = match_courses_from_catalog(
        wanted_course_names,
        all_courses,
        resolutions=resolutions,
        semester_label=(
            f"{semester_info.get('p_xn', '?')} 第{semester_info.get('p_xq', '?')}学期"
        ),
    )

    for line in selection.match_log:
        print(f"  [*] {line}")

    if selection.not_found:
        print(f"\n[!] 以下课程未在 TIS 中找到:")
        for name in selection.not_found:
            print(f"    - {name}")
        print("    请检查课程名是否与 TIS 系统中的完全一致\n")

    if selection.ambiguous:
        print(f"\n[?] 以下课程存在歧义，需要确认:")
        for match in selection.ambiguous:
            ids = " / ".join(o.identity for o in match.options)
            print(f"    - \"{match.query}\" 可能指: {ids}")

    return selection
