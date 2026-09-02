"""CAS 登录模块：通过南科大 CAS 认证获取 TIS 系统的会话 Cookie"""

from __future__ import annotations

import re
import os
import warnings
from getpass import getpass

import requests
from urllib3.exceptions import InsecureRequestWarning

# 抑制 SSL 不安全警告（南科大 TIS 的证书有时配置不当）
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

CAS_LOGIN_URL = "https://cas.sustech.edu.cn/cas/login?service=https%3A%2F%2Ftis.sustech.edu.cn%2Fcas"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def cas_login(student_id: str, password: str) -> dict[str, str]:
    """通过 CAS 登录并返回 TIS 所需的请求头（含 Cookie）。

    Parameters
    ----------
    student_id : str
        学号
    password : str
        CAS 密码

    Returns
    -------
    dict[str, str]
        包含 cookie 和 UA 的请求头字典，可直接用于后续 TIS 请求

    Raises
    ------
    ConnectionError
        无法连接到 CAS 服务器
    ValueError
        用户名或密码错误
    """
    # 1. GET 登录页，获取 execution token
    try:
        resp = requests.get(CAS_LOGIN_URL, headers=HEADERS, verify=False, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"无法连接到 CAS 服务器，请检查网络: {e}") from e

    # 解析 execution token
    match = re.search(r'name="execution"\s+value="([^"]+)"', resp.text)
    if not match:
        raise ConnectionError("无法从 CAS 页面解析 execution token，CAS 页面结构可能已变更")
    execution = match.group(1)

    # 2. POST 登录
    login_data = {
        "username": student_id,
        "password": password,
        "execution": execution,
        "_eventId": "submit",
        "geolocation": "",
    }
    resp = requests.post(
        CAS_LOGIN_URL,
        data=login_data,
        headers=HEADERS,
        allow_redirects=False,
        verify=False,
        timeout=15,
    )

    if resp.status_code == 500:
        raise ConnectionError("CAS 服务出错 (HTTP 500)，请稍后重试")

    if "Location" not in resp.headers:
        raise ValueError("用户名或密码错误，请检查")

    # 3. 跟随重定向到 TIS，获取 Cookie
    redirect_url = resp.headers["Location"]
    resp = requests.get(
        redirect_url,
        headers=HEADERS,
        allow_redirects=False,
        verify=False,
        timeout=15,
    )

    route_match = re.search(r"route=([^;]+)", resp.headers.get("Set-Cookie", ""))
    jsessionid_match = re.search(r"JSESSIONID=([^;]+)", resp.headers.get("Set-Cookie", ""))

    if not route_match or not jsessionid_match:
        raise ConnectionError("登录成功但无法获取 TIS Cookie，请重试")

    route = route_match.group(1)
    jsessionid = jsessionid_match.group(1)

    # 构建用于后续请求的 headers
    tis_headers = {
        **HEADERS,
        "Cookie": f"route={route}; JSESSIONID={jsessionid};",
    }
    return tis_headers


def interactive_login() -> dict[str, str]:
    """交互式登录：从环境变量或终端输入获取凭据。

    环境变量:
        SUSTECH_SID  - 学号
        SUSTECH_PWD  - CAS 密码

    Returns
    -------
    dict[str, str]
        TIS 请求头
    """
    sid = os.environ.get("SUSTECH_SID", "")
    pwd = os.environ.get("SUSTECH_PWD", "")

    if sid and pwd:
        print("[*] 从环境变量读取凭据...")
        try:
            return cas_login(sid, pwd)
        except (ConnectionError, ValueError) as e:
            print(f"[!] 环境变量凭据登录失败: {e}")
            print("[*] 切换到手动输入...")

    # 手动输入
    max_retries = 3
    for attempt in range(max_retries):
        sid = input("请输入学号: ").strip()
        pwd = getpass("请输入 CAS 密码（输入不显示）: ")
        try:
            headers = cas_login(sid, pwd)
            print("[+] 登录成功！")
            return headers
        except ValueError as e:
            print(f"[x] {e}")
            if attempt < max_retries - 1:
                print(f"[*] 请重试 ({attempt + 2}/{max_retries})...")
        except ConnectionError as e:
            print(f"[x] {e}")
            if attempt < max_retries - 1:
                print(f"[*] 请重试 ({attempt + 2}/{max_retries})...")

    raise RuntimeError("登录失败次数过多，请检查网络连接和凭据后重试")
