# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .models import IoChannel, IoPoint, IoProject
from .omron_ladder_migration import migrate_ladder_network_to_v2
from .program_models import (
    FunctionBlock,
    LadderCell,
    LadderElement,
    LadderInstructionInstance,
    LadderNetwork,
    LadderRung,
    ProgramUnit,
    StDocument,
    VariableDecl,
)


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


def _variable_to_dict(variable: VariableDecl) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "name": variable.name,
        "data_type": variable.data_type,
        "category": variable.category,
        "comment": variable.comment,
        "initial_value": variable.initial_value,
    }
    if variable.at_address:
        d["at_address"] = variable.at_address
    if variable.retain:
        d["retain"] = True
    return d


def _element_to_dict(element: LadderElement) -> Dict[str, Any]:
    return {
        "kind": element.kind,
        "operand": element.operand,
        "params": list(element.params),
        "comment": element.comment,
    }


def _cell_to_dict(cell: LadderCell) -> Dict[str, Any]:
    return {
        "row": cell.row,
        "column": cell.column,
        "element": _element_to_dict(cell.element) if cell.element is not None else None,
    }


def _instruction_instance_to_dict(inst: LadderInstructionInstance) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": inst.instance_id,
        "spec_id": inst.spec_id,
        "operands": list(inst.operands),
        "comment": inst.comment,
        "slot": inst.slot_index,
    }
    if inst.branch_group_id:
        d["branch_group_id"] = inst.branch_group_id
    return d


def _rung_to_dict(rung: LadderRung) -> Dict[str, Any]:
    return {
        "index": rung.index,
        "label": rung.label,
        "comment": rung.comment,
        "elements": [_instruction_instance_to_dict(element) for element in rung.elements],
    }


def _network_to_dict(network: LadderNetwork) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "title": network.title,
        "rows": network.rows,
        "columns": network.columns,
        "comment": network.comment,
        "format_version": network.format_version,
    }
    if network.format_version >= 2:
        base["rungs"] = [_rung_to_dict(rung) for rung in network.rungs]
        base["cells"] = []
    else:
        base["cells"] = [_cell_to_dict(cell) for cell in network.cells]
    return base


def _program_to_dict(program: ProgramUnit) -> Dict[str, Any]:
    return {
        "uid": program.uid,
        "name": program.name,
        "implementation_language": program.implementation_language,
        "st_document": {"source": program.st_document.source},
        "ladder_networks": [_network_to_dict(network) for network in program.ladder_networks],
        "local_variables": [_variable_to_dict(variable) for variable in program.local_variables],
        "workspace_state": dict(program.workspace_state),
    }


def _function_block_to_dict(block: FunctionBlock) -> Dict[str, Any]:
    return {
        "uid": block.uid,
        "name": block.name,
        "implementation_language": block.implementation_language,
        "variables": [_variable_to_dict(variable) for variable in block.variables],
        "st_document": {"source": block.st_document.source},
        "ladder_networks": [_network_to_dict(network) for network in block.ladder_networks],
        "workspace_state": dict(block.workspace_state),
    }


def _normalize_project_workspace_state(ws: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ws)
    pw = dict(out.get("program_workspace") or {})
    sel = str(pw.get("selected_item", "") or "")
    if sel.startswith("fb:") and (
        sel.endswith(":variables") or sel.endswith(":body") or sel.endswith(":block")
    ):
        parts = sel.split(":")
        if len(parts) >= 2:
            pw["selected_item"] = f"fb:{parts[1]}:editor"
    out["program_workspace"] = pw
    return out


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
            workspace_state=_normalize_project_workspace_state(dict(d.get("workspace_state") or {})),
            project_preferences=dict(d.get("project_preferences") or {}),
            programs=[_program_from_dict(program) for program in d.get("programs", [])],
            function_blocks=[_function_block_from_dict(block) for block in d.get("function_blocks", [])],
            program_settings=dict(d.get("program_settings") or {}),
        )
    pts = [_point_from_dict(x) for x in d.get("points", [])]
    return IoProject(
        name=d.get("name", "未命名"),
        plc_prefix=d.get("plc_prefix", "PLC"),
        channels=[IoChannel(name="导入数据", zone_id="", points=pts)],
        workspace_state=_normalize_project_workspace_state(dict(d.get("workspace_state") or {})),
        project_preferences=dict(d.get("project_preferences") or {}),
        programs=[_program_from_dict(program) for program in d.get("programs", [])],
        function_blocks=[_function_block_from_dict(block) for block in d.get("function_blocks", [])],
        program_settings=dict(d.get("program_settings") or {}),
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


def _variable_from_dict(x: Dict[str, Any]) -> VariableDecl:
    return VariableDecl(
        name=str(x.get("name", "")).strip(),
        data_type=str(x.get("data_type", "BOOL")).strip() or "BOOL",
        category=str(x.get("category", "VAR")).strip() or "VAR",
        comment=str(x.get("comment", "")).strip(),
        initial_value=str(x.get("initial_value", "")).strip(),
        at_address=str(x.get("at_address", x.get("at", "")) or "").strip(),
        retain=bool(x.get("retain", False)),
    )


def _element_from_dict(x: Dict[str, Any] | None) -> LadderElement | None:
    if not isinstance(x, dict):
        return None
    return LadderElement(
        kind=str(x.get("kind", "")).strip(),
        operand=str(x.get("operand", "")).strip(),
        params=[str(item) for item in x.get("params", []) if str(item).strip()],
        comment=str(x.get("comment", "")).strip(),
    )


def _cell_from_dict(x: Dict[str, Any]) -> LadderCell:
    return LadderCell(
        row=int(x.get("row", 0) or 0),
        column=int(x.get("column", 0) or 0),
        element=_element_from_dict(x.get("element")),
    )


def _instruction_instance_from_dict(d: Dict[str, Any]) -> LadderInstructionInstance:
    raw_ops = d.get("operands", [])
    operands: list[str] = []
    if isinstance(raw_ops, list):
        operands = ["" if x is None else str(x) for x in raw_ops]
    return LadderInstructionInstance(
        instance_id=str(d.get("id", "") or "").strip(),
        spec_id=str(d.get("spec_id", "") or "").strip(),
        operands=operands,
        comment=str(d.get("comment", "") or "").strip(),
        slot_index=int(d.get("slot", 0) or 0),
        branch_group_id=str(d.get("branch_group_id", "") or "").strip(),
    )


def _rung_from_dict(d: Dict[str, Any]) -> LadderRung:
    elements_raw = d.get("elements", [])
    elements: list[LadderInstructionInstance] = []
    if isinstance(elements_raw, list):
        for item in elements_raw:
            if isinstance(item, dict):
                elements.append(_instruction_instance_from_dict(item))
    return LadderRung(
        index=int(d.get("index", 0) or 0),
        label=str(d.get("label", "") or "").strip(),
        comment=str(d.get("comment", "") or "").strip(),
        elements=elements,
    )


def _network_from_dict(x: Dict[str, Any]) -> LadderNetwork:
    format_version = int(x.get("format_version", 1) or 1)
    rungs_raw = x.get("rungs", [])
    rungs: list[LadderRung] = []
    if format_version >= 2 and isinstance(rungs_raw, list):
        for item in rungs_raw:
            if isinstance(item, dict):
                rungs.append(_rung_from_dict(item))
    network = LadderNetwork(
        title=str(x.get("title", "")).strip(),
        rows=int(x.get("rows", 6) or 6),
        columns=int(x.get("columns", 8) or 8),
        comment=str(x.get("comment", "")).strip(),
        cells=[_cell_from_dict(cell) for cell in x.get("cells", []) if isinstance(cell, dict)],
        format_version=format_version,
        rungs=rungs,
    )
    if network.format_version >= 2 and not network.rungs:
        network.rungs = [LadderRung(index=i) for i in range(max(network.rows, 1))]
    elif network.format_version < 2 and network.cells:
        migrate_ladder_network_to_v2(network)
    return network


def _program_from_dict(x: Dict[str, Any]) -> ProgramUnit:
    return ProgramUnit(
        uid=str(x.get("uid", "")).strip(),
        name=str(x.get("name", "程序")).strip() or "程序",
        implementation_language=str(x.get("implementation_language", "ladder")).strip() or "ladder",
        st_document=StDocument(source=str((x.get("st_document") or {}).get("source", ""))),
        ladder_networks=[_network_from_dict(network) for network in x.get("ladder_networks", []) if isinstance(network, dict)],
        local_variables=[_variable_from_dict(variable) for variable in x.get("local_variables", []) if isinstance(variable, dict)],
        workspace_state=dict(x.get("workspace_state") or {}),
    )


def _function_block_from_dict(x: Dict[str, Any]) -> FunctionBlock:
    return FunctionBlock(
        uid=str(x.get("uid", "")).strip(),
        name=str(x.get("name", "功能块")).strip() or "功能块",
        implementation_language=str(x.get("implementation_language", "st")).strip() or "st",
        variables=[_variable_from_dict(variable) for variable in x.get("variables", []) if isinstance(variable, dict)],
        st_document=StDocument(source=str((x.get("st_document") or {}).get("source", ""))),
        ladder_networks=[_network_from_dict(network) for network in x.get("ladder_networks", []) if isinstance(network, dict)],
        workspace_state=dict(x.get("workspace_state") or {}),
    )


def project_to_dict(project: IoProject) -> Dict[str, Any]:
    """与 :func:`save_project_json` 写入磁盘的项目结构一致（供自动保存等复用）。"""
    return {
        "name": project.name,
        "plc_prefix": project.plc_prefix,
        "channels": [_channel_to_dict(c) for c in project.channels],
        "workspace_state": project.workspace_state,
        "project_preferences": project.project_preferences,
        "programs": [_program_to_dict(program) for program in project.programs],
        "function_blocks": [_function_block_to_dict(block) for block in project.function_blocks],
        "program_settings": project.program_settings,
    }


def write_text_atomic(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = "\n",
) -> None:
    """将文本原子写入路径：先写同目录临时文件再 os.replace，避免保存中断导致半文件。

    默认 ``newline="\\n"`` 使 JSON 等在 Windows 下也使用 LF；需与
    :meth:`pathlib.Path.write_text` 完全一致（例如 CSV）时传入 ``newline=None``。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp)
    owns_fd = True
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as fp:
            owns_fd = False
            fp.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        if owns_fd:
            try:
                os.close(fd)
            except OSError:
                pass
        tmp_path.unlink(missing_ok=True)
        raise


def save_project_json(project: IoProject, path: str | Path) -> None:
    path = Path(path)
    write_text_atomic(path, json.dumps(project_to_dict(project), ensure_ascii=False, indent=2))


def load_project_json(path: str | Path) -> IoProject:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise OSError(f"无法读取项目文件：{path}") from e
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"项目文件 JSON 无效：{path}") from e
    if not isinstance(d, dict):
        raise ValueError(f"项目文件格式错误（JSON 根节点须为对象）：{path}")
    return project_from_dict(d)
