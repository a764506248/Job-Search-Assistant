#!/usr/bin/env python3
"""
BOSS 自动缓存清理 (v1)

策略:
  1. pipeline_state 文件 → 保留最近 5 个，其余删除
  2. 阶段中间文件 (phase1_raw/phase2_filtered/phase3_jd/phase4_approved/phase4_reviewed/phase5_result)
     → 保留每个类别最近 3 个，其余删除
  3. apply 报告 (boss_apply_*.md) → 保留最近 5 个，其余删除
  4. logs/archive/ 子目录 → 删除 3 天前的日目录
  5. boss_applied.json / scoring_config.json → 永远不动

用法:
  python3 -m scripts.cleanup                  # 默认清理（stdout输出）
  python3 -m scripts.cleanup --dry-run        # 只列出不删除
  python3 -m scripts.cleanup --quiet          # 只输出删除摘要
  python3 -m scripts.cleanup --force          # 保留更少（state只留3，phase只留1）

集成到 pipeline:
  from scripts.cleanup import run_cleanup
  run_cleanup(work_dir, quiet=True)
"""
import os, glob, time, shutil, re
from datetime import datetime, timezone, timedelta

# ── 默认保留量 ──
DEFAULT_KEEP = {
    "pipeline_state": 5,        # boss_pipeline_state_*.json
    "phase_output": 3,          # boss_phase[1-5]_*.json (每类)
    "apply_report": 5,          # boss_apply_*.md / boss_pipeline_result_*.md
    "archive_days": 3,          # logs/archive/YYYY-MM-DD 早于 N 天删除
}

FORCE_KEEP = {
    "pipeline_state": 3,
    "phase_output": 1,
    "apply_report": 3,
    "archive_days": 1,
}

PRESERVE = {"boss_applied.json", "scoring_config.json"}


def get_dirs(path: str) -> list[str]:
    """按 mtime 升序返回子目录列表"""
    dirs = []
    for d in glob.glob(os.path.join(path, "*")):
        if os.path.isdir(d):
            dirs.append(d)
    dirs.sort(key=os.path.getmtime)
    return dirs


def get_files_by_pattern(path: str, pattern: str) -> list[str]:
    """按 mtime 升序返回匹配的文件列表"""
    files = glob.glob(os.path.join(path, pattern))
    files = [f for f in files if os.path.basename(f) not in PRESERVE]
    files.sort(key=os.path.getmtime)
    return files


def purge_old_keep(files: list[str], keep: int, label: str, dry_run: bool, deleted_log: list):
    """保留最近的 N 个，删除更老的"""
    if len(files) <= keep:
        return
    to_delete = files[:len(files) - keep]
    for f in to_delete:
        basename = os.path.basename(f)
        if not dry_run:
            os.remove(f)
        deleted_log.append((label, basename))


def purge_old_dirs(dirs: list[str], max_days: float, label: str, dry_run: bool, deleted_log: list):
    """删除超过 N 天的子目录"""
    now = time.time()
    for d in dirs:
        age_days = (now - os.path.getmtime(d)) / 86400
        if age_days > max_days:
            basename = os.path.basename(d)
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
            deleted_log.append((label, f"{basename}/ ({age_days:.1f}天)"))


def run_cleanup(work_dir: str = None, dry_run: bool = False, quiet: bool = False, force: bool = False):
    """执行清理"""
    if work_dir is None:
        work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    keep = FORCE_KEEP if force else DEFAULT_KEEP
    deleted = []  # [(type, name), ...]

    # ── 1. pipeline state: boss_pipeline_state_*.json ──
    state_files = get_files_by_pattern(work_dir, "boss_pipeline_state_*.json")
    purge_old_keep(state_files, keep["pipeline_state"], "state", dry_run, deleted)

    # ── 2. 阶段中间文件 ──
    phase_patterns = [
        "boss_phase1_raw_*.json",
        "boss_phase2_filtered_*.json",
        "boss_phase3_jd_*.json",
        "boss_phase4_approved_*.json",
        "boss_phase4_reviewed_*.json",
        "boss_phase5_result_*.json",
    ]
    for pat in phase_patterns:
        files = get_files_by_pattern(work_dir, pat)
        purge_old_keep(files, keep["phase_output"], pat.replace("*", "N"), dry_run, deleted)

    # ── 3. apply 报告 ──
    report_patterns = [
        "boss_apply_*.md",
        "boss_pipeline_result_*.md",
    ]
    for pat in report_patterns:
        files = get_files_by_pattern(work_dir, pat)
        purge_old_keep(files, keep["apply_report"], pat.replace("*", "N"), dry_run, deleted)

    # ── 4. scripts/ 下的日志同样清理 ──
    scripts_dir = os.path.join(work_dir, "scripts")
    if os.path.exists(scripts_dir):
        for pat in ["boss_apply_*.md", "boss_pipeline_result_*.md"]:
            files = get_files_by_pattern(scripts_dir, pat)
            purge_old_keep(files, keep["apply_report"], f"scripts/{pat.replace('*','N')}", dry_run, deleted)

    # ── 5. logs/archive/ 日目录 ──
    for archive_base in ["logs/archive", "scripts/logs/archive"]:
        archive_path = os.path.join(work_dir, archive_base)
        if os.path.exists(archive_path):
            dirs = get_dirs(archive_path)
            purge_old_dirs(dirs, keep["archive_days"], f"{archive_base}/YYYY-MM-DD", dry_run, deleted)

    # ── 6. logs/ 下老文件 ──
    logs_base = os.path.join(work_dir, "logs")
    if os.path.exists(logs_base):
        for pat in ["boss_apply_*.md", "boss_pipeline_result_*.md", "boss_phase?_*.json", "boss_pipeline_state_*.json"]:
            files = get_files_by_pattern(logs_base, pat)
            files = [f for f in files if os.path.isfile(f)]
            files.sort(key=os.path.getmtime)
            purge_old_keep(files, keep["phase_output"], f"logs/{pat.replace('*','N')}", dry_run, deleted)

    # ── 输出 ──
    if not dry_run and not quiet and deleted:
        print(f"\n🧹 清理完成（{work_dir}）")
        print("-" * 50)
        types = {}
        for t, name in deleted:
            types.setdefault(t, []).append(name)
        for t, names in sorted(types.items()):
            print(f"  [{t}] ({len(names)}个)")
            if not quiet:
                for n in names:
                    print(f"    - {n}")
    elif dry_run:
        print(f"\n🔍 Dry Run（{work_dir}）- 以下文件将被删除")
        print("-" * 50)
        types = {}
        for t, name in deleted:
            types.setdefault(t, []).append(name)
        for t, names in sorted(types.items()):
            print(f"  [{t}] 共 {len(names)}个:")
            for n in names:
                print(f"    - {n}")

    return len(deleted)


def main():
    import sys
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    quiet = "--quiet" in args
    force = "--force" in args
    wd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if dry_run:
        print(f"=== Dry Run: {wd} ===")
    count = run_cleanup(wd, dry_run=dry_run, quiet=quiet, force=force)
    if not dry_run:
        print(f"\n已删除 {count} 个缓存文件" if not quiet else f"cleanup: {count} files removed")


if __name__ == "__main__":
    main()
