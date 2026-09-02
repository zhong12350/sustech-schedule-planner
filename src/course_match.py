"""课程名匹配：规范化 TIS 名称并与用户输入做相似度匹配。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# 去掉 "-01班-..." 或末尾 "1班" 及之后的内容
_SECTION_SUFFIX = re.compile(r"-\d+班.*$")
_TRAILING_BAN = re.compile(r"[-\s（(]*\d+班.*$")

# 末尾罗马数字 / 阿拉伯数字（含 Unicode 罗马字符）
_TRAILING_NUMERAL = re.compile(
    r"(I{1,3}V?|IV|VI{0,3}|IX|X|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|\d+)$"
)

# 默认相似度阈值：略宽松以覆盖轻微错别字，后缀不一致会直接否决
DEFAULT_MATCH_THRESHOLD = 0.72


def normalize_course_name(name: str) -> str:
    """提取课程核心名称，去掉班号、语言、地点等后缀。"""
    text = name.strip()
    text = _SECTION_SUFFIX.sub("", text)
    text = _TRAILING_BAN.sub("", text)
    text = re.sub(r"\s+", "", text)
    return text


def split_base_and_suffix(name: str) -> tuple[str, str]:
    """拆分为 (基础课名, 末尾序号)，如 电子科学创新实验II -> (电子科学创新实验, II)。"""
    norm = normalize_course_name(name)
    match = _TRAILING_NUMERAL.search(norm)
    if not match:
        return norm, ""
    return norm[: match.start()], match.group(0)


def _char_overlap_ratio(a: str, b: str) -> float:
    """字符多重集合 Jaccard 相似度，适合中文短字符串。"""
    if not a or not b:
        return 0.0
    counts_a: dict[str, int] = {}
    counts_b: dict[str, int] = {}
    for ch in a:
        counts_a[ch] = counts_a.get(ch, 0) + 1
    for ch in b:
        counts_b[ch] = counts_b.get(ch, 0) + 1

    intersection = 0
    union = 0
    chars = set(counts_a) | set(counts_b)
    for ch in chars:
        ca = counts_a.get(ch, 0)
        cb = counts_b.get(ch, 0)
        intersection += min(ca, cb)
        union += max(ca, cb)
    return intersection / union if union else 0.0


def suffix_compatible(
    q_norm: str,
    q_suffix: str,
    c_norm: str,
    c_suffix: str,
) -> bool:
    """若用户输入带序号（II / Ⅴ），候选需一致或以完整课名为前缀。"""
    if not q_suffix:
        return True
    if q_suffix == c_suffix:
        return True
    # 候选也有不同序号（II vs III）-> 拒绝
    if c_suffix:
        return False
    # 候选无末尾序号，但以完整查询名开头（如 体育Ⅴ-中文-...）
    return c_norm.startswith(q_norm)


def match_score(query: str, candidate: str) -> float:
    """综合相似度 [0, 1]。后缀不一致时返回 0。"""
    q_norm = normalize_course_name(query)
    c_norm = normalize_course_name(candidate)
    if not q_norm or not c_norm:
        return 0.0

    q_base, q_suffix = split_base_and_suffix(q_norm)
    c_base, c_suffix = split_base_and_suffix(c_norm)
    if not suffix_compatible(q_norm, q_suffix, c_norm, c_suffix):
        return 0.0

    if q_norm == c_norm:
        return 1.0

    # TIS 完整名常以用户输入的课名为前缀
    if c_norm.startswith(q_norm):
        return 0.95

    # 公共前缀之后的尾部必须相似，避免「微系统」误匹配「嵌入式系统」
    prefix_len = 0
    for qc, cc in zip(q_norm, c_norm):
        if qc == cc:
            prefix_len += 1
        else:
            break
    tail_q = q_norm[prefix_len:]
    tail_c = c_norm[prefix_len:]
    if tail_q and tail_c:
        tail_ratio = SequenceMatcher(None, tail_q, tail_c).ratio()
        if tail_ratio < 0.55:
            return 0.0

    seq_ratio = SequenceMatcher(None, q_norm, c_norm).ratio()
    char_ratio = _char_overlap_ratio(q_norm, c_norm)
    base_seq = SequenceMatcher(None, q_base, c_base).ratio() if q_base and c_base else 0.0

    return max(seq_ratio, char_ratio, base_seq)


def find_matching_course_keys(
    query: str,
    available_keys: list[str],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[tuple[str, float]]:
    """返回所有匹配到的 TIS 课程 key 及得分，按得分降序。"""
    scored: list[tuple[str, float]] = []
    for key in available_keys:
        score = match_score(query, key)
        if score >= threshold:
            scored.append((key, score))

    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def pick_best_match_group(
    query: str,
    available_keys: list[str],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> tuple[list[str], float]:
    """返回所有达标的 TIS key（同一门课的多个教学班会各自占一个 key）。"""
    scored = find_matching_course_keys(query, available_keys, threshold)
    if not scored:
        return [], 0.0

    best_keys = [key for key, _ in scored]
    best_score = scored[0][1]
    return best_keys, best_score
