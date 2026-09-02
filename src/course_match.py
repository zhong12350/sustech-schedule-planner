"""课程名匹配：规范化 TIS 名称并与用户输入做相似度匹配。"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# 去掉 "-01班-..." 或末尾 "1班" 及之后的内容
_SECTION_SUFFIX = re.compile(r"-\d+班.*$")
_TRAILING_BAN = re.compile(r"[-\s（(]*\d+班.*$")

# 末尾罗马数字 / 阿拉伯数字（含 Unicode 罗马字符）
_TRAILING_NUMERAL = re.compile(
    r"(I{1,3}V?|IV|VI{0,3}|IX|X|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|\d+)$"
)

# 连接词：不同院系可能开设名称仅差一字（如 信号与系统 vs 信号和系统）
_CONNECTIVE_CHARS = frozenset("与和及")

# 默认相似度阈值：略宽松以覆盖轻微错别字，后缀不一致会直接否决
DEFAULT_MATCH_THRESHOLD = 0.72


@dataclass
class MatchOption:
    """一个可匹配的课程身份（可能对应多个教学班 key）。"""

    identity: str
    keys: list[str] = field(default_factory=list)
    score: float = 0.0
    section_count: int = 0
    teachers: list[str] = field(default_factory=list)


@dataclass
class CourseMatchResult:
    """单门用户输入课程的匹配结果。"""

    query: str
    status: str  # "exact" | "matched" | "ambiguous" | "not_found" | "alias"
    keys: list[str] = field(default_factory=list)
    score: float = 0.0
    options: list[MatchOption] = field(default_factory=list)
    near_misses: list[tuple[str, float]] = field(default_factory=list)
    alias_target: str = ""  # 别名表解析后的正式课名


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


def connectives_compatible(query: str, candidate: str) -> bool:
    """连接词（与/和/及）必须一致，避免不同院系同名课误匹配。"""
    q_norm = normalize_course_name(query)
    c_norm = normalize_course_name(candidate)
    if len(q_norm) != len(c_norm):
        # 长度不同但含连接词时，检查较短串中的连接词是否在较长串同位置一致
        shorter, longer = (q_norm, c_norm) if len(q_norm) <= len(c_norm) else (c_norm, q_norm)
        if any(ch in _CONNECTIVE_CHARS for ch in shorter):
            for i, ch in enumerate(shorter):
                if ch in _CONNECTIVE_CHARS and longer[i] != ch:
                    return False
        return True

    for qc, cc in zip(q_norm, c_norm):
        if qc in _CONNECTIVE_CHARS or cc in _CONNECTIVE_CHARS:
            if qc != cc:
                return False
    return True


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

    if not connectives_compatible(query, candidate):
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


def group_keys_by_identity(keys: list[str], query: str | None = None) -> dict[str, list[str]]:
    """按规范化课名将 TIS key 分组（同一门课的不同教学班）。

    若用户输入是候选名的前缀（如 体育Ⅴ -> 体育Ⅴ-中文-乒乓球...），
    归入同一组而非按子项目拆分。
    """
    groups: dict[str, list[str]] = defaultdict(list)
    q_norm = normalize_course_name(query) if query else ""
    for key in keys:
        identity = normalize_course_name(key)
        if q_norm and (identity.startswith(q_norm) or q_norm == identity):
            identity = q_norm
        groups[identity].append(key)
    return dict(groups)


def _build_options(
    groups: dict[str, list[str]],
    scored_map: dict[str, float],
    section_meta: dict[str, list] | None = None,
) -> list[MatchOption]:
    """从分组构建 MatchOption 列表，按得分降序。"""
    options: list[MatchOption] = []
    for identity, keys in groups.items():
        score = max(scored_map.get(k, 0.0) for k in keys)
        teachers: list[str] = []
        if section_meta:
            section_count = sum(len(section_meta.get(k, [])) for k in keys)
            seen_teachers: set[str] = set()
            for key in keys:
                for sec in section_meta.get(key, []):
                    teacher = getattr(sec, "teacher", "") or ""
                    if teacher and teacher not in seen_teachers:
                        seen_teachers.add(teacher)
                        teachers.append(teacher)
        else:
            section_count = len(keys)
        options.append(
            MatchOption(
                identity=identity,
                keys=keys,
                score=score,
                section_count=section_count,
                teachers=teachers[:5],
            )
        )
    options.sort(key=lambda o: (-o.score, o.identity))
    return options


def resolve_course_match(
    query: str,
    available_keys: list[str],
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    section_meta: dict[str, list] | None = None,
    chosen_identity: str | None = None,
) -> CourseMatchResult:
    """解析单门课的匹配结果，必要时标记歧义。

    Parameters
    ----------
    query : str
        用户输入的课程名
    available_keys : list[str]
        TIS 全部课程 key
    threshold : float
        相似度阈值
    section_meta : dict | None
        key -> Section 列表，用于展示教师等信息
    chosen_identity : str | None
        用户已选择的课程身份（歧义消解后）
    """
    query = query.strip()
    if not query:
        return CourseMatchResult(query=query, status="not_found")

    original_query = query
    from .aliases import apply_alias

    search_query, alias_target, alias_keys = apply_alias(query, available_keys)
    if alias_keys:
        return CourseMatchResult(
            query=original_query,
            status="alias",
            keys=alias_keys,
            score=1.0,
            alias_target=alias_target or search_query,
        )
    if alias_target:
        query = search_query

    # 精确 key 匹配
    if query in available_keys:
        result = CourseMatchResult(
            query=original_query,
            status="exact",
            keys=[query],
            score=1.0,
        )
        if alias_target:
            result.alias_target = alias_target
            result.status = "alias"
        return result

    scored = find_matching_course_keys(query, available_keys, threshold)
    if not scored:
        near = find_matching_course_keys(query, available_keys, threshold=0.5)
        return CourseMatchResult(
            query=original_query,
            status="not_found",
            near_misses=near[:5],
            alias_target=alias_target or "",
        )

    scored_map = {key: score for key, score in scored}
    groups = group_keys_by_identity([key for key, _ in scored], query=query)

    def _with_alias_meta(result: CourseMatchResult) -> CourseMatchResult:
        result.query = original_query
        if alias_target:
            result.alias_target = alias_target
        return result

    # 用户已选择
    if chosen_identity:
        if chosen_identity in groups:
            keys = groups[chosen_identity]
            return _with_alias_meta(CourseMatchResult(
                query=original_query,
                status="matched",
                keys=keys,
                score=max(scored_map[k] for k in keys),
            ))
        # 按规范化名查找
        for identity, keys in groups.items():
            if identity == chosen_identity or normalize_course_name(chosen_identity) == identity:
                return _with_alias_meta(CourseMatchResult(
                    query=original_query,
                    status="matched",
                    keys=keys,
                    score=max(scored_map[k] for k in keys),
                ))

    options = _build_options(groups, scored_map, section_meta)

    # 查询名与某一 identity 完全一致 -> 唯一匹配
    q_norm = normalize_course_name(query)
    if q_norm in groups and len(groups) == 1:
        keys = groups[q_norm]
        return _with_alias_meta(CourseMatchResult(
            query=original_query,
            status="matched",
            keys=keys,
            score=max(scored_map[k] for k in keys),
        ))

    # 只有一个候选身份
    if len(groups) == 1:
        keys = next(iter(groups.values()))
        return _with_alias_meta(CourseMatchResult(
            query=original_query,
            status="matched",
            keys=keys,
            score=options[0].score,
        ))

    # 多个候选身份 -> 歧义
    return _with_alias_meta(CourseMatchResult(
        query=original_query,
        status="ambiguous",
        options=options,
        score=options[0].score,
    ))


def pick_best_match_group(
    query: str,
    available_keys: list[str],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> tuple[list[str], float]:
    """返回所有达标的 TIS key（同一门课的多个教学班会各自占一个 key）。

    若存在多个不同课程身份且未消解，仅返回得分最高的一组（向后兼容）。
    推荐使用 resolve_course_match 获取完整歧义信息。
    """
    result = resolve_course_match(query, available_keys, threshold=threshold)
    if result.status in ("exact", "matched", "alias"):
        return result.keys, result.score
    if result.status == "ambiguous" and result.options:
        return result.options[0].keys, result.options[0].score
    return [], 0.0
