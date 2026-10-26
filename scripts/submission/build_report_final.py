# -*- coding: utf-8 -*-
"""Build the final technical report PDF/DOCX from the maintained Markdown."""
from __future__ import annotations

import shutil
import subprocess
import sys
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
    tpl = mat / "archive" / "report_work" / "templates" / "report-final-header.tex"
    pdf = mat / "边缘行者-技术报告-contest2026_313_bianyuanxingzhe.pdf"
    docx = mat / "边缘行者_技术报告_定稿.docx"

    if not md.is_file():
        raise SystemExit(f"missing {md}")
    if not tpl.is_file():
        raise SystemExit(f"missing {tpl}")

    gen = ROOT / "scripts" / "submission" / "generate_report_diagrams.py"
    if gen.is_file():
        subprocess.run([sys.executable, str(gen)], check=True, cwd=str(ROOT))

    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise SystemExit("pandoc not found in PATH")

    resource_path = mat.as_posix()
    base = [
        pandoc,
        str(md),
        "--from",
        "markdown+yaml_metadata_block",
        "--resource-path",
        resource_path,
        "--toc",
        "-V",
        "toc-title=目录",
    ]

    # DOCX：目录 + 节编号
    subprocess.run(
        base + ["--to", "docx", "-o", str(docx)],
        check=True,
        cwd=str(mat),
    )
    print(f"OK docx -> {docx} ({docx.stat().st_size} bytes)")

    pdf_args = base + [
        "--to",
        "pdf",
        "-o",
        str(pdf),
        "--pdf-engine=xelatex",
        "-V",
        "documentclass=ctexart",
        "-V",
        "papersize=a4",
        "-V",
        "CJKmainfont=SimSun",
        "-V",
        "geometry:top=2.54cm,bottom=2.54cm,left=3.17cm,right=2.54cm",
        "-V",
        "fontsize=12pt",
        "--include-in-header",
        str(tpl),
    ]
    try:
        subprocess.run(pdf_args, check=True, cwd=str(mat))
    except subprocess.CalledProcessError as e:
        print("xelatex failed:", e)
        return 1

    print(f"OK pdf  -> {pdf} ({pdf.stat().st_size} bytes)")
    print("定稿完成：A4、封面、目录、页眉页脚。章节编号由源稿统一维护。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
