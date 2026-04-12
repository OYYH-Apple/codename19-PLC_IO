# 欧姆龙梯形图：指令规格（OmronInstructionSpec）与旧版迁移规则

本文档约定**内容对齐欧姆龙**、**交互对齐西门子**时的数据契约，以及从当前 `LadderNetwork.cells`（表格模式）迁移到新编辑器模型的规则。实现时可据此落地为 Python `dataclass` / 表驱动 JSON，不必与本文同名。

---

## 1. `OmronInstructionSpec`（单条指令元数据，最小字段集）

每条记录描述**一种可在调色板出现、且可被 CX 导出管线理解**的欧姆龙侧指令。西门子风格 UI 只消费这些记录，不引入西门子指令语义。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `spec_id` | `str` | 是 | 稳定内部 ID，如 `omron.ld`、`omron.tim`。存盘、撤销、遥测用，**勿用自然语言作唯一键**。 |
| `mnemonic` | `str` | 是 | 欧姆龙助记 / 显示名（以 CX 手册为准），如 `LD`、`OUT`、`TIM`。 |
| `category` | `str` | 是 | 调色板分组：`bit_logic`、`timer_counter`、`compare`、`move`、`math`、`program_control`、`function_block` 等。 |
| `operand_slots` | `list[OperandSlot]` | 是 | 有序操作数槽定义，长度 = 指令所需操作数个数。 |
| `cx_emit` | `CxEmitKind` + 模板参数 | 是 | 导出到 CXR / 未来 CX 文本的规则（见 §3）。 |
| `allowed_in_series` | `bool` | 是 | 是否允许串联在一条梯级主干上（触点类通常为真）。 |
| `allowed_as_output` | `bool` | 是 | 是否允许作为梯级最右端输出（线圈/OUT 类）。 |
| `requires_power_flow_in` | `bool` | 是 | 是否必须有左侧能流（绝大多数为真）。 |
| `parallel_branch_role` | `enum \| null` | 否 | 若涉及并联：`open`、`close`、`none`。欧姆龙拓扑与西门子 UI 的「开分支/合分支」对应时，**语义以欧姆龙允许的结构为准**。 |
| `description_zh` | `str` | 否 | 简短中文说明（手册用语）。 |
| `help_url` | `str \| null` | 否 | 可选，链到官方 PDF/HTML 锚点。 |
| `deprecated` | `bool` | 否 | 旧机型仍导出但调色板默认隐藏。 |

### 1.1 `OperandSlot`（子结构）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `role` | `str` | 是 | `BOOL_IN`、`BOOL_OUT`、`WORD_IN`、`TIMER_NO`、`ANY` 等，供校验与补全过滤。 |
| `label_zh` | `str` | 是 | 参数在属性对话框中的标签，如「操作数」「设定值」。 |
| `required` | `bool` | 是 | 是否允许空串（未连变量）。 |
| `address_class_hint` | `str \| null` | 否 | 提示符号/地址类型：`BOOL`、`CHANNEL`、`TIMER`、`COUNTER` 等，与 `ProgramSymbolIndex` 对齐。 |

### 1.2 `CxEmitKind`（与现有导出衔接）

当前 `program_export.cxr_text_from_ladder_networks` 使用 `CELL\trow\tcol\tkind\toperand\tparams\tcomment` 行。迁移期建议：

- **短期**：新模型导出仍生成兼容的 `CELL` 行时，`kind` 填 **`spec_id`** 或 **`mnemonic`（二选一并写死）**，并在文件头增加 `FORMAT_VERSION\t2` 之类一行，便于区分解析。
- **中期**：增加 `INSTR` 行（欧姆龙语义优先，含助记与槽位），`CELL` 仅作降级或删除——以 `CxEmitter` 单点实现为准。

`OmronInstructionSpec.cx_emit` 最小可表示为：

- `kind`: `cell_compat` | `instr_line` | `block_header`
- `template`: 如 `"CELL\t{row}\t{col}\t{spec_id}\t{op0}\t{params_csv}\t{comment}"`（占位符名与实现一致即可）

**原则**：调色板与图元只引用 `spec_id`；**导出器**把 `spec_id` + 槽位值变成 CXR/CX 可接受文本。

---

## 2. 新梯形图文档模型 v1（与旧表脱钩后的骨架）

以下为逻辑结构名，便于评审；存盘 JSON 可与之一一对应。

- **`LadderDocument`**
  - `format_version: int`（≥2 表示非纯 cells 表）
  - `vendor: "omron"`
  - `networks: list[LadderNetworkV2]`

- **`LadderNetworkV2`**
  - `title`, `comment`（继承现 `LadderNetwork`）
  - `rungs: list[LadderRung]`（**替代** `rows/columns/cells` 作为主编辑结构）

- **`LadderRung`**
  - `index: int`（顺序）
  - `label: str`（可选，对应网络内显示）
  - `comment: str`
  - `elements: list[LadderInstructionInstance]`（主干串联；并联用树扩展见后续迭代）

- **`LadderInstructionInstance`**
  - `instance_id: str`（UUID）
  - `spec_id: str`（外键 → `OmronInstructionSpec`）
  - `operands: list[str]`（与 `operand_slots` 等长；空串表示未填）
  - `comment: str`
  - `layout: dict`（可选：西门子式拖放需要的 x/y 或 grid 吸附键，**不参与欧姆龙语义**）

**说明**：v1 可强制「每梯级仅一条串联主干」，并联在 v2 引入；这样迁移简单、导出易验证。

---

## 3. 旧版 `cells` → 新模型 v1 迁移规则

### 3.1 输入（当前持久化形状）

- `LadderNetwork`: `title`, `rows`, `columns`, `comment`, `cells: [{row, column, element?}]`
- `LadderElement`: `kind`, `operand`, `params[]`, `comment`

### 3.2 输出

- 一个 `LadderNetworkV2`，含 `len = rows` 的 `rungs`（若 `rows <= 0` 则至少 1 条空梯级，与默认网络行为一致）。
- 每条梯级 `rung[row]` 上，按 **`column` 升序** 排列非空 `element`，映射为 `LadderInstructionInstance` 序列。

### 3.3 `kind` → `spec_id` / 操作数映射表（首版建议）

| 旧 `kind` | 新 `spec_id`（示例） | `operands` 映射 |
|-----------|---------------------|-----------------|
| `contact_no` | `omron.ld` | `[operand]` |
| `contact_nc` | `omron.ldnot` | `[operand]` |
| `coil` | `omron.out` | `[operand]` |
| `set` | `omron.set` | `[operand]` |
| `reset` | `omron.rset` | `[operand]`（欧姆龙常用 `RSET`；若后续手册定为其它助记，只改编目不改 UI） |
| `box` | `omron.fblk_generic` 或按 `params[0]` 解析具体 FUN | `[operand] + params` 按 `OperandSlot` 拆分规则在迁移脚本中单写 |
| `branch` | **丢弃** 或 `omron.comment_only` | 若有 `comment` 可生成仅注释占位；v1 无并联时不生成支路图元 |
| `line` | **丢弃** | 纯连线在表格里无欧姆龙语义等价物 |
| 未知 / 空 `kind` | **丢弃** 并记录迁移警告日志 | — |

> **注意**：`LD` / `LD NOT` 等助记以目标 PLC 系列（CJ/CP 等）手册为准；上表 `spec_id` 为占位命名，落地时以你们选定的官方名为准，**与西门子 LAD 指令名不必一致**。

### 3.4 冲突与异常

- **同一 `(row, column)` 多条 cell**：按 `column` 再稳定排序（或取第一条），其余写入迁移报告，**不静默丢失**。
- **`element is None`**：跳过。
- **`rows`/`columns` 与 cell 坐标不一致**：以 **max(现有 rows, max_row+1)** 确定梯级数；列仅影响串联顺序，**不保留**「绝对列号」到 v1（列信息可写入 `layout` 供 UI 尽量还原位置，导出仍以串联序为准）。

### 3.5 迁移触发点

- **读盘**：`persistence._network_from_dict` 或统一 `normalize_ladder_network(raw) -> LadderNetworkV2`，若检测到无 `format_version` 或 `cells` 键则走迁移。
- **写盘**：仅写 v2；可选保留 `cells` 只读镜像 **不推荐**（与「不保留旧表格模式」一致，**不写回 cells**）。

### 3.6 验收

- 迁移前后 **`cxr_text_from_ladder_networks` 或其后继 `CxEmitter`** 对「仅含 contact/coil/set/reset」的网络生成结果**语义等价**（允许行格式差异但操作数与顺序一致）。
- 含 `branch`/`line` 的旧工程：迁移报告非空，打开编辑器后用户可见提示（实现阶段定 UI）。

---

## 4. 与 `ProgramSymbolIndex` / 补全的衔接

- 调色板与属性编辑调用 `suggestions(..., mode="ladder", ...)` 时，应传入 **`spec_id` 或 `address_class_hint`** 过滤候选，避免把 TIM 操作数补全到 BOOL 槽。
- 新建变量（`create_missing_symbol`）逻辑不变，但槽位校验失败时应报**欧姆龙语境**下的错误文案（例如「定时器号应为 …」）。

---

## 5. 分阶段实施计划（修订摘要）

以下为与产品路线对齐的**分阶段目标**、交付物与验收口径；实现顺序上阶段 1 为当前主干，后续阶段依赖前一阶段的数据流与导出收口。

### 阶段 1：欧姆龙语义图元 + Graphics 母线/梯级 + 键盘/选中

**目标**：在保留 `LadderInstructionInstance` / `rungs` 与现有 CXR v2 导出的前提下，引入 **Qt Graphics** 左母线 + 按梯级展开的水平串联视图；指令仅支持**与当前导出路径一致的最小子集**（`omron.ld` / `omron.ldnot` / `omron.out` / `omron.set` / `omron.rset`，`omron.fblk` 可作占位图元）。

**交付物**：`QGraphicsScene` + 母线/梯级槽道、表驱动图元外观、`spec_id` 绑定实例；单击选中、方向键在梯级内沿槽位移动、Delete 删除；与 `SPEC_BY_ID` 同步。

**当前落地**：`src/omron_io_planner/ui/ladder_graphics_scene.py`（`LadderGraphicsScene`、`LadderGraphicsView`、`InstructionBlockItem`）；`LadderEditorWidget` 内 **「梯形图 | 指令表」** 分栏，默认 **指令表**。画布展示当前网络**全部梯级**与**全部指令**；`SPEC_BY_ID` 未收录的 `spec_id` 以灰底虚线框占位；梯级左缘序号；串联**能流线**为母线—图元—图元—尾段折线；**单击母线空白**预定槽位（橙虚线），下一次工具条放置优先落在该槽；**Ctrl+滚轮**缩放、**Ctrl+0** 复位；选中图元自动 `ensureVisible`。**`PHASE1_CANVAS_SPEC_IDS`** 仍表示与 CXR 常用导出子集对齐的助记集合（文档/导出用），不再限制画布是否绘制某条指令。

**验收**：画布编辑结果与 JSON 往返一致；`cxr_text_from_ladder_networks` 的 v2 输出与既有测试一致。

### 阶段 2：西门子式拖放窗格 + 符号拖放；表驱动参数

**目标**：调色板按 `OmronInstructionSpec.category` 分组；拖放创建实例；操作数槽编辑与 `OperandSlot`、`ProgramSymbolIndex` 一致；导出拼装迁入单一 **`CxEmitter`**（见 §1.2），避免散落字符串。

**验收**：新增指令以**表项**为主增量；符号拖放后存盘与导出一致。

**当前落地**：`cx_emitter.py` 单模块生成 CXR 行，`program_export.cxr_text_from_ladder_networks` 委托之。`ladder_drag_mime.py` 定义拖放 MIME。`omron_ladder_spec.catalog_by_category` / `category_label_zh` 驱动调色板分组。`omron_ladder_spec.validate_instruction_placement`：按槽位从左到右排序，用 `allowed_in_series` / `allowed_as_output` 禁止非法位置（多条时仅最右可为输出类；唯一一条须二者居一）。`place_instruction_at` 与画布拖放、工具条放置共用该校验，失败时 `QMessageBox` 提示。`ui/ladder_instruction_palette.py`：`InstructionDragTree`、`SymbolDragList`。`LadderGraphicsView` 拖放信号由编辑器执行校验。顶部按钮仍保留为快捷方式。

### 阶段 3：支路/并联（欧姆龙拓扑规则）

**目标**：在**欧姆龙允许的并联结构**下扩展模型（如 `parallel_branch_role`），校验器拒绝西门子 FBD 式自由拓扑；持久化版本与迁移策略单独约定。

**验收**：合法/非法拓扑用例自动化测试 + 手册允许结构抽样。

**当前落地（首批）**：`OmronInstructionSpec.parallel_branch_role`（`open` / `close`）；目录项 `omron.parallel_open`（`↓∥`）、`omron.parallel_close`（`∥↑`），分类 `parallel_branch`。`LadderInstructionInstance.branch_group_id` 与 JSON `branch_group_id` 持久化。`omron_ladder_topology.validate_rung_parallel_topology`：按槽位顺序对开/合做 **LIFO** 配对，禁止重复打开同组、禁止错序闭合、禁止未闭合；放置前与串联位置校验一起拦截非法状态。并联标记不参与 `validate_instruction_placement` 的「最右须为输出类」规则。画布与调色板自动出现新指令。`format_version` 仍为 2（仅增可选字段）。**未做**：竖向母线分叉几何、删除后弱提示、与 CX-Programmer 逐条对齐的并联指令真名。

### 阶段 4：导出、校验、大网络性能；CX / 实机验收

**目标**：导出完整、静态校验（符号/类型/拓扑）、大图性能（视口裁剪、批量更新等）；黄金样本与 CX 文本或实机对照。

**验收**：约定样本工程：打开—编辑—保存—导出—与参考 CX 一致（有条件上载 PLC）。

**当前落地（首批）**：`ladder_static_validate.py`：`validate_ladder_network` / `validate_ladder_networks` 汇总并联拓扑（`validate_rung_parallel_topology`）、串联位规则（非并联标记按槽位的 `allowed_in_series` / `allowed_as_output`）、未知 `spec_id`、必填操作数槽；可选 `check_unknown_symbols` 对 `address_class_hint == BOOL` 且为合法标识符的操作数对照 `ProgramSymbolIndex.known_names` 给出 **warning**。`ProgramWorkspace.copy_current_ladder_export`：复制 CXR 前运行校验，存在 **error** 时弹出确认框，默认「否」取消复制。`LadderGraphicsScene` 启用 `BspTreeIndex`；`LadderGraphicsView` 启用 `SmartViewportUpdate`、`CacheBackground`、`DontSavePainterState` 以改善大图滚动/缩放。**未做**：导出文本内嵌校验报告、视口级懒加载梯级、CX 黄金文件与实机对照流程自动化。

### 跨阶段依赖（摘要）

1. 阶段 1 须先稳定 **画布 ↔ `LadderInstructionInstance`** 数据流，再展开阶段 2 拖放。  
2. 阶段 2 结束前尽量收口 **`CxEmitter`**，降低阶段 4 返工。  
3. 并联扩展以**目录表 + `validate_rung_parallel_topology`** 为准，不承诺任意西门子式 FBD 拓扑。

### 各阶段可续作汇总（续排期用）

以下为各阶段在「当前落地」之上仍可自然延伸的工作，**不表示承诺优先级**；与上文各小节「未做」及 §1～§4 契约交叉处已去重归纳。

#### 阶段 1

- **呈现**：图元外观与 CX-Programmer / 手册进一步对齐（触点、线圈、并联标记的样式与间距规范）。
- **并联视觉**（与阶段 3 衔接）：竖向母线、分叉/汇合几何，使并联在画布上可读，而不限于水平槽位 + 开/合标记。
- **交互**：多选/框选、批量删除；跨梯级或更完整的键盘导航；若梯形图编辑路径未全覆盖，可补 **撤销/重做**。
- **编辑体验**：属性区与画布选中双向同步深化；梯级标签/注释在画布侧的展示与编辑入口。
- **工程化**：大图下 **单梯级或局部差分刷新**（避免每次小改全量重建场景），为阶段 4 性能打底。

#### 阶段 2

- **导出契约（§1.2）**：中长期引入 `INSTR` 行 / `block_header` 等与 CELL 兼容策略并行的形态，由 **`CxEmitter`** 单点承载模板与版本头。
- **符号与补全（§4）**：`suggestions(..., mode="ladder")` 按 **`spec_id`、`OperandSlot.role`、`address_class_hint`** 过滤候选，避免 BOOL 槽补全到定时器等不兼容类型。
- **校验文案**：槽位/类型失败时使用 **欧姆龙语境** 提示（如定时器/计数器号格式），与通用错误句区分。
- **FUN/FB**：`omron.fblk` 的实例名与参数区从占位走向 **结构化编辑**（仍表驱动），并与导出字段一致。
- **指令增量**：新指令以 **`OMRON_INSTRUCTION_CATALOG` + OperandSlot + cx_emit** 为主增量路径，减少 UI 硬编码。

#### 阶段 3

- **文档已列未做**：竖向母线分叉几何；删除并联相关指令后的 **弱提示**（拓扑即将不合法）；与 **CX-Programmer 并联指令真名/助记** 对齐（若与当前占位不同）。
- **测试与验收**：在自动化测试中扩充 **手册允许结构** 的合法/非法矩阵（嵌套、多组、边界槽位）。
- **规则入口统一**：放置前将 `validate_instruction_placement` 与并联拓扑校验 **收敛为单一入口**（便于与阶段 4 静态校验共用规则源）。
- **迁移（§3）**：旧 `cells` 中 `branch` / `line` 的 **迁移报告** 与用户可见提示（§3.6），与 v2 `rungs` 路径衔接。

#### 阶段 4

- **文档已列未做**：导出文本内嵌校验摘要（如 `; VALIDATION:` 注释行）；**视口级懒加载梯级**；**CX 黄金样本** 与参考 CX 文本 diff 的自动化；有条件时的 **上载/在线对比** 流程说明或脚本。
- **校验覆盖面**：在 `ladder_static_validate` 上扩展定时器/计数器/字地址等与 **`address_class_hint`** 对齐的规则；权衡误报后决定是否默认开启更多 **warning**；除「复制梯形图」外增加 **独立校验入口**（工具栏、保存前提示等）。
- **导出完整性**：`cx_emitter` 对未知 spec、槽位与 v2 CELL 一致性的 **结构化报告**（供 UI 或 CI）。
- **性能**：在阶段 1 差分刷新之上，视需要增加 **视口裁剪图元**、批量几何更新、避免频繁全量 `set_network`；以真实大工程 **profiling** 后再定方案。

#### 跨阶段

- **数据契约**：`deprecated`、`help_url`（§1）在目录与调色板中的行为约定与实现。
- **ProgramSymbolIndex**：补全、拖放列表、静态校验对符号集的 **单一真源** 策略，避免规则漂移。
- **验收资产**：固定「样本工程」检查清单：打开 → 编辑 → 保存 → 导出 → 与参考 CX 对照（对应阶段 4 **验收** 的可执行化）。

---

## 6. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-04-12 | 初稿：基于仓库内 `LadderCell` / `cxr_text_from_ladder_networks` 现状整理。 |
| 2026-04-12 | 增补 §5 分阶段实施计划；阶段 1 启动：Graphics 母线/梯级与最小位逻辑图元。 |
| 2026-04-12 | 阶段 2 首批：`CxEmitter`、拖放调色板与符号列表、画布 MIME 拖放。 |
| 2026-04-12 | 放置/拖放按 `allowed_in_series` / `allowed_as_output` 校验槽位（`validate_instruction_placement`）。 |
| 2026-04-12 | 阶段 3 首批：`parallel_branch_role`、`parallel_open/close`、`branch_group_id`、LIFO 拓扑校验。 |
| 2026-04-12 | 阶段 4 首批：`ladder_static_validate`、复制梯形图前校验对话框、`LadderGraphicsScene`/`View` 性能相关标志；`tests/test_ladder_static_validate.py`。 |
| 2026-04-12 | §5 增补「各阶段可续作汇总」小节，便于续排期与评审对齐。 |
