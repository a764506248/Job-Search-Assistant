# ruff: noqa: E501

from html import escape
from typing import Any


def build_resume_html(data: dict[str, Any]) -> str:
    strengths = "".join(f"<li>{escape(item)}</li>" for item in data["strengths"])
    skills = "".join(
        f"<div><strong>{escape(title)}：</strong>{escape(value)}</div>"
        for title, value in data["skillGroups"]
    )
    projects = "".join(_entry(item, project=True) for item in data["projects"])
    experience = data["experience"]
    education = "".join(
        f"<article class='entry'><div class='entry-head'><h3>{escape(item['school'])} "
        f"<em>{escape(item['degree'])}</em></h3><time>{escape(item['period'])}</time></div></article>"
        for item in data["education"]
    )
    architecture = "".join(
        f"<div><strong>{title}</strong><p>{content}</p></div>"
        for title, content in [
            ("业务输入", "商户与商品数据<br>内容运营需求<br>历史咨询数据"),
            ("处理与项目能力", "知识数据加工<br>内容生产工作流<br>数据清洗与微调"),
            ("AI 资产", "RAG 知识库<br>LoRA 微调模型<br>评测数据集"),
            ("线上应用", "实时语音导购 Agent<br>内容运营系统<br>智能问答"),
        ]
    )
    contact = "<br>".join(escape(item) for item in data["contact"])
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(data["name"])} - 简历</title>
<style>{PRINT_CSS}</style></head><body>
<main class="page">
  <header><div><h1>{escape(data["name"])}</h1><b>{escape(data["headline"])}</b></div>
    <p>{contact}</p><p><strong>核心技术</strong><br>{escape(data["coreSkills"])}</p></header>
  {_section("个人优势", f"<ul>{strengths}</ul>")}
  {_section("技术栈", f'<div class="skills">{skills}</div>')}
  {_section("AI Agent 项目实践", f'<div class="architecture">{architecture}</div>')}
  <span class="page-no">第 1 页</span>
</main>
<main class="page">
  {_section("项目经历", projects)}
  {_section("工作经历", _entry(experience[0]))}
  <span class="page-no">第 2 页</span>
</main>
<main class="page">
  {"".join(_entry(item) for item in experience[1:])}
  {_section("教育经历", education)}
  <span class="page-no">第 3 页</span>
</main></body></html>"""


def _section(title: str, content: str) -> str:
    return f"<section><h2><i></i>{escape(title)}</h2>{content}</section>"


def _entry(item: dict[str, Any], project: bool = False) -> str:
    title = item["name"] if project else item["role"]
    label = item["role"] if project else item["company"]
    bullets = "".join(f"<li>{escape(value)}</li>" for value in item["bullets"])
    return (
        "<article class='entry'><div class='entry-head'>"
        f"<h3>{escape(title)} <em>{escape(label)}</em></h3>"
        f"<time>{escape(item['period'])}</time></div>"
        f"<p>{escape(item['summary'])}</p><ul>{bullets}</ul></article>"
    )


PRINT_CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #eef1f2; color: #08263a; font-family: "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; }
.page { position: relative; width: 210mm; height: 297mm; margin: 0 auto 8mm; padding: 15mm 16mm 17mm; background: white; overflow: hidden; break-after: page; }
.page:last-child { break-after: auto; }
header { display: grid; grid-template-columns: 1.2fr .85fr 1.25fr; gap: 10mm; align-items: start; padding-bottom: 5mm; border-bottom: .35mm solid #cfdee4; }
h1 { margin: 0 0 2mm; font-size: 28pt; line-height: 1.15; font-weight: 700; }
header b { color: #007f8e; font-size: 10.5pt; }
header p { margin: 0; font-size: 8.5pt; line-height: 1.65; overflow-wrap: anywhere; }
section { margin-top: 5mm; }
h2 { display: flex; align-items: center; gap: 3mm; margin: 0 0 3mm; font-size: 16pt; line-height: 1.2; }
h2 i { width: 9mm; height: 1.4mm; border-radius: 2mm; background: #00a0a0; }
ul { margin: 0; padding-left: 5mm; }
li { margin-bottom: 1.5mm; padding-left: 1mm; font-size: 9.2pt; line-height: 1.55; }
li::marker { color: #00a0a0; }
.skills { display: grid; grid-template-columns: 1fr 1fr; gap: 2.4mm 8mm; font-size: 9.2pt; line-height: 1.55; }
.skills strong, h3 em { color: #007f8e; font-style: normal; }
.architecture { display: grid; grid-template-columns: repeat(4, 1fr); border: .3mm solid #cfdee4; }
.architecture > div { min-height: 52mm; border-right: .3mm solid #cfdee4; }
.architecture > div:last-child { border-right: 0; }
.architecture strong { display: block; padding: 3mm; background: #eef7f7; color: #007f8e; font-size: 9pt; }
.architecture p { margin: 0; padding: 5mm 3mm; color: #526b7a; font-size: 8.5pt; line-height: 1.8; }
.entry { margin-bottom: 6mm; break-inside: avoid; }
.entry-head { display: flex; justify-content: space-between; gap: 5mm; align-items: baseline; }
h3 { margin: 0 0 1mm; font-size: 12.5pt; line-height: 1.35; }
h3 em { margin-left: 2mm; font-size: 10.5pt; }
time { color: #526b7a; font-size: 8pt; white-space: nowrap; }
.entry > p { margin: 0 0 1.5mm; color: #526b7a; font-size: 9pt; line-height: 1.5; }
.entry li { font-size: 9.2pt; line-height: 1.52; margin-bottom: 1.3mm; }
.page-no { position: absolute; right: 16mm; bottom: 7mm; color: #758894; font-size: 7.5pt; }
@media screen { body { padding: 8mm 0; } }
@media print { html, body { background: white; } .page { margin: 0; } }
"""
