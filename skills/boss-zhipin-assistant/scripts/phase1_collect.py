#!/usr/bin/env python3
"""
Phase 1: 统一采集脚本

通过 WebBridge 操作 Chrome，在 BOSS直聘上搜索并提取岗位。
- 推荐页滚动采集 + 关键词搜索采集
- Vue $props.data 提取完整字段
- 薪资字体解密
- 全局唯一 SESSION（不开多标签页）

用法:
    cd <WORK_DIR>
    python phase1_collect.py [--output boss_phase1_raw.json]

输出: JSON 岗位列表
"""

import json
import time
import random
import sys
import os
from collections import Counter

# 添加 skills 目录到 path
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.webbridge_client import (
    SESSION, navigate, evaluate, scroll_page, extract_jobs,
    ensure_active_tab, health_check, clean_pid_files,
)
from scripts.config_v3 import SEARCH_KEYWORDS, USER


def collect_recommend_page(max_no_new=15, max_scrolls=40):
    """推荐页滚动采集"""
    print("Phase 1A: 推荐页滚动采集")
    print("-" * 50)

    navigate(f"https://www.zhipin.com/web/geek/recommend?city={USER['city_code']}&source=",
             wait_range=(8, 10))

    all_jobs = {}
    no_new_count = 0

    for scroll_i in range(max_scrolls):
        jobs = extract_jobs()
        new_count = 0
        for j in jobs:
            jid = j.get('jobId', '')
            if jid and jid not in all_jobs:
                all_jobs[jid] = j
                new_count += 1

        if new_count > 0:
            print(f"  滚动 {scroll_i + 1}: 新增 {new_count}, 累计 {len(all_jobs)}")
            no_new_count = 0
        else:
            no_new_count += 1
            if no_new_count % 5 == 0:
                print(f"  滚动 {scroll_i + 1}: 无新增 (连续 {no_new_count}/{max_no_new})")

        if no_new_count >= max_no_new:
            break

        scroll_page()
        time.sleep(random.uniform(2, 3.5))

    print(f"推荐页采集完成: {len(all_jobs)} 条")
    return all_jobs


def collect_search_keywords(existing_jobs, keywords=None):
    """关键词搜索采集"""
    print(f"\nPhase 1B: 关键词搜索采集 ({len(keywords or SEARCH_KEYWORDS)} 个关键词)")
    print("-" * 50)

    all_jobs = dict(existing_jobs)
    keywords = keywords or SEARCH_KEYWORDS

    for kw_idx, kw in enumerate(keywords, 1):
        kw_url = f"https://www.zhipin.com/web/geek/job?query={kw}&city={USER['city_code']}"
        print(f"[{kw_idx}/{len(keywords)}] 搜索: {kw}", end=" -> ")

        navigate(kw_url, wait_range=(4, 6))

        before = len(all_jobs)

        for scroll_i in range(3):
            jobs = extract_jobs()
            for j in jobs:
                jid = j.get('jobId', '')
                if jid and jid not in all_jobs:
                    j['search_keyword'] = kw
                    all_jobs[jid] = j

            scroll_page()
            time.sleep(random.uniform(1.5, 2.5))

        after = len(all_jobs)
        print(f"新增 {after - before}, 累计 {after}")
        time.sleep(random.uniform(1, 2))

    return all_jobs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 1: 岗位采集")
    parser.add_argument("--output", default="boss_phase1_raw.json", help="输出文件名")
    parser.add_argument("--keywords", nargs="*", help="自定义关键词（覆盖默认）")
    args = parser.parse_args()

    # 环境检查
    if not health_check():
        print("WebBridge 未运行，尝试清理 PID 并重启...")
        clean_pid_files()
        print("请手动运行: kimi-webbridge start")
        sys.exit(1)

    print(f"SESSION: {SESSION} (全局唯一)")
    print(f"城市: {USER['target_city']} ({USER['city_code']})")
    print(f"关键词数: {len(args.keywords) if args.keywords else len(SEARCH_KEYWORDS)}")
    print("=" * 60)

    # 确保有活跃标签页
    if not ensure_active_tab():
        print("无法建立 WebBridge 标签页，请检查浏览器和登录状态")
        sys.exit(1)

    # Phase 1A: 推荐页
    recommend_jobs = collect_recommend_page()

    # Phase 1B: 关键词搜索
    all_jobs = collect_search_keywords(recommend_jobs, args.keywords)

    # 保存结果
    all_list = list(all_jobs.values())
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(all_list, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Phase 1 完成!")
    print(f"总采集: {len(all_list)} 条 (去重后)")
    print(f"保存到: {args.output}")
    print(f"{'=' * 60}")

    # 行业分布统计
    industries = Counter(j.get('industry', '') for j in all_list)
    print(f"\n行业分布 (Top 15):")
    for ind, cnt in industries.most_common(15):
        print(f"  {cnt:>3}  {ind}")


if __name__ == "__main__":
    main()
