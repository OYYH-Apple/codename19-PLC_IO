# -*- coding: utf-8 -*-
"""阶段 4：梯形图静态校验（串联位、并联拓扑、目录与必填槽）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .omron_ladder_spec import SPEC_BY_ID
from .omron_ladder_topology import validate_rung_parallel_topology
from .program_models import LadderInstructionInstance, LadderNetwork

Severity = Literal["error", "warning"]


@dataclass
class LadderValidationIssue:
    severity: Severity
    message_zh: str
    network_title: str = ""
    rung_index: int | None = None
    slot_index: int | None = None
    spec_id: str = ""


def _series_elements(elements: list[LadderInstructionInstance]) -> list[LadderInstructionInstance]:
    """参与串联位置规则的指令（排除并联开/合标记）。"""
    out: list[LadderInstructionInstance] = []
    for inst in elements:
        spec = SPEC_BY_ID.get(inst.spec_id)
        if spec is None:
            continue
        if spec.parallel_branch_role is not None:
            continue
        out.append(inst)
    return out


def validate_rung_series_topology(elements: list[LadderInstructionInstance]) -> list[str]:
    """按槽位顺序校验非并联标记指令的 `allowed_in_series` / `allowed_as_output` 分布。"""
    series = _series_elements(elements)
    if not series:
        return []
    series.sort(key=lambda e: (e.slot_index, e.spec_id))
    n = len(series)
    errs: list[str] = []
    for i, inst in enumerate(series):
        spec = SPEC_BY_ID.get(inst.spec_id)
        if spec is None:
            continue
        mnem = spec.mnemonic
        if n == 1:
            if not (spec.allowed_in_series or spec.allowed_as_output):
                errs.append(
                    f"槽 {inst.slot_index}「{mnem}」：单独一条时须允许串联或允许作为输出端。"
                )
        elif i == n - 1:
            if not spec.allowed_as_output:
                errs.append(
                    f"槽 {inst.slot_index}「{mnem}」：串联最右端须为输出类指令。"
                )
        elif not spec.allowed_in_series:
            errs.append(
                f"槽 {inst.slot_index}「{mnem}」：触点串联区不能使用输出类指令。"
            )
    return errs


def validate_instruction_slots(inst: LadderInstructionInstance) -> list[str]:
    """必填操作数槽（`OperandSlot.required`）非空检查。"""
    spec = SPEC_BY_ID.get(inst.spec_id)
    if spec is None:
        return []
    errs: list[str] = []
    ops = list(inst.operands or [])
    for i, slot in enumerate(spec.operand_slots):
        if not slot.required:
            continue
        val = ops[i].strip() if i < len(ops) else ""
        if not val:
            errs.append(
                f"槽 {inst.slot_index} 指令「{spec.mnemonic}」：{slot.label_zh}为必填，当前为空。"
            )
    return errs


def validate_ladder_network(
    network: LadderNetwork,
    *,
    known_symbols: set[str] | None = None,
    check_unknown_symbols: bool = False,
) -> list[LadderValidationIssue]:
    """校验单个 `LadderNetwork`（含 v2 `rungs`）。"""
    title = network.title or "（未命名网络）"
    issues: list[LadderValidationIssue] = []

    if getattr(network, "format_version", 1) < 2 or not network.rungs:
        return issues

    for ri, rung in enumerate(network.rungs):
        for msg in validate_rung_parallel_topology(rung.elements):
            issues.append(
                LadderValidationIssue("error", msg, title, ri, None, ""),
            )
        for msg in validate_rung_series_topology(rung.elements):
            issues.append(
                LadderValidationIssue("error", msg, title, ri, None, ""),
            )
        for inst in rung.elements:
            if inst.spec_id not in SPEC_BY_ID:
                issues.append(
                    LadderValidationIssue(
                        "error",
                        f"未知指令规格「{inst.spec_id}」，无法对照欧姆龙目录。",
                        title,
                        ri,
                        inst.slot_index,
                        inst.spec_id,
                    )
                )
                continue
            for msg in validate_instruction_slots(inst):
                issues.append(
                    LadderValidationIssue("error", msg, title, ri, inst.slot_index, inst.spec_id),
                )
            if check_unknown_symbols and known_symbols is not None:
                spec = SPEC_BY_ID[inst.spec_id]
                known_cf = {k.casefold() for k in known_symbols}
                for i, slot in enumerate(spec.operand_slots):
                    if slot.address_class_hint != "BOOL":
                        continue
                    val = (inst.operands[i] if i < len(inst.operands) else "").strip()
                    if not val or not val.isidentifier():
                        continue
                    if val.casefold() not in known_cf:
                        issues.append(
                            LadderValidationIssue(
                                "warning",
                                f"槽 {inst.slot_index}：名称「{val}」未出现在当前符号索引中（可能为全局符号或拼写错误）。",
                                title,
                                ri,
                                inst.slot_index,
                                inst.spec_id,
                            )
                        )
    return issues


def validate_ladder_networks(
    networks: list[LadderNetwork],
    *,
    known_symbols: set[str] | None = None,
    check_unknown_symbols: bool = False,
) -> list[LadderValidationIssue]:
    out: list[LadderValidationIssue] = []
    for network in networks:
        out.extend(
            validate_ladder_network(
                network,
                known_symbols=known_symbols,
                check_unknown_symbols=check_unknown_symbols,
            )
        )
    return out


def format_issues_for_dialog(issues: list[LadderValidationIssue], *, max_lines: int = 12) -> str:
    lines: list[str] = []
    for issue in issues[:max_lines]:
        loc = ""
        if issue.rung_index is not None:
            loc = f"网络「{issue.network_title}」梯级 {issue.rung_index}"
            if issue.slot_index is not None:
                loc += f" 槽 {issue.slot_index}"
            loc += "："
        lines.append(f"[{issue.severity}] {loc}{issue.message_zh}")
    if len(issues) > max_lines:
        lines.append(f"… 另有 {len(issues) - max_lines} 条")
    return "\n".join(lines) if lines else "（无问题）"
