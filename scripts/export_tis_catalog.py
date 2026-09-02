#!/usr/bin/env python3
"""从 TIS 导出本学期全校课名索引，供维护 tis_course_aliases.yaml 时查阅。

用法：
    cp config.yaml.example config.yaml   # 填入学号密码（或使用环境变量）
    python scripts/export_tis_catalog.py

输出：
    data/catalogs/{学年}-{学期}.yaml   — 按 identity 分组的全校课程索引
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import cas_login
from src.scraper import get_semester_info, fetch_all_courses
from src.aliases import build_catalog_from_keys, catalog_path_for_semester, save_catalog


def main() -> None:
    import os
    import yaml

    config_path = PROJECT_ROOT / "config.yaml"
    sid = os.environ.get("SUSTECH_SID", "")
    pwd = os.environ.get("SUSTECH_PWD", "")

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        sid = sid or str(cfg.get("student_id") or "")
        pwd = pwd or str(cfg.get("password") or "")

    if not sid or not pwd:
        print("请配置 config.yaml 或环境变量 SUSTECH_SID / SUSTECH_PWD")
        sys.exit(1)

    print("[*] 登录 TIS...")
    headers = cas_login(sid, pwd)
    semester_info = get_semester_info(headers)
    label = f"{semester_info.get('p_xn', '?')} 第{semester_info.get('p_xq', '?')}学期"
    print(f"[+] 当前学期: {label}")

    print("[*] 拉取全校课程（六种选课类型，需 1–2 分钟）...")
    all_courses = fetch_all_courses(headers, semester_info)

    catalog = build_catalog_from_keys(all_courses, semester_label=label)
    out_path = catalog_path_for_semester(semester_info)
    save_catalog(catalog, out_path)

    print(f"[+] 已导出 {catalog['course_count']} 门课 identity、"
          f"{catalog['section_key_count']} 个教学班 key")
    print(f"[+] 索引文件: {out_path}")
    print()
    print("下一步：打开索引搜索正式课名，把简称写入 tis_course_aliases.yaml")


if __name__ == "__main__":
    main()
