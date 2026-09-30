#!/usr/bin/env python3
"""
模块 G: 投递汇报 HTML 页生成

职责:
  读取 stream_progress.json 投递进度文件，
  生成自包含、无外部资源依赖的 HTML 汇报页。

独立可运行:
    python report_builder.py --progress stream_progress.json --output 投递汇总.html
"""

import json
import os
import sys
from datetime import datetime

def _esc(text):
    """HTML 转义"""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def build_report(progress_file="stream_progress.json", output_path="投递汇总.html"):
    """生成投递汇报 HTML 页

    参数:
        progress_file: 投递进度 JSON 文件路径
        output_path: 输出 HTML 文件路径

    返回:
        output_path (str) 或 None (失败时)
    """
    if not os.path.exists(progress_file):
        print(f"进度文件不存在: {progress_file}")
        return None

    with open(progress_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    delivered = data.get('delivered', [])
    failed = data.get('failed', [])

    total_delivered = len(delivered)
    total_failed = len(failed)

    # 按行业分组
    industry_groups = {}
    for job in delivered:
        industry = job.get('industry', '未知') or '未知'
        if industry not in industry_groups:
            industry_groups[industry] = []
        industry_groups[industry].append(job)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投递汇报 - {now}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
.container {{ max-width: 900px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #00b38a, #009688); color: #fff; padding: 30px; border-radius: 12px; text-align: center; margin-bottom: 20px; }}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header .subtitle {{ opacity: 0.9; font-size: 14px; }}
.stats {{ display: flex; gap: 16px; margin-bottom: 20px; }}
.stat-card {{ flex: 1; background: #fff; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.stat-card .num {{ font-size: 32px; font-weight: bold; color: #00b38a; }}
.stat-card .label {{ font-size: 13px; color: #888; margin-top: 4px; }}
.stat-card.fail .num {{ color: #e74c3c; }}
.section {{ background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.section h2 {{ font-size: 18px; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 2px solid #f0f0f0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ text-align: left; padding: 10px 8px; color: #888; font-weight: 500; border-bottom: 1px solid #eee; }}
td {{ padding: 10px 8px; border-bottom: 1px solid #f8f8f8; }}
tr:hover td {{ background: #fafafa; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #e8f5e9; color: #2e7d32; }}
.tag.fail {{ background: #fbe9e7; color: #c62828; }}
.empty {{ text-align: center; padding: 40px; color: #aaa; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>投递汇报</h1>
    <div class="subtitle">生成时间: {now}</div>
  </div>
  <div class="stats">
    <div class="stat-card"><div class="num">{total_delivered}</div><div class="label">成功投递</div></div>
    <div class="stat-card fail"><div class="num">{total_failed}</div><div class="label">投递失败</div></div>
    <div class="stat-card"><div class="num">{len(industry_groups)}</div><div class="label">覆盖行业</div></div>
  </div>
  <div class="section">
    <h2>投递明细</h2>
"""

    if delivered:
        html += """    <table>
      <thead><tr><th>#</th><th>岗位名称</th><th>公司</th><th>薪资</th><th>行业</th><th>结果</th></tr></thead>
      <tbody>
"""
        for i, job in enumerate(delivered, 1):
            html += (f'      <tr><td>{i}</td><td>{_esc(job.get("title",""))}</td>'
                     f'<td>{_esc(job.get("company",""))}</td>'
                     f'<td>{_esc(job.get("salary",""))}</td>'
                     f'<td>{_esc(job.get("industry",""))}</td>'
                     f'<td><span class="tag">成功</span></td></tr>\n')
        html += "    </tbody>\n  </table>\n"
    else:
        html += '    <div class="empty">暂无投递记录</div>\n'

    html += "  </div>\n"

    if failed:
        html += """  <div class="section">
    <h2>失败记录</h2>
    <table>
      <thead><tr><th>#</th><th>岗位名称</th><th>公司</th><th>失败原因</th></tr></thead>
      <tbody>
"""
        for i, job in enumerate(failed, 1):
            html += (f'      <tr><td>{i}</td><td>{_esc(job.get("title",""))}</td>'
                     f'<td>{_esc(job.get("company",""))}</td>'
                     f'<td><span class="tag fail">{_esc(job.get("reason",""))}</span></td></tr>\n')
        html += "    </tbody>\n  </table>\n  </div>\n"

    html += """</div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"投递汇报已生成: {output_path}")
    print(f"  成功投递: {total_delivered} 份")
    print(f"  投递失败: {total_failed} 份")
    print(f"  覆盖行业: {len(industry_groups)} 个")

    return output_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="投递汇报 HTML 生成")
    parser.add_argument("--progress", default="stream_progress.json", help="进度文件路径")
    parser.add_argument("--output", default="投递汇总.html", help="输出 HTML 路径")
    args = parser.parse_args()

    result = build_report(args.progress, args.output)
    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
