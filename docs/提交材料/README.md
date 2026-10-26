# 提交材料目录

本目录根层只保留最终交付物和评委复现入口；制作过程文件统一放在 [`archive/`](archive/README.md)。

## 最终交付物

- `边缘行者-技术报告-contest2026_313_bianyuanxingzhe.pdf`
- `边缘行者_技术报告_定稿.docx`
- `边缘行者-Demo-contest2026_313_bianyuanxingzhe.mp4`
- `photos/`：官网提交的 4 张自有主图

## 源稿与验收入口

- `边缘行者_技术报告_V1.0.md`：报告维护源稿
- `上交材料清单.md`：提交状态与剩余任务
- `Demo脚本与验收步骤.md`：功能演示验收
- `LD2451数据与策略复现.md`：雷达解析回归步骤

官网 zip 由 `python scripts/submission/pack_submission.py` 生成，只包含 PDF、Demo 成片和 4 张主图。
