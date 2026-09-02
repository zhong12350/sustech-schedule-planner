#!/usr/bin/env python3
"""一键启动脚本 — 无需 Git，双击或一条命令即可运行"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def ensure_deps() -> None:
    """检查并安装依赖。"""
    try:
        import flask  # noqa: F401
        import requests  # noqa: F401
        import yaml  # noqa: F401
        import rich  # noqa: F401
    except ImportError:
        print("[*] 正在安装依赖，请稍候...")
        req = PROJECT_ROOT / "requirements.txt"
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req), "-q"])
        print("[+] 依赖安装完成\n")


def main() -> None:
    ensure_deps()
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.web_app import main as web_main
    web_main()


if __name__ == "__main__":
    main()
