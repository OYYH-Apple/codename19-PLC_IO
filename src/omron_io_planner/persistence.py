# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import IoChannel, IoPoint, IoProject


def _channel_to_dict(ch: IoChannel) -> Dict[str, Any]:
    return {
        "name": ch.name,
        "zone_id": ch.zone_id,
        "points": [_point_to_dict(p) for p in ch.points],
    }


def _point_to_dict(p: IoPoint) -> Dict[str, Any]:
    return {
        "name": p.name,
        "data_type": p.data_type,
        "address": p.address,
        "comment": p.comment,
        "rack": p.rack,
        "usage": p.usage,
    }


def project_from_dict(d: Dict[str, Any]) -> IoProject:
    raw_ch = d.get("channels")
    if isinstance(raw_ch, list) and len(raw_ch) > 0:
        chs: List[IoChannel] = []
        for x in raw_ch:
            pts = [_point_from_dict(p) for p in x.get("points", [])]
            chs.append(IoChannel(
                name=str(x.get("name", "通道")),
                zone_id=str(x.get("zone_id", "")),
                points=pts,
            ))
        return IoProject(
            name=d.get("name", "未命名"),
            plc_prefix=d.get("plc_prefix", "PLC"),
            channels=chs,
            workspace_state=dict(d.get("workspace_state") or {}),
            project_preferences=dict(d.get("project_preferences") or {}),
        )
    pts = [_point_from_dict(x) for x in d.get("points", [])]
    return IoProject(
        name=d.get("name", "未命名"),
        plc_prefix=d.get("plc_prefix", "PLC"),
        channels=[IoChannel(name="导入数据", zone_id="", points=pts)],
        workspace_state=dict(d.get("workspace_state") or {}),
        project_preferences=dict(d.get("project_preferences") or {}),
    )


def _point_from_dict(x: Dict[str, Any]) -> IoPoint:
    return IoPoint(
        name=(x.get("name") or x.get("symbol_name") or "").strip(),
        data_type=str(x.get("data_type") or "BOOL"),
        address=str(x.get("address", "")).strip(),
        comment=str(x.get("comment", "")).strip(),
        rack=str(x.get("rack") or x.get("group") or "").strip(),
        usage=str(x.get("usage", "")).strip(),
    )


def save_project_json(project: IoProject, path: str | Path) -> None:
    path = Path(path)
    body = {
        "name": project.name,
        "plc_prefix": project.plc_prefix,
        "channels": [_channel_to_dict(c) for c in project.channels],
        "workspace_state": project.workspace_state,
        "project_preferences": project.project_preferences,
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project_json(path: str | Path) -> IoProject:
    path = Path(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    return project_from_dict(d)
