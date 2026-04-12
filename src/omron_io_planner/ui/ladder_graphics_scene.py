# -*- coding: utf-8 -*-
"""阶段 1：梯形图 Graphics 母线、梯级与串联图元（欧姆龙 spec_id 表驱动）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal

from ..ladder_drag_mime import SPEC_ID_MIME, SYMBOL_NAME_MIME
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QStyle,
    QStyleOptionGraphicsItem,
    QWidget,
)

from ..omron_ladder_spec import SPEC_BY_ID
from ..program_models import LadderInstructionInstance, LadderNetwork

# 布局常量（与 slot_index 相乘，与持久化槽位一致）
RAIL_X = 6.0
RAIL_WIDTH = 10.0
RUNG_HEIGHT = 52.0
SLOT_WIDTH = 84.0
TOP_MARGIN = 6.0
MIN_VISIBLE_SLOTS = 14

# 与 CXR v2 导出常用子集一致（调色板/手册对齐用；画布仍渲染任意 spec_id，未知规格灰显）
PHASE1_CANVAS_SPEC_IDS = frozenset(
    {
        "omron.ld",
        "omron.ldnot",
        "omron.out",
        "omron.set",
        "omron.rset",
        "omron.fblk",
        "omron.parallel_open",
        "omron.parallel_close",
    }
)


class InstructionBlockItem(QGraphicsRectItem):
    """单条指令的串联图元；不参与欧姆龙语义，仅展示与选中。"""

    ITEM_TYPE = QGraphicsItem.UserType + 1

    def __init__(self, rung_index: int, inst: LadderInstructionInstance) -> None:
        w = SLOT_WIDTH - 8.0
        h = RUNG_HEIGHT - 14.0
        super().__init__(0.0, 0.0, w, h)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setData(0, inst.instance_id)
        self.setData(1, rung_index)
        self.setData(2, inst.slot_index)
        self._rung_index = rung_index
        self._instance_id = inst.instance_id
        self._inst: LadderInstructionInstance | None = inst
        self._apply_label(inst)

    def type(self) -> int:  # noqa: A003
        return self.ITEM_TYPE

    def instance_id(self) -> str:
        return self._instance_id

    def rung_index(self) -> int:
        return self._rung_index

    def slot_index(self) -> int:
        return int(self.data(2) or 0)

    def set_instruction_ref(self, inst: LadderInstructionInstance) -> None:
        """与模型中同一实例绑定，便于重绘时读到最新操作数。"""
        self._inst = inst
        self._apply_label(inst)

    def _apply_label(self, inst: LadderInstructionInstance) -> None:
        spec = SPEC_BY_ID.get(inst.spec_id)
        mnem = spec.mnemonic if spec else inst.spec_id
        op0 = inst.operands[0] if inst.operands else ""
        self.setToolTip(f"{mnem}  {op0}".strip() or inst.spec_id)

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        inst = self._inst
        spec_id = inst.spec_id if inst else ""
        known = spec_id in SPEC_BY_ID
        pen = QPen(QColor("#1a3a5c" if not selected else "#c45c00"))
        if not known:
            pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(2 if selected else 1)
        painter.setPen(pen)
        fill = "#f4f7fb" if known else "#eceef2"
        if selected:
            fill = "#fff6ed" if known else "#f0e8dc"
        painter.setBrush(QBrush(QColor(fill)))
        painter.drawRoundedRect(self.rect(), 4.0, 4.0)
        painter.setPen(QPen(QColor("#244C7B" if known else "#6b7280")))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        op0 = inst.operands[0] if inst and inst.operands else ""
        spec = SPEC_BY_ID.get(spec_id)
        mnem = spec.mnemonic if spec else (spec_id[:14] + "..." if len(spec_id) > 14 else spec_id or "?")
        r = self.rect().adjusted(4, 3, -4, -3)
        painter.drawText(r, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), mnem)
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#333333" if known else "#4b5563")))
        painter.drawText(r, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom), op0[:18])


def _hx0() -> float:
    return RAIL_X + RAIL_WIDTH + 4.0


def _block_left_x(slot_index: int) -> float:
    return _hx0() + slot_index * SLOT_WIDTH


def _block_geom(slot_index: int, y0: float) -> tuple[float, float, float, float]:
    """左、上、右（不含内边）、垂直中心线 y。"""
    x_left = _block_left_x(slot_index)
    w = SLOT_WIDTH - 8.0
    y_top = y0 + 6.0
    yc = y0 + RUNG_HEIGHT * 0.5
    return x_left, y_top, x_left + w, yc


class LadderGraphicsScene(QGraphicsScene):
    """单网络、全梯级垂直排列；左母线 + 梯级间串联能流线。"""

    selection_info_changed = Signal(str, int, int)  # instance_id, rung_index, slot_index；空 id 表示无选中

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self._network: LadderNetwork | None = None
        self._blocks: dict[str, InstructionBlockItem] = {}
        self._selected_id: str | None = None
        self._pending_rung: int | None = None
        self._pending_slot: int | None = None
        self._pending_marker: QGraphicsRectItem | None = None

    def network(self) -> LadderNetwork | None:
        return self._network

    def instruction_block_count(self) -> int:
        return len(self._blocks)

    def discard_pending_slot(self) -> None:
        """取消母线预定的放置槽位（切换网络或重置视图时调用）。"""
        self._pending_rung = None
        self._pending_slot = None
        self._remove_pending_marker()

    def take_pending_slot(self) -> tuple[int, int] | None:
        """消费「母线点击」预定的槽位（供下一次放置）；若无预定则返回 None。"""
        if self._pending_rung is None or self._pending_slot is None:
            return None
        pr, ps = self._pending_rung, self._pending_slot
        self._pending_rung = None
        self._pending_slot = None
        self._remove_pending_marker()
        return pr, ps

    def _remove_pending_marker(self) -> None:
        if self._pending_marker is not None:
            self.removeItem(self._pending_marker)
            self._pending_marker = None

    def _set_pending_slot(self, rung_index: int, slot_index: int) -> None:
        self._pending_rung = rung_index
        self._pending_slot = max(0, slot_index)
        self._remove_pending_marker()
        if self._network is None or rung_index < 0 or rung_index >= len(self._network.rungs):
            return
        y0 = TOP_MARGIN + rung_index * RUNG_HEIGHT
        x_left = _block_left_x(self._pending_slot)
        rect = QRectF(x_left, y0 + 4.0, SLOT_WIDTH - 8.0, RUNG_HEIGHT - 10.0)
        self._pending_marker = QGraphicsRectItem(rect)
        self._pending_marker.setPen(QPen(QColor("#c45c00"), 2.0, Qt.PenStyle.DashLine))
        self._pending_marker.setBrush(QBrush(Qt.GlobalColor.transparent))
        self._pending_marker.setZValue(2.0)
        self.addItem(self._pending_marker)

    def _rung_index_at_scene_y(self, y: float) -> int:
        if self._network is None:
            return -1
        rel = y - TOP_MARGIN
        if rel < 0:
            return -1
        ri = int(rel // RUNG_HEIGHT)
        if ri < 0 or ri >= len(self._network.rungs):
            return -1
        return ri

    def focus_rect_for_instance(self, instance_id: str) -> QRectF | None:
        b = self._blocks.get(instance_id)
        if b is None:
            return None
        return b.sceneBoundingRect()

    def rebuild(self, network: LadderNetwork | None) -> None:
        pending_r, pending_s = self._pending_rung, self._pending_slot
        self.clear()
        self._blocks.clear()
        self._pending_marker = None
        self._selected_id = None
        self._pending_rung = pending_r
        self._pending_slot = pending_s
        self._network = network
        if network is None or not network.rungs:
            self.selection_info_changed.emit("", -1, -1)
            return

        n = len(network.rungs)
        height = TOP_MARGIN + n * RUNG_HEIGHT + 8.0
        max_slot = MIN_VISIBLE_SLOTS
        for rung in network.rungs:
            for el in rung.elements:
                max_slot = max(max_slot, el.slot_index + 2)
        width = RAIL_X + RAIL_WIDTH + max_slot * SLOT_WIDTH + 24.0

        # 左母线（连续竖线）
        rail = QGraphicsLineItem(RAIL_X + RAIL_WIDTH * 0.5, TOP_MARGIN, RAIL_X + RAIL_WIDTH * 0.5, height - 8.0)
        rail.setPen(QPen(QColor("#2d6cb5"), 3.0))
        self.addItem(rail)

        for ri, rung in enumerate(network.rungs):
            y0 = TOP_MARGIN + ri * RUNG_HEIGHT
            sep = QGraphicsLineItem(0.0, y0 + RUNG_HEIGHT, width, y0 + RUNG_HEIGHT)
            sep.setPen(QPen(QColor("#dde4ee"), 1.0))
            self.addItem(sep)
            # 梯级序号（左下角小字）
            lab = QGraphicsSimpleTextItem(str(ri))
            lab.setBrush(QBrush(QColor("#9aa7b8")))
            f = lab.font()
            f.setPointSize(7)
            lab.setFont(f)
            lab.setPos(2.0, y0 + RUNG_HEIGHT - 14.0)
            lab.setZValue(0.5)
            self.addItem(lab)

            ordered = sorted(rung.elements, key=lambda e: (e.slot_index, e.spec_id))
            yc = y0 + RUNG_HEIGHT * 0.5
            hx0 = _hx0()
            # 能流线：母线出口 → 首图元 → 相邻图元之间 → 尾端延伸
            pen_bus = QPen(QColor("#7a8aa3"), 2.0)
            pen_bus.setCapStyle(Qt.PenCapStyle.FlatCap)
            if ordered:
                xs_edges: list[tuple[float, float]] = []
                for inst in ordered:
                    xl, _yt, xr, _yc2 = _block_geom(inst.slot_index, y0)
                    xs_edges.append((xl, xr))
                x_from = hx0
                x_to_first_left = xs_edges[0][0]
                seg0 = QGraphicsLineItem(x_from, yc, x_to_first_left, yc)
                seg0.setPen(pen_bus)
                seg0.setZValue(-1.0)
                self.addItem(seg0)
                for i in range(len(xs_edges) - 1):
                    _l0, r0 = xs_edges[i]
                    l1, _r1 = xs_edges[i + 1]
                    seg = QGraphicsLineItem(r0, yc, l1, yc)
                    seg.setPen(pen_bus)
                    seg.setZValue(-1.0)
                    self.addItem(seg)
                last_r = xs_edges[-1][1]
                tail = QGraphicsLineItem(last_r, yc, min(width - 8.0, last_r + SLOT_WIDTH * 0.75), yc)
                tail.setPen(QPen(QColor("#a8b4c8"), 1.5))
                tail.setZValue(-1.0)
                self.addItem(tail)
            else:
                stub = QGraphicsLineItem(hx0, yc, hx0 + SLOT_WIDTH * 2.0, yc)
                stub.setPen(QPen(QColor("#c5cedd"), 1.0, Qt.PenStyle.DashLine))
                stub.setZValue(-1.0)
                self.addItem(stub)

            for inst in ordered:
                item = InstructionBlockItem(ri, inst)
                item.set_instruction_ref(inst)
                x = _block_left_x(inst.slot_index)
                item.setPos(x, y0 + 6.0)
                item.setZValue(0.0)
                self.addItem(item)
                self._blocks[inst.instance_id] = item

        self.setSceneRect(QRectF(0.0, 0.0, width, height))
        if self._pending_rung is not None and self._pending_slot is not None:
            self._set_pending_slot(self._pending_rung, self._pending_slot)
        self.selection_info_changed.emit("", -1, -1)

    def selected_instance_id(self) -> str | None:
        return self._selected_id

    def select_instance(self, instance_id: str | None) -> None:
        self._selected_id = instance_id or None
        for bid, item in self._blocks.items():
            item.setSelected(bid == self._selected_id)
        if self._selected_id and self._selected_id in self._blocks:
            b = self._blocks[self._selected_id]
            self.selection_info_changed.emit(b.instance_id(), b.rung_index(), b.slot_index())
        else:
            self.selection_info_changed.emit("", -1, -1)

    def item_at_scene_pos(self, pos: QPointF) -> InstructionBlockItem | None:
        for item in self.items(pos):
            if isinstance(item, InstructionBlockItem):
                return item
        return None

    def rung_slot_at_scene_pos(self, pos: QPointF) -> tuple[int, int] | None:
        """母线可编辑区内的 (梯级索引, 槽位索引)；坐标不在区内则返回 None。"""
        if self._network is None:
            return None
        ri = self._rung_index_at_scene_y(pos.y())
        if ri < 0:
            return None
        hx0 = _hx0()
        if pos.x() < hx0:
            return None
        slot = int((pos.x() - hx0) // SLOT_WIDTH)
        return ri, max(0, slot)

    def _ordered_keys(self, rung_index: int) -> list[tuple[int, str]]:
        if self._network is None or rung_index < 0 or rung_index >= len(self._network.rungs):
            return []
        rung = self._network.rungs[rung_index]
        els = list(rung.elements)
        els.sort(key=lambda e: (e.slot_index, e.spec_id))
        return [(e.slot_index, e.instance_id) for e in els]

    def move_selection_horizontal(self, delta: int) -> None:
        if not self._selected_id or self._network is None:
            return
        b = self._blocks.get(self._selected_id)
        if b is None:
            return
        ri = b.rung_index()
        keys = self._ordered_keys(ri)
        ids = [k[1] for k in keys]
        if self._selected_id not in ids:
            return
        i = ids.index(self._selected_id)
        j = max(0, min(len(ids) - 1, i + delta))
        self.select_instance(ids[j])

    def move_selection_vertical(self, delta: int) -> None:
        if not self._selected_id or self._network is None:
            return
        b = self._blocks.get(self._selected_id)
        if b is None:
            return
        ri = b.rung_index()
        slot = b.slot_index()
        nj = ri + delta
        if nj < 0 or nj >= len(self._network.rungs):
            return
        keys = self._ordered_keys(nj)
        if not keys:
            self.select_instance(None)
            return
        best = None
        best_dist = 10**9
        for s, iid in keys:
            d = abs(s - slot)
            if d < best_dist:
                best_dist = d
                best = iid
            elif d == best_dist and best is not None:
                pass
        if best:
            self.select_instance(best)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self.item_at_scene_pos(event.scenePos())
            if isinstance(hit, InstructionBlockItem):
                self._pending_rung = None
                self._pending_slot = None
                self._remove_pending_marker()
                self.select_instance(hit.instance_id())
                event.accept()
                return
            self.select_instance(None)
            pos = event.scenePos()
            ri = self._rung_index_at_scene_y(pos.y())
            hx0 = _hx0()
            if ri >= 0 and pos.x() >= hx0:
                slot = int((pos.x() - hx0) // SLOT_WIDTH)
                if slot >= 0:
                    self._set_pending_slot(ri, slot)
                    event.accept()
                    return
            self._pending_rung = None
            self._pending_slot = None
            self._remove_pending_marker()
            event.accept()
            return
        super().mousePressEvent(event)


class LadderGraphicsView(QGraphicsView):
    """接收方向键与 Delete；阶段 2：接受指令/符号拖放。"""

    navigate_horizontal = Signal(int)
    navigate_vertical = Signal(int)
    delete_selected = Signal()
    spec_id_dropped_on_canvas = Signal(int, int, str)  # rung, slot, spec_id
    symbol_dropped_on_canvas = Signal(str, str, int, int)  # symbol, target_instance_id, rung, slot

    def __init__(self, scene: LadderGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self._zoom_level = 1.0
        self.setAcceptDrops(True)
        self.setRenderHints(
            self.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameShape(QGraphicsView.Shape.StyledPanel)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)

    def reset_zoom(self) -> None:
        self._zoom_level = 1.0
        self.resetTransform()

    def _scene_ladder(self) -> LadderGraphicsScene | None:
        sc = self.scene()
        return sc if isinstance(sc, LadderGraphicsScene) else None

    @staticmethod
    def _decode_spec_id(md) -> str | None:  # QMimeData
        if md.hasFormat(SPEC_ID_MIME):
            return bytes(md.data(SPEC_ID_MIME)).decode("utf-8", errors="ignore").strip() or None
        return None

    @staticmethod
    def _decode_symbol(md) -> str | None:  # QMimeData
        if md.hasFormat(SYMBOL_NAME_MIME):
            return bytes(md.data(SYMBOL_NAME_MIME)).decode("utf-8", errors="ignore").strip() or None
        t = md.text().strip()
        if not t:
            return None
        return t.split("\n", 1)[0].strip()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        md = event.mimeData()
        if self._decode_spec_id(md) or self._decode_symbol(md):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # type: ignore[override]
        md = event.mimeData()
        if self._decode_spec_id(md) or self._decode_symbol(md):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        sc = self._scene_ladder()
        if sc is None:
            event.ignore()
            return
        md = event.mimeData()
        pos = self.mapToScene(event.position().toPoint())
        hit = sc.item_at_scene_pos(pos)
        spec_id = self._decode_spec_id(md)
        if spec_id:
            if isinstance(hit, InstructionBlockItem):
                self.spec_id_dropped_on_canvas.emit(hit.rung_index(), hit.slot_index(), spec_id)
            else:
                rs = sc.rung_slot_at_scene_pos(pos)
                if rs is not None:
                    self.spec_id_dropped_on_canvas.emit(rs[0], rs[1], spec_id)
            event.acceptProposedAction()
            return
        symbol = self._decode_symbol(md)
        if symbol:
            if isinstance(hit, InstructionBlockItem):
                self.symbol_dropped_on_canvas.emit(symbol, hit.instance_id(), hit.rung_index(), hit.slot_index())
            else:
                rs = sc.rung_slot_at_scene_pos(pos)
                if rs is not None:
                    self.symbol_dropped_on_canvas.emit(symbol, "", rs[0], rs[1])
            event.acceptProposedAction()
            return
        event.ignore()

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                super().wheelEvent(event)
                return
            factor = 1.12 if delta > 0 else 1.0 / 1.12
            self._zoom_level = max(0.35, min(3.5, self._zoom_level * factor))
            self.resetTransform()
            self.scale(self._zoom_level, self._zoom_level)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_0:
            self.reset_zoom()
            event.accept()
            return
        if key in (Qt.Key.Key_Left,):
            self.navigate_horizontal.emit(-1)
            event.accept()
            return
        if key in (Qt.Key.Key_Right,):
            self.navigate_horizontal.emit(1)
            event.accept()
            return
        if key in (Qt.Key.Key_Up,):
            self.navigate_vertical.emit(-1)
            event.accept()
            return
        if key in (Qt.Key.Key_Down,):
            self.navigate_vertical.emit(1)
            event.accept()
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected.emit()
            event.accept()
            return
        super().keyPressEvent(event)
