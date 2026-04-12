# 欧姆龙 IO 分配助手

**IO/符号表风格编辑**（列：**名称、数据类型、地址/值、注释**，可选 **机架位置、使用**），与 CX-Programmer 常见表格列对齐。**数据类型**下拉选项来自对欧姆龙官方《CX-Programmer Operation Manual》**(W446)** 的公开归纳；完整定义以官网手册为准：  
[https://files.omron.eu/downloads/latest/manual/en/w446_cx-programmer_operation_manual_en.pdf](https://files.omron.eu/downloads/latest/manual/en/w446_cx-programmer_operation_manual_en.pdf)  
类型列表见 `src/omron_io_planner/omron_symbol_types.py`（含对第三方对手册条目的整理链接）。

## 环境

- Python 3.10+
- 依赖见 `pyproject.toml`（PySide6、openpyxl）

## 安装与运行

```bash
cd codename19_plc_io
pip install -e .
python -m omron_io_planner.app
```

也可使用入口脚本（安装后）：`omron-io-planner`

## 功能概要

- **多通道选项卡**：每个通道单独一张表编辑 IO；可「添加通道」、在选项卡上**双击**重命名、删除当前通道（至少保留一个）。
- **全通道预览**：第一个选项卡中勾选要拼接的通道，下方表格按**列表自上而下顺序**拼接（可拖拽列表项调整顺序）；支持全选/全不选/刷新。
- **复制**：在预览选项卡上，IO/符号/D/CIO 复制内容遵循当前勾选与列表顺序；在某一通道选项卡上则仅复制该通道；「合并多段」仍为**全部通道**按项目内顺序合并。
- **表格列**：名称、数据类型（下拉，可手输未列出的类型）、地址/值、注释、机架位置、使用。
- **从 Excel 导入**：默认**单通道**；支持欧姆龙风格表头（名称/数据类型/地址/注释等）或旧版 IN/OUT 多块表；无表头时按固定六列顺序解析。
- **导出**：JSON（含 `channels` 数组）、Excel、CSV（合并表）

## 开发说明

- 源码：`src/omron_io_planner/`
- 测试：`pytest tests`（建议 `PYTHONPATH=src`）

## 版本

0.4.3 — 新增应用图标并更新 Windows 桌面发行包