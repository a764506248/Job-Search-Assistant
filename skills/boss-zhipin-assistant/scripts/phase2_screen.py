#!/usr/bin/env python3
"""
Phase 2: 统一机械筛选

纯机械条件过滤，不做任何语义判断：
- 薪资 >= 7K
- 城市匹配用户配置
- 猎头/保险/房产公司排除
- 标题硬排除词过滤
- 标题须含目标关键词

用法:
    cd <WORK_DIR>
    python phase2_screen.py boss_phase1_raw.json [--output boss_phase2_passed.json]

输出: JSON 通过筛选的岗位列表
"""

import json
import re
import sys
import os
from collections import Counter

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.webbridge_client import parse_salary_max
from scripts.config_v3 import (
    USER, CITY, SALARY_MIN, C_EXCLUDE, T_EXCLUDE,
    EXCLUDE_SALARY_PATTERNS,
)

# 目标标题关键词（满足任一即可通过机械筛选）
TARGET_TITLE_KW = [
    # 文旅类
    '文旅', '旅游', '景区', '研学', '旅行', '计调', '度假', '文创',
    # 住宿类
    '酒店', '民宿', '住宿', '前厅', '客房', '管家', '宾馆', '度假村',
    # 场馆类
    '场馆', '空间', '书店', '茶馆', '茶室', '营地', '展览',
    '美术馆', '博物馆', '画廊', '剧院', '剧场', '展厅',
    # 活动类
    '活动策划', '活动执行', '会展', '展会', '会务',
    # OTA类
    'OTA', '飞猪', '携程', '在线旅游',
    # 运营管理类
    '运营经理', '运营主管', '运营总监', '运营管理',
    '店长', '主理人', '项目经理',
    # HR类
    '招聘', 'HR', 'HRBP', '人事', '人力资源',
]


def screen_job(job):
    """筛选单条岗位，返回 (passed, reject_reason)"""
    title = job.get('title', '')
    company = job.get('company', '')
    industry = job.get('industry', '')
    salary = job.get('salary', '')
    city = job.get('city', '')

    # 1. 薪资 >= 7K
    sal_max = parse_salary_max(salary)
    if sal_max < SALARY_MIN:
        return False, f"薪资{salary}<{SALARY_MIN}K"

    # 2. 非月薪排除
    for pattern in EXCLUDE_SALARY_PATTERNS:
        if pattern in salary:
            return False, f"非月薪({pattern})"

    # 3. 城市匹配
    if city and CITY not in city:
        return False, f"城市{city}非{CITY}"

    # 4. 猎头公司排除
    if any(kw in company for kw in C_EXCLUDE):
        return False, f"黑名单公司({company})"

    # 5. 标题硬排除词
    matched_exclude = [kw for kw in T_EXCLUDE if kw in title]
    if matched_exclude:
        return False, f"排除标题({','.join(matched_exclude[:3])})"

    # 6. 标题须含目标关键词
    if not any(kw in title for kw in TARGET_TITLE_KW):
        return False, "标题无目标关键词"

    return True, None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 2: 机械筛选")
    parser.add_argument("input", help="Phase 1 输出的 JSON 文件")
    parser.add_argument("--output", default="boss_phase2_passed.json", help="输出文件名")
    parser.add_argument("--progress", default="stream_progress.json", help="进度文件（排除已投递）")
    args = parser.parse_args()

    # 加载 Phase 1 数据
    with open(args.input, 'r', encoding='utf-8') as f:
        jobs = json.load(f)
    print(f"Phase 1 输入: {len(jobs)} 条")

    # 加载已投递（排除已投岗位）
    done_ids = set()
    if os.path.exists(args.progress):
        with open(args.progress, 'r', encoding='utf-8') as f:
            prog = json.load(f)
            done_ids = set(j['jobId'] for j in prog.get('delivered', []) + prog.get('failed', []))
        jobs = [j for j in jobs if j.get('jobId') not in done_ids]
        print(f"排除已投递后: {len(jobs)} 条")

    # 执行筛选
    passed = []
    rejected = []

    for job in jobs:
        ok, reason = screen_job(job)
        if ok:
            passed.append(job)
        else:
            rejected.append({
                'jobId': job.get('jobId', ''),
                'title': job.get('title', ''),
                'reason': reason,
            })

    # 保存结果
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(passed, f, ensure_ascii=False, indent=2)

    reject_file = args.output.replace('.json', '_rejected.json')
    with open(reject_file, 'w', encoding='utf-8') as f:
        json.dump(rejected, f, ensure_ascii=False, indent=2)

    # 统计
    print(f"\n{'=' * 60}")
    print(f"Phase 2 机械筛选结果")
    print(f"{'=' * 60}")
    print(f"输入: {len(jobs)} 条")
    print(f"通过: {len(passed)} 条")
    print(f"拒绝: {len(rejected)} 条")

    reasons = Counter(r['reason'].split('(')[0] for r in rejected)
    print(f"\n拒绝原因统计:")
    for reason, cnt in reasons.most_common():
        print(f"  {cnt:>3}  {reason}")

    industries = Counter(j.get('industry', '') for j in passed)
    print(f"\n通过岗位行业分布:")
    for ind, cnt in industries.most_common(15):
        print(f"  {cnt:>3}  {ind}")

    print(f"\n保存通过岗位到: {args.output} ({len(passed)} 条)")
    print(f"保存拒绝记录到: {reject_file} ({len(rejected)} 条)")


if __name__ == "__main__":
    main()
