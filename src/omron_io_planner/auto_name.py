# -*- coding: utf-8 -*-
from __future__ import annotations

import re

from .addressing import format_cio_bit, parse_cio_bit
from .models import IoChannel, IoPoint, IoProject

_ZONE_PREFIXES = {
    "CIO": "CIO",
    "WR": "W",
    "HR": "H",
    "DM": "D",
    "EM": "E",
    "AR": "A",
    "TIM": "T",
    "CNT": "C",
}
_COMMENT_SEPARATORS_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_ADDRESS_TOKEN_RE = re.compile(r"^[A-Za-z0-9]+(?:[._][A-Za-z0-9]+)*$")


def normalize_zone_prefix(zone_id: str) -> str:
    return _ZONE_PREFIXES.get(str(zone_id or "").strip().upper(), "IO")


def normalize_comment_fragment(comment: str) -> str:
    text = _COMMENT_SEPARATORS_RE.sub("_", str(comment or "").strip())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "待注释"


def normalize_address_fragment(zone_id: str, address: str) -> str:
    candidate = _strip_address_zone_prefix(zone_id, address)
    candidate = re.sub(r"\s+", "", candidate)
    if not candidate:
        return "待分配"
    parsed = parse_cio_bit(candidate)
    if parsed is not None:
        return format_cio_bit(*parsed)
    if _ADDRESS_TOKEN_RE.fullmatch(candidate) and any(ch.isdigit() for ch in candidate):
        return candidate
    return "待分配"


def build_auto_name(zone_id: str, address: str, comment: str) -> str:
    return "_".join(
        (
            normalize_zone_prefix(zone_id),
            normalize_address_fragment(zone_id, address),
            normalize_comment_fragment(comment),
        )
    )


def normalize_point_auto_name(point: IoPoint, zone_id: str) -> bool:
    expected = ""
    if point.address.strip() or point.comment.strip():
        expected = build_auto_name(zone_id, point.address, point.comment)
    if point.name == expected:
        return False
    point.name = expected
    return True


def normalize_channel_auto_names(channel: IoChannel) -> int:
    return sum(1 for point in channel.points if normalize_point_auto_name(point, channel.zone_id))


def normalize_project_auto_names(project: IoProject) -> int:
    return sum(normalize_channel_auto_names(channel) for channel in project.channels)


def _strip_address_zone_prefix(zone_id: str, address: str) -> str:
    text = str(address or "").strip()
    if not text:
        return ""
    upper_text = text.upper()
    aliases = _zone_prefix_aliases(zone_id)
    for alias in aliases:
        if upper_text.startswith(alias):
            remainder = text[len(alias):].strip()
            return remainder.lstrip("_").strip()
    return text


def _zone_prefix_aliases(zone_id: str) -> list[str]:
    zone_key = str(zone_id or "").strip().upper()
    aliases = [zone_key] if zone_key else []
    short = _ZONE_PREFIXES.get(zone_key)
    if short and short not in aliases:
        aliases.append(short)
    return sorted((alias for alias in aliases if alias), key=len, reverse=True)
