# -*- coding: utf-8 -*-
"""欧姆龙梯级并联拓扑校验（阶段 3）：开/合分支按槽位顺序 LIFO 配对。"""
from __future__ import annotations

from .omron_ladder_spec import SPEC_BY_ID
from .program_models import LadderInstructionInstance


def branch_group_for_topology(inst: LadderInstructionInstance) -> str:
    g = (inst.branch_group_id or "").strip()
    if g:
        return g
    if inst.operands:
        return str(inst.operands[0] or "").strip()
    return ""


def validate_rung_parallel_topology(elements: list[LadderInstructionInstance]) -> list[str]:
    """按 `slot_index` 升序检查 `parallel_branch_role` 开/合配对（栈：后进先出）。

    与西门子 FBD 自由连线无关：仅允许目录中带 `parallel_branch_role` 的指令参与配对。
    返回错误文案列表；空列表表示通过。
    """
    errors: list[str] = []
    ordered = sorted(elements, key=lambda e: (e.slot_index, e.spec_id))
    stack: list[str] = []

    for inst in ordered:
        spec = SPEC_BY_ID.get(inst.spec_id)
        if spec is None or not spec.parallel_branch_role:
            continue
        gid = branch_group_for_topology(inst)
        if not gid:
            errors.append(
                f"槽 {inst.slot_index}：指令「{spec.mnemonic}」须填写分支组名（操作数或 branch_group_id）。"
            )
            continue
        role = spec.parallel_branch_role
        if role == "open":
            if gid in stack:
                errors.append(f"槽 {inst.slot_index}：分支组「{gid}」已在未闭合的并联栈中，不能重复打开。")
            stack.append(gid)
        elif role == "close":
            if not stack:
                errors.append(f"槽 {inst.slot_index}：合分支「{gid}」没有对应的打开分支（栈空）。")
            elif stack[-1] != gid:
                errors.append(
                    f"槽 {inst.slot_index}：合分支「{gid}」须与当前最内层打开分支「{stack[-1]}」一致（欧姆龙式 LIFO 闭合）。"
                )
            else:
                stack.pop()
        else:
            errors.append(f"槽 {inst.slot_index}：未知的 parallel_branch_role「{role}」。")

    for gid in reversed(stack):
        errors.append(f"未闭合的并联分支组：「{gid}」缺少合分支指令。")

    return errors
