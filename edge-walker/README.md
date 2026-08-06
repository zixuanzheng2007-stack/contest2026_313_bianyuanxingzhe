# 边缘行者 · 无板开发工程（edge-walker）

板未到货阶段的主机侧工程：模拟 LD2451 数据 → 本地策略判决 → Agent 事件桥接。  
板到货后，将 `policy` / `agent` 接口迁到 openvela（`sf32lb52_devkit_lcd`），仅替换「读 UART」适配层。

## 目录

```
edge-walker/
  src/edge_walker/     # 协议、模拟器、策略、Agent 桥接
  skills/              # 可迁到板上的 Skill 草稿
  scripts/             # 演示入口
  tests/               # 单测
  docs/                # 本工程说明
```

## 环境

- Python 3.10+（Windows / Ubuntu 均可）
- 不依赖开发板、不依赖 openvela 编译

```bash
cd edge-walker
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/run_demo.py
```

## 无板能验证什么

| 模块 | 状态 |
|------|------|
| LD2451 帧编解码 / 解析 | 主机可测 |
| 过滤 + TTC + `alert_level` | 主机可测 |
| 假接近场景 → 事件 → Tool 日志 | 主机可测 |
| `approach-guard` Skill 文案 | 可先写 |
| 真 UART / WiFi / 震动 / 烧录 | **等板** |

## 与仓库文档的关系

- 产品与赛题：`../docs/`
- 换板定案：`../docs/开发板更换分析.md`
- 初期安排：`../docs/初期工作安排.md`
