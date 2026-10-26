# -*- coding: utf-8 -*-
"""Build technical report PDF/DOCX from Markdown with embedded photos."""
from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def material_dir() -> Path:
    for d in (ROOT / "docs").iterdir():
        if d.is_dir() and (d / "边缘行者_技术报告_V1.0.md").exists():
            return d
    raise SystemExit("cannot find docs/提交材料/")


def main() -> int:
    mat = material_dir()
    md = mat / "边缘行者_技术报告_V1.0.md"
    draft_dir = mat / "archive" / "report_work" / "generated_draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    pdf = draft_dir / "边缘行者_技术报告_初稿.pdf"
    docx = draft_dir / "边缘行者_技术报告_初稿.docx"
    review = draft_dir / "报告初稿_组员审核说明.md"

    if not md.is_file():
        raise SystemExit(f"missing {md}")

    photos = mat / "photos"
    required = [
        photos / "01_正面.jpg",
        photos / "02_接线.jpg",
        photos / "03_运行_SOFT.jpg",
        photos / "04_EW_READY对照.jpg",
        mat / "archive" / "report_work" / "assets" / "extra" / "05_WiFi页.jpg",
        mat / "archive" / "report_work" / "assets" / "extra" / "06_Agent页.jpg",
        mat / "archive" / "report_work" / "assets" / "extra" / "11_NO_RADAR.jpg",
    ]
    missing = [str(p.relative_to(mat)) for p in required if not p.is_file()]
    if missing:
        print("WARN: missing photos:", ", ".join(missing))

    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise SystemExit("pandoc not found in PATH")

    resource_path = mat.as_posix()
    common = [
        pandoc,
        str(md),
        "--from",
        "markdown",
        "--resource-path",
        resource_path,
    ]

    # DOCX (Word 审核友好)
    subprocess.run(
        common + ["--to", "docx", "-o", str(docx)],
        check=True,
        cwd=str(mat),
    )
    print(f"OK docx -> {docx} ({docx.stat().st_size} bytes)")

    # PDF：优先 xelatex 中文；失败则回退默认引擎
    pdf_args = common + [
        "--to",
        "pdf",
        "-o",
        str(pdf),
        "-V",
        "geometry:margin=2.5cm",
        "--pdf-engine=xelatex",
        "-V",
        "CJKmainfont=SimSun",
    ]
    try:
        subprocess.run(pdf_args, check=True, cwd=str(mat))
    except subprocess.CalledProcessError:
        print("xelatex/SimSun failed, retry default pdf engine...")
        subprocess.run(
            common + ["--to", "pdf", "-o", str(pdf)],
            check=True,
            cwd=str(mat),
        )
    print(f"OK pdf  -> {pdf} ({pdf.stat().st_size} bytes)")

    today = date.today().isoformat()
    review.write_text(
        f"""# 技术报告 PDF 初稿 · 组员审核说明

> 生成日期：{today}  
> 命令：`python scripts/submission/build_report_pdf.py`

## 交付文件

| 文件 | 用途 |
|------|------|
| `边缘行者-技术报告-contest2026_313_bianyuanxingzhe.pdf` | **官网提交用 PDF 初稿**（含嵌入照片） |
| `archive/report_work/generated_draft/边缘行者_技术报告_初稿.docx` | Word 初稿，便于批注修改 |
| `边缘行者_技术报告_V1.0.md` | Markdown 源稿 |

## 已嵌入照片（5 张，主图 2026-09-18 更新）

| 图号 | 文件 | 位置 | 内容 |
|------|------|------|------|
| 图1 | `photos/01_正面.jpg` | §3.2.2 | 整体接线全貌 |
| 图2 | `photos/02_接线.jpg` | §3.2.2 | LD2451 ↔ ESP UART 特写 |
| 图3 | `archive/report_work/assets/extra/07_蜂鸣器模块规格.jpg` | §3.2.2 | 蜂鸣器模块（未换） |
| 图4 | `photos/03_运行_SOFT.jpg` | §3.2.4 | SOFT 黄底运行态 |
| 图5 | `archive/report_work/assets/extra/06_Agent页.jpg` | §3.2.4 | Agent 页（未换） |

## 请组员重点审核

1. 摘要与 §3.1 表述是否准确（尤其「产品形态」「创新点」）。
2. 分工与代码占比（郑/王/韦）是否与各自实际一致。
3. §3.5 表格中「待测」项：WiFi / Agent 联网 / 真机靠近 / 路测指标——定稿前是否改写或保留。
4. 照片是否清晰、是否与正文匹配；是否需要补 **橙 WARN / 红 CRIT** 屏摄。
5. 有无需要删改的敏感信息（WiFi 密码、API Key 等——当前应无）。

## 定稿后

1. 在 Word 中统一样式 → 导出 PDF 覆盖同名文件，或改 md 后重跑本脚本。  
2. 与 Demo 视频、photos 一起：`python scripts/submission/pack_submission.py`
""",
        encoding="utf-8",
    )
    print(f"OK review note -> {review}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
