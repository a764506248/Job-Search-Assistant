import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .resume_html import build_resume_html

TEAL = colors.HexColor("#009c9c")
NAVY = colors.HexColor("#08263a")
MUTED = colors.HexColor("#526b7a")
LINE = colors.HexColor("#d4e1e6")
FONT_NAME = "JsaChinese"


def build_resume_pdf(data: dict[str, Any]) -> bytes:
    chrome = _find_chrome()
    if chrome:
        try:
            return _build_chromium_pdf(data, chrome)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            pass
    return _build_reportlab_pdf(data)


def _build_chromium_pdf(data: dict[str, Any], chrome: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="jsa-resume-") as directory:
        html_path = Path(directory) / "resume.html"
        pdf_path = Path(directory) / "resume.pdf"
        html_path.write_text(build_resume_html(data), encoding="utf-8")
        result = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path}",
                html_path.as_uri(),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0 or not pdf_path.exists():
            raise RuntimeError(result.stderr.decode(errors="replace"))
        return pdf_path.read_bytes()


def _find_chrome() -> str | None:
    configured = os.getenv("JSA_CHROME_PATH")
    candidates = [
        configured,
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    return next((path for path in candidates if path and Path(path).is_file()), None)


def _build_reportlab_pdf(data: dict[str, Any]) -> bytes:
    _register_chinese_font()
    buffer = BytesIO()
    document = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{data['name']} - 简历",
        author="Job Search Assistant",
    )
    frame = Frame(
        document.leftMargin, document.bottomMargin, document.width, document.height, id="body"
    )
    document.addPageTemplates(PageTemplate(id="resume", frames=[frame], onPage=_page_footer))
    styles = _styles()
    story = []

    contact = " · ".join(data["contact"])
    header = Table(
        [
            [Paragraph(data["name"], styles["name"]), Paragraph(contact, styles["contact"])],
            [
                Paragraph(data["headline"], styles["headline"]),
                Paragraph(f"<b>核心技术</b><br/>{data['coreSkills']}", styles["techTop"]),
            ],
        ],
        colWidths=[76 * mm, 104 * mm],
    )
    header.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)])
    )
    story.extend([header, Spacer(1, 5 * mm), _rule(), Spacer(1, 5 * mm)])

    story.extend([_section_title("个人优势", styles)])
    story.extend(_bullets(data["strengths"], styles))

    story.extend([Spacer(1, 4 * mm), _section_title("技术栈", styles)])
    skill_rows = []
    groups = data["skillGroups"]
    for index in range(0, len(groups), 2):
        cells = []
        for title, value in groups[index : index + 2]:
            cells.append(
                Paragraph(f"<font color='#007f8e'><b>{title}：</b></font>{value}", styles["body"])
            )
        if len(cells) == 1:
            cells.append(Paragraph("", styles["body"]))
        skill_rows.append(cells)
    skill_table = Table(skill_rows, colWidths=[90 * mm, 90 * mm], hAlign="LEFT")
    skill_table.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])
    )
    story.append(skill_table)

    story.append(Spacer(1, 5 * mm))
    story.extend([_section_title("项目经历", styles)])
    for project in data["projects"]:
        story.append(
            _entry(
                project["name"],
                project["role"],
                project["period"],
                project["summary"],
                project["bullets"],
                styles,
            )
        )

    story.extend([_section_title("工作经历", styles)])
    for item in data["experience"]:
        story.append(
            _entry(
                item["role"],
                item["company"],
                item["period"],
                item["summary"],
                item["bullets"],
                styles,
            )
        )
    story.extend([Spacer(1, 2 * mm), _section_title("教育经历", styles)])
    for item in data["education"]:
        education = Table(
            [
                [
                    Paragraph(
                        f"<b>{item['school']}</b><br/>"
                        f"<font color='#007f8e'>{item['degree']}</font>",
                        styles["body"],
                    ),
                    Paragraph(item["period"], styles["period"]),
                ]
            ],
            colWidths=[145 * mm, 35 * mm],
        )
        education.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(education)

    document.build(story)
    return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    font = FONT_NAME
    return {
        "name": ParagraphStyle(
            "Name", parent=base["Normal"], fontName=font, fontSize=29, leading=34, textColor=NAVY
        ),
        "headline": ParagraphStyle(
            "Headline",
            parent=base["Normal"],
            fontName=font,
            fontSize=11,
            leading=17,
            textColor=colors.HexColor("#007f8e"),
        ),
        "contact": ParagraphStyle(
            "Contact",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            leading=14,
            textColor=MUTED,
            alignment=TA_LEFT,
        ),
        "techTop": ParagraphStyle(
            "TechTop",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            leading=14,
            textColor=NAVY,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Normal"],
            fontName=font,
            fontSize=16,
            leading=21,
            textColor=NAVY,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName=font, fontSize=9.5, leading=15, textColor=NAVY
        ),
        "summary": ParagraphStyle(
            "Summary",
            parent=base["Normal"],
            fontName=font,
            fontSize=9.2,
            leading=14.5,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName=font,
            fontSize=9.3,
            leading=15,
            leftIndent=8,
            firstLineIndent=-8,
            bulletIndent=0,
            textColor=NAVY,
            spaceAfter=3.5,
        ),
        "entryTitle": ParagraphStyle(
            "EntryTitle",
            parent=base["Normal"],
            fontName=font,
            fontSize=12.5,
            leading=17,
            textColor=NAVY,
        ),
        "period": ParagraphStyle(
            "Period",
            parent=base["Normal"],
            fontName=font,
            fontSize=7.8,
            leading=12,
            alignment=TA_RIGHT,
            textColor=MUTED,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName=font,
            fontSize=7,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
    }


def _rule() -> Table:
    table = Table([[""]], colWidths=[180 * mm], rowHeights=[0.5])
    table.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.7, LINE)]))
    return table


def _section_title(title: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [["", Paragraph(f"<b>{title}</b>", styles["section"])]], colWidths=[7 * mm, 173 * mm]
    )
    table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (0, 0), 4, TEAL),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _bullets(items: list[str], styles: dict[str, ParagraphStyle]) -> list[Paragraph]:
    return [
        Paragraph(f"<font color='#00a5a5'>●</font>&nbsp;&nbsp;{item}", styles["bullet"])
        for item in items
    ]


def _entry(
    title: str,
    role: str,
    period: str,
    summary: str,
    bullets: list[str],
    styles: dict[str, ParagraphStyle],
) -> KeepTogether:
    heading = Table(
        [
            [
                Paragraph(
                    f"<b>{title}</b>&nbsp;&nbsp;<font color='#007f8e'>{role}</font>",
                    styles["entryTitle"],
                ),
                Paragraph(period, styles["period"]),
            ]
        ],
        colWidths=[145 * mm, 35 * mm],
    )
    heading.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)])
    )
    return KeepTogether(
        [
            heading,
            Paragraph(summary, styles["summary"]),
            *_bullets(bullets, styles),
            Spacer(1, 5 * mm),
        ]
    )


def _page_footer(canvas, document) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFont(FONT_NAME, 7)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(A4[0] - 15 * mm, 7 * mm, f"第 {document.page} 页")
    canvas.restoreState()


def _register_chinese_font() -> None:
    global FONT_NAME
    candidates = [
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if path.exists():
            registerFont(TTFont(FONT_NAME, str(path), subfontIndex=0))
            return
    registerFont(UnicodeCIDFont("STSong-Light"))
    FONT_NAME = "STSong-Light"
