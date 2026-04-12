# -*- coding: utf-8 -*-
"""欧姆龙梯形图指令规格（表驱动）；交互可对齐西门子，语义以本目录为准。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class OperandSlot:
    role: str
    label_zh: str
    required: bool = True
    address_class_hint: str | None = None


@dataclass(frozen=True)
class OmronInstructionSpec:
    spec_id: str
    mnemonic: str
    category: str
    operand_slots: tuple[OperandSlot, ...]
    allowed_in_series: bool = True
    allowed_as_output: bool = False
    requires_power_flow_in: bool = True
    description_zh: str = ""
    # 并联拓扑：`open` / `close` 与 `branch_group_id`（或首操作数字串）配对，见 `omron_ladder_topology`
    parallel_branch_role: str | None = None


def _slots1(role: str, label: str, *, hint: str | None = "BOOL") -> tuple[OperandSlot, ...]:
    return (OperandSlot(role=role, label_zh=label, required=True, address_class_hint=hint),)


OMRON_INSTRUCTION_CATALOG: Final[tuple[OmronInstructionSpec, ...]] = (
    OmronInstructionSpec(
        spec_id="omron.ld",
        mnemonic="LD",
        category="bit_logic",
        operand_slots=_slots1("BOOL_IN", "操作数"),
        allowed_in_series=True,
        allowed_as_output=False,
        requires_power_flow_in=True,
        description_zh="读常开触点",
    ),
    OmronInstructionSpec(
        spec_id="omron.ldnot",
        mnemonic="LD NOT",
        category="bit_logic",
        operand_slots=_slots1("BOOL_IN", "操作数"),
        allowed_in_series=True,
        allowed_as_output=False,
        requires_power_flow_in=True,
        description_zh="读常闭触点",
    ),
    OmronInstructionSpec(
        spec_id="omron.out",
        mnemonic="OUT",
        category="bit_logic",
        operand_slots=_slots1("BOOL_OUT", "操作数"),
        allowed_in_series=False,
        allowed_as_output=True,
        requires_power_flow_in=True,
        description_zh="输出线圈",
    ),
    OmronInstructionSpec(
        spec_id="omron.set",
        mnemonic="SET",
        category="bit_logic",
        operand_slots=_slots1("BOOL_OUT", "操作数"),
        allowed_in_series=False,
        allowed_as_output=True,
        requires_power_flow_in=True,
        description_zh="置位",
    ),
    OmronInstructionSpec(
        spec_id="omron.rset",
        mnemonic="RSET",
        category="bit_logic",
        operand_slots=_slots1("BOOL_OUT", "操作数"),
        allowed_in_series=False,
        allowed_as_output=True,
        requires_power_flow_in=True,
        description_zh="复位",
    ),
    OmronInstructionSpec(
        spec_id="omron.fblk",
        mnemonic="FUN/FB",
        category="function_block",
        operand_slots=(
            OperandSlot(role="NAME", label_zh="实例/名称", required=False, address_class_hint=None),
            OperandSlot(role="ANY", label_zh="参数区", required=False, address_class_hint=None),
        ),
        allowed_in_series=True,
        allowed_as_output=False,
        requires_power_flow_in=True,
        description_zh="功能块（占位，参数以操作数+附加字串表示）",
    ),
    OmronInstructionSpec(
        spec_id="omron.parallel_open",
        mnemonic="↓∥",
        category="parallel_branch",
        operand_slots=(OperandSlot(role="ANY", label_zh="分支组", required=False, address_class_hint=None),),
        allowed_in_series=True,
        allowed_as_output=False,
        requires_power_flow_in=True,
        description_zh="并联分支起点（与「合分支」成对，按槽位顺序 LIFO 闭合）",
        parallel_branch_role="open",
    ),
    OmronInstructionSpec(
        spec_id="omron.parallel_close",
        mnemonic="∥↑",
        category="parallel_branch",
        operand_slots=(OperandSlot(role="ANY", label_zh="分支组", required=False, address_class_hint=None),),
        allowed_in_series=True,
        allowed_as_output=False,
        requires_power_flow_in=True,
        description_zh="并联分支汇合点（分支组须与对应「开分支」一致）",
        parallel_branch_role="close",
    ),
)

SPEC_BY_ID: Final[dict[str, OmronInstructionSpec]] = {s.spec_id: s for s in OMRON_INSTRUCTION_CATALOG}

_CATEGORY_LABEL_ZH: Final[dict[str, str]] = {
    "bit_logic": "位逻辑",
    "timer_counter": "定时器/计数器",
    "compare": "比较",
    "move": "传送",
    "math": "运算",
    "program_control": "程序控制",
    "function_block": "功能块",
    "parallel_branch": "并联",
}


def category_label_zh(category: str) -> str:
    return _CATEGORY_LABEL_ZH.get(category, category)


def catalog_by_category() -> dict[str, tuple[OmronInstructionSpec, ...]]:
    """按 `OmronInstructionSpec.category` 分组，组内顺序与目录声明一致。"""
    buckets: dict[str, list[OmronInstructionSpec]] = {}
    for spec in OMRON_INSTRUCTION_CATALOG:
        buckets.setdefault(spec.category, []).append(spec)
    return {k: tuple(v) for k, v in buckets.items()}


def require_spec(spec_id: str) -> OmronInstructionSpec:
    spec = SPEC_BY_ID.get(spec_id)
    if spec is None:
        raise KeyError(f"未知指令规格: {spec_id}")
    return spec


def validate_instruction_placement(
    *,
    existing_slot_specs: list[tuple[int, str]],
    target_slot: int,
    new_spec_id: str,
) -> tuple[bool, str]:
    """按槽位从左到右的串联顺序，校验 `allowed_in_series` / `allowed_as_output`。

    规则（与 `OmronInstructionSpec` 一致）：
    - 排序后仅一条：须 `allowed_in_series` 或 `allowed_as_output`；
    - 多条时最右一条须 `allowed_as_output`；其余须 `allowed_in_series`。

    `existing_slot_specs` 为当前梯级已有 ``(slot_index, spec_id)``；本函数假定在
    ``target_slot`` 处放置/替换为 ``new_spec_id``（同槽先去掉旧项再合并）。
    """
    spec = SPEC_BY_ID.get(new_spec_id)
    if spec is None:
        return False, f"未知指令规格，无法校验：{new_spec_id}"
    # 并联开/合标记不参与串联「最右必须为线圈」的几何约束（拓扑由 `validate_rung_parallel_topology` 单独校验）
    if spec.parallel_branch_role is not None:
        return True, ""

    merged = [(s, sid) for s, sid in existing_slot_specs if s != target_slot]
    merged.append((target_slot, new_spec_id))
    merged.sort(key=lambda x: (x[0], x[1]))
    # 同槽仅保留新指令（上面已去重）
    idx = max(i for i, (s, _) in enumerate(merged) if s == target_slot)
    n = len(merged)
    mnem = spec.mnemonic

    if n == 1:
        if spec.allowed_in_series or spec.allowed_as_output:
            return True, ""
        return (
            False,
            f"「{mnem}」不能单独作为一条梯级上的唯一指令（目录中未允许串联也未允许作为输出端）。",
        )
    if idx == n - 1:
        if spec.allowed_as_output:
            return True, ""
        return (
            False,
            f"「{mnem}」位于串联最右端时须为输出类指令（OUT/SET/RSET 等）。请放在更右侧空槽，或先放置触点。",
        )
    if spec.allowed_in_series:
        return True, ""
    return (
        False,
        f"「{mnem}」只能放在串联最右端（输出位），不能放在触点串联区域。",
    )
