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
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

TEAL = colors.HexColor("#009c9c")
NAVY = colors.HexColor("#08263a")
MUTED = colors.HexColor("#526b7a")
LINE = colors.HexColor("#d4e1e6")
FONT_NAME = "JsaChinese"


def build_resume_pdf(data: dict[str, Any]) -> bytes:
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

    story.extend([Spacer(1, 5 * mm), _section_title("AI Agent 项目实践", styles)])
    story.append(_architecture_overview(styles))
    story.append(PageBreak())

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
    for item in data["experience"][:1]:
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
    story.append(PageBreak())
    for item in data["experience"][1:]:
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


def _architecture_overview(styles: dict[str, ParagraphStyle]) -> Table:
    headings = ["业务输入", "处理与项目能力", "AI 资产", "线上应用"]
    values = [
        "商户与商品数据<br/>内容运营需求<br/>历史咨询数据",
        "知识数据加工<br/>内容生产工作流<br/>数据清洗与微调",
        "RAG 知识库<br/>LoRA 微调模型<br/>评测数据集",
        "实时语音导购 Agent<br/>内容运营系统<br/>智能问答",
    ]
    table = Table(
        [
            [Paragraph(f"<b>{value}</b>", styles["body"]) for value in headings],
            [Paragraph(value, styles["summary"]) for value in values],
        ],
        colWidths=[45 * mm] * 4,
        rowHeights=[11 * mm, 52 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef7f7")),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("VALIGN", (0, 1), (-1, 1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, 1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), TEAL),
            ]
        )
    )
    return table


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
