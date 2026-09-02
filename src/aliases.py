"""南科大课名别名知识库：简称 -> TIS 正式课名。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .course_match import normalize_course_name

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALIASES_PATH = PROJECT_ROOT / "tis_course_aliases.yaml"
DEFAULT_CATALOG_DIR = PROJECT_ROOT / "data" / "catalogs"
MATCH_MISS_LOG = PROJECT_ROOT / "data" / "match_misses.log"

_aliases_cache: dict[str, str] | None = None
_aliases_mtime: float | None = None


@dataclass
class AliasTable:
    """别名表及元数据。"""

    aliases: dict[str, str] = field(default_factory=dict)
    path: Path = DEFAULT_ALIASES_PATH
    semester: str = ""
    notes: str = ""


def _normalize_alias_key(key: str) -> str:
    return re.sub(r"\s+", "", key.strip())


def load_aliases(path: Path | None = None, *, reload: bool = False) -> AliasTable:
    """加载 tis_course_aliases.yaml。"""
    global _aliases_cache, _aliases_mtime

    aliases_path = path or DEFAULT_ALIASES_PATH
    if not aliases_path.exists():
        return AliasTable(path=aliases_path)

    mtime = aliases_path.stat().st_mtime
    if not reload and _aliases_cache is not None and _aliases_mtime == mtime:
        return AliasTable(
            aliases=dict(_aliases_cache),
            path=aliases_path,
        )

    with open(aliases_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    mapping = raw.get("aliases") or {}
    normalized: dict[str, str] = {}
    for key, target in mapping.items():
        if not key or not target:
            continue
        normalized[_normalize_alias_key(str(key))] = str(target).strip()

    _aliases_cache = normalized
    _aliases_mtime = mtime
    return AliasTable(
        aliases=normalized,
        path=aliases_path,
        semester=str(raw.get("semester") or ""),
        notes=str(raw.get("notes") or ""),
    )


def lookup_alias(query: str, path: Path | None = None) -> str | None:
    """查别名表，命中则返回 TIS 正式课名/身份名。"""
    table = load_aliases(path)
    if not table.aliases:
        return None
    key = _normalize_alias_key(query)
    return table.aliases.get(key)


def keys_for_identity(identity: str, available_keys: list[str]) -> list[str]:
    """返回与别名目标身份一致的全部 TIS key。"""
    target_norm = normalize_course_name(identity)
    if not target_norm:
        return []

    matched: list[str] = []
    for key in available_keys:
        key_norm = normalize_course_name(key)
        if key_norm == target_norm or key_norm.startswith(target_norm):
            matched.append(key)
    return matched


def apply_alias(
    query: str,
    available_keys: list[str],
    *,
    path: Path | None = None,
) -> tuple[str, str | None, list[str]]:
    """应用别名，返回 (有效查询, 别名目标, 直接命中的 keys)。

    若别名能唯一映射到 TIS keys，keys 非空，可直接选用。
    """
    target = lookup_alias(query, path)
    if not target:
        return query, None, []

    keys = keys_for_identity(target, available_keys)
    if keys:
        return target, target, keys

    # 本学期 catalog 中尚无该课，仍用正式名走模糊匹配
    return target, target, []


def log_match_miss(
    query: str,
    near_misses: list[tuple[str, float]] | None = None,
    *,
    semester: str = "",
) -> None:
    """记录匹配失败，便于学期末补充 aliases。"""
    MATCH_MISS_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"{ts}\t{semester}\t{query}"
    if near_misses:
        hints = "; ".join(f"{name} ({score:.0%})" for name, score in near_misses[:3])
        line += f"\t近候选: {hints}"
    with open(MATCH_MISS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def build_catalog_from_keys(
    all_courses: dict[str, list],
    *,
    semester_label: str = "",
) -> dict:
    """从 TIS 全量目录构建课名索引（按 identity 分组）。"""
    from .course_match import group_keys_by_identity

    identities: dict[str, dict] = {}
    groups = group_keys_by_identity(list(all_courses.keys()))
    for identity, keys in sorted(groups.items()):
        section_count = sum(len(all_courses.get(k, [])) for k in keys)
        sample_keys = keys[:3]
        identities[identity] = {
            "section_count": section_count,
            "sample_keys": sample_keys,
        }

    return {
        "semester": semester_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "course_count": len(identities),
        "section_key_count": len(all_courses),
        "identities": identities,
    }


def save_catalog(catalog: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            catalog,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )


def catalog_path_for_semester(semester_info: dict) -> Path:
    xn = semester_info.get("p_xn", "unknown")
    xq = semester_info.get("p_xq", "?")
    return DEFAULT_CATALOG_DIR / f"{xn}-{xq}.yaml"
