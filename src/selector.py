"""选课模块：向 TIS 提交选课请求"""

from __future__ import annotations

import time
import warnings

import requests
from urllib3.exceptions import InsecureRequestWarning

from .models import Section

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

SELECT_URL = "https://tis.sustech.edu.cn/Xsxk/addGouwuche"


def select_course(
    headers: dict[str, str],
    semester_info: dict,
    section: Section,
    to_selected: bool = True,
) -> tuple[bool, str]:
    """提交一门课的选课请求。

    Returns
    -------
    tuple[bool, str]
        (是否成功, 服务端返回消息)
    """
    data = {
        "p_pylx": 1,
        "p_xktjz": "rwtjzyx" if to_selected else "rwtjzgwc",
        "p_xn": semester_info["p_xn"],
        "p_xq": semester_info["p_xq"],
        "p_xnxq": semester_info["p_xnxq"],
        "p_xkfsdm": section.course_type,
        "p_id": section.section_id,
        "p_sfxsgwckb": 1,
    }

    try:
        resp = requests.post(
            SELECT_URL,
            data=data,
            headers=headers,
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        msg = result.get("message", str(result))
        success = "成功" in msg
        return success, msg
    except Exception as e:
        return False, f"请求异常: {e}"


def select_schedule(
    headers: dict[str, str],
    semester_info: dict,
    schedule: list[Section],
    delay: float = 1.6,
) -> list[tuple[Section, bool, str]]:
    """依次选择一个课表方案中的所有课程。

    Parameters
    ----------
    delay : float
        每次请求间隔秒数（TIS 有频率限制，建议 >= 1.5s）

    Returns
    -------
    list[tuple[Section, bool, str]]
        每门课的 (教学班, 是否成功, 消息)
    """
    results: list[tuple[Section, bool, str]] = []

    for i, section in enumerate(schedule):
        # 硬编码课程没有真实 section_id，跳过
        if not section.section_id or section.section_id.startswith("CS104"):
            print(f"  [!] {section.course_name} 为手动硬编码课程，需在 TIS 页面手动选课")
            results.append((section, False, "硬编码课程，需手动选课"))
            continue

        print(f"  [{i+1}/{len(schedule)}] 选课: {section.course_name} ({section.section_name})...", end=" ", flush=True)
        success, msg = select_course(headers, semester_info, section)

        if success:
            print(f"\033[32m成功\033[0m - {msg}")
        else:
            print(f"\033[31m失败\033[0m - {msg}")

        results.append((section, success, msg))

        if i < len(schedule) - 1:
            time.sleep(delay)

    return results
