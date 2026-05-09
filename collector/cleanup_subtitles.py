#!/usr/bin/env python3
"""清理 subtitles 目录下不符合规则的文件和目录。

清理规则:
1. 电影目录: 只保留 {movie_name}.{lang}.srt 格式的文件
2. 剧集集目录: 只保留 {series}.S{season}E{episode}.{lang}.srt 格式的文件
3. 删除所有非 .srt 文件、隐藏文件、临时文件
4. 删除季/集目录名不符合 S{2位数字}/E{2位数字}/ 的目录树
5. 递归清理产生的空目录
6. 报告清理结果

用法:
    python collector/cleanup_subtitles.py [--dry-run] [--force]
"""

import os
import re
import sys
import time
import shutil
from pathlib import Path

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent.parent / "data" / "subtitles"
TRASH_DIR = Path(__file__).parent.parent / "data" / "subtitles" / "_cleanup_trash"

# 标准季/集目录名正则
SEASON_DIR_RE = re.compile(r"^S(\d{2})$")      # S01, S02, ...
EPISODE_DIR_RE = re.compile(r"^E(\d{2})$")     # E01, E02, ...

# 电影字幕文件名正则: {movie_name}.{lang}[cc].srt
# lang 格式: xx-xx, xx-xx[cc], xx-001, xx-419 等
MOVIE_FILE_RE = re.compile(r"^(.+)\.([a-z]{2,3}-[a-z0-9]{2,4}(?:\[cc\])?)\.srt$")

# 剧集字幕文件名正则: {series}.S{season}E{episode}.{lang}[cc].srt
TV_FILE_RE = re.compile(r"^(.+)\.(S\d{2}E\d{2})\.([a-z]{2,3}-[a-z0-9]{2,4}(?:\[cc\])?)\.srt$")

# 隐藏文件/系统文件模式
HIDDEN_FILE_RE = re.compile(r"^\..*")
TEMP_FILE_RE = re.compile(r"\.(tmp|part|bak|swp|swo)$")

# ============================================================
# 统计
# ============================================================
class Stats:
    def __init__(self):
        self.deleted_files = 0
        self.deleted_dirs = 0
        self.moved_files = 0
        self.moved_dirs = 0
        self.skipped_files = 0
        self.errors = 0

    def report(self):
        print("\n" + "=" * 60)
        print("清理报告")
        print("=" * 60)
        print(f"  删除文件:     {self.deleted_files}")
        print(f"  删除目录:     {self.deleted_dirs}")
        print(f"  移动文件:     {self.moved_files}")
        print(f"  移动目录:     {self.moved_dirs}")
        print(f"  跳过文件:     {self.skipped_files}")
        if self.errors:
            print(f"  错误:         {self.errors}")
        print("=" * 60)


stats = Stats()

# ============================================================
# 工具函数
# ============================================================
def is_hidden(name: str) -> bool:
    """检查是否为隐藏文件/目录"""
    return HIDDEN_FILE_RE.match(name) is not None

def is_temp_file(name: str) -> bool:
    """检查是否为临时文件"""
    return TEMP_FILE_RE.search(name) is not None

def move_to_trash(src: Path, report_name: str = ""):
    """将文件或目录移动到回收站"""
    if TRASH_DIR.exists() or dry_run:
        pass
    elif not dry_run:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
    
    if dry_run:
        print(f"  [DRY-RUN] 移动: {src}")
        stats.moved_files += 1 if src.is_file() else 0
        stats.moved_dirs += 1 if src.is_dir() else 0
        return
    
    try:
        dst = TRASH_DIR / src.name
        if dst.exists():
            dst = TRASH_DIR / f"{src.name}_{int(time.time())}"
        if src.is_file():
            shutil.move(str(src), str(dst))
            stats.moved_files += 1
        elif src.is_dir():
            shutil.move(str(src), str(dst))
            stats.moved_dirs += 1
        if report_name:
            print(f"  移动: {report_name}")
    except Exception as e:
        print(f"  错误: 移动 {src} 失败: {e}")
        stats.errors += 1

def remove_item(src: Path, report_name: str = ""):
    """删除文件或目录"""
    if dry_run:
        print(f"  [DRY-RUN] 删除: {src}")
        stats.deleted_files += 1 if src.is_file() else 0
        stats.deleted_dirs += 1 if src.is_dir() else 0
        return
    
    try:
        if src.is_file():
            src.unlink()
            stats.deleted_files += 1
        elif src.is_dir():
            shutil.rmtree(str(src))
            stats.deleted_dirs += 1
        if report_name:
            print(f"  删除: {report_name}")
    except Exception as e:
        print(f"  错误: 删除 {src} 失败: {e}")
        stats.errors += 1

def clean_empty_dirs(base: Path):
    """递归清理空目录（从最深层开始）"""
    for root, dirs, files in os.walk(str(base), topdown=False):
        root_path = Path(root)
        if root_path == base:
            continue
        try:
            if not any(root_path.iterdir()):
                rel = root_path.relative_to(base)
                if not dry_run:
                    root_path.rmdir()
                    stats.deleted_dirs += 1
                    print(f"  删除空目录: {rel}")
                else:
                    stats.deleted_dirs += 1
                    print(f"  [DRY-RUN] 删除空目录: {rel}")
        except Exception as e:
            pass  # 目录不空或有权限问题，跳过

def is_standard_season(dirname: str) -> tuple:
    """检查是否为标准季目录名 S{2位数字}，返回 (is_match, season_num)"""
    m = SEASON_DIR_RE.match(dirname)
    return (True, m.group(1)) if m else (False, None)

def is_standard_episode(dirname: str) -> tuple:
    """检查是否为标准集目录名 E{2位数字}，返回 (is_match, episode_num)"""
    m = EPISODE_DIR_RE.match(dirname)
    return (True, m.group(1)) if m else (False, None)

def validate_movie_file(filepath: Path, movie_dir: Path) -> bool:
    """验证电影字幕文件名是否符合 {movie_name}.{lang}.srt"""
    basename = filepath.name
    dir_name = movie_dir.name
    m = MOVIE_FILE_RE.match(basename)
    if not m:
        return False
    # 文件名前缀应等于目录名
    file_prefix = m.group(1)
    return file_prefix == dir_name

def validate_tv_file(filepath: Path, tv_dir: Path, season_dir: Path, episode_dir: Path) -> bool:
    """验证剧集字幕文件名是否符合 {series}.S{season}E{episode}.{lang}.srt"""
    basename = filepath.name
    series_name = tv_dir.name
    season_num = season_dir.name[1:]  # S01 -> 01
    episode_num = episode_dir.name[1:]  # E01 -> 01
    expected_se = f"S{season_num}E{episode_num}"
    
    m = TV_FILE_RE.match(basename)
    if not m:
        return False
    return m.group(1) == series_name and m.group(2) == expected_se

# ============================================================
# 主清理逻辑
# ============================================================
def cleanup_category(cat_path: Path):
    """清理单个 category 目录"""
    cat_name = cat_path.name
    
    # 检查 category 目录下是否有非目录文件
    for item in cat_path.iterdir():
        if item.is_file():
            if is_hidden(item.name) or is_temp_file(item.name):
                print(f"\n[{cat_name}] 隐藏/临时文件: {item.name}")
                move_to_trash(item, f"{cat_name}/{item.name}")
            else:
                print(f"\n[{cat_name}] 非目录文件: {item.name}")
                move_to_trash(item, f"{cat_name}/{item.name}")
    
    # 遍历 category 下的所有子项
    for item in cat_path.iterdir():
        if not item.is_dir():
            continue
        
        item_name = item.name
        
        # 判断是 section、movie 还是 series
        # Section: 包含 movie 目录或 series 目录，且自身不以 S{nn} 开头
        # Series: 包含 S{nn} 子目录
        # Movie: 包含 {name}.{lang}.srt 文件
        
        has_season_dirs = any(SEASON_DIR_RE.match(d.name) for d in item.iterdir() if d.is_dir())
        
        if has_season_dirs:
            # 这是剧集目录
            cleanup_series(item, cat_name)
        else:
            # 这是 section 或 movie 目录
            cleanup_movie_section(item, cat_name)

def cleanup_series(series_dir: Path, cat_name: str):
    """清理剧集目录"""
    series_name = series_dir.name
    print(f"\n{'='*60}")
    print(f"检查剧集: {cat_name}/{series_name}")
    
    # 检查剧集目录下是否有非 S{nn} 子目录
    for sub in series_dir.iterdir():
        if sub.is_file():
            # 旧格式剧集文件: {series}.S{season}E{episode}.{lang}.srt
            if TV_FILE_RE.match(sub.name):
                print(f"  [旧格式] 移动: {sub.name}")
                move_to_trash(sub, f"{cat_name}/{series_name}/{sub.name}")
            else:
                print(f"  [异常文件] 移动: {sub.name}")
                move_to_trash(sub, f"{cat_name}/{series_name}/{sub.name}")
        elif sub.is_dir():
            is_season, _ = is_standard_season(sub.name)
            if not is_season:
                print(f"  [异常目录] 删除: {sub.name}")
                remove_item(sub, f"{cat_name}/{series_name}/{sub.name}")
    
    # 清理每个季目录
    for season_dir in series_dir.iterdir():
        if not season_dir.is_dir():
            continue
        
        is_season, season_num = is_standard_season(season_dir.name)
        if not is_season:
            print(f"  [非标准季目录] 删除: {season_dir.name}")
            remove_item(season_dir, f"{cat_name}/{series_name}/{season_dir.name}")
            continue
        
        # 清理季目录下的内容
        for episode_dir in season_dir.iterdir():
            if episode_dir.is_file():
                print(f"  [季目录中的文件] 删除: {episode_dir.name}")
                remove_item(episode_dir, f"{cat_name}/{series_name}/{season_dir.name}/{episode_dir.name}")
            elif episode_dir.is_dir():
                is_ep, ep_num = is_standard_episode(episode_dir.name)
                if not is_ep:
                    print(f"  [非标准集目录] 删除: {episode_dir.name}")
                    remove_item(episode_dir, f"{cat_name}/{series_name}/{season_dir.name}/{episode_dir.name}")
                    continue
                
                # 清理集目录中的文件
                for file in episode_dir.iterdir():
                    if file.is_dir():
                        print(f"  [集目录中的子目录] 删除: {file.name}")
                        remove_item(file, f"{cat_name}/{series_name}/{season_dir.name}/{episode_dir.name}/{file.name}")
                    elif file.is_file():
                        if is_hidden(file.name) or is_temp_file(file.name):
                            print(f"  [隐藏/临时文件] 移动: {file.name}")
                            move_to_trash(file, f"{cat_name}/{series_name}/{season_dir.name}/{episode_dir.name}/{file.name}")
                        elif not validate_tv_file(file, series_dir, season_dir, episode_dir):
                            print(f"  [命名不符] 移动: {file.name}")
                            move_to_trash(file, f"{cat_name}/{series_name}/{season_dir.name}/{episode_dir.name}/{file.name}")
                        else:
                            stats.skipped_files += 1

def cleanup_movie_section(section_dir: Path, cat_name: str):
    """清理 section 目录或 movie 目录"""
    section_name = section_dir.name
    
    # 检查 section 目录下是否有非目录文件
    for item in section_dir.iterdir():
        if item.is_file():
            if is_hidden(item.name) or is_temp_file(item.name):
                print(f"\n[{cat_name}/{section_name}] 隐藏/临时文件: {item.name}")
                move_to_trash(item, f"{cat_name}/{section_name}/{item.name}")
            else:
                print(f"\n[{cat_name}/{section_name}] 非预期文件: {item.name}")
                move_to_trash(item, f"{cat_name}/{section_name}/{item.name}")
    
    # 遍历 section 下的子项
    for item in section_dir.iterdir():
        if not item.is_dir():
            continue
        
        item_name = item.name
        
        # 判断是 movie 还是 series
        has_season_dirs = any(SEASON_DIR_RE.match(d.name) for d in item.iterdir() if d.is_dir())
        
        if has_season_dirs:
            # 这是剧集
            cleanup_series(item, f"{cat_name}/{section_name}")
        else:
            # 这是电影目录
            cleanup_movie(item, cat_name, section_name)

def cleanup_movie(movie_dir: Path, cat_name: str, section_name: str = ""):
    """清理电影目录"""
    movie_name = movie_dir.name
    prefix = f"{cat_name}/{section_name}" if section_name else cat_name
    
    # 检查电影目录下是否有非字幕子目录
    for sub in movie_dir.iterdir():
        if sub.is_dir():
            print(f"  [电影目录中的子目录] 删除: {sub.name}")
            remove_item(sub, f"{prefix}/{movie_name}/{sub.name}")
    
    # 清理电影目录中的文件
    for file in movie_dir.iterdir():
        if file.is_dir():
            continue
        
        if is_hidden(file.name) or is_temp_file(file.name):
            print(f"  [隐藏/临时文件] 移动: {file.name}")
            move_to_trash(file, f"{prefix}/{movie_name}/{file.name}")
        elif not validate_movie_file(file, movie_dir):
            print(f"  [命名不符] 移动: {file.name}")
            move_to_trash(file, f"{prefix}/{movie_name}/{file.name}")
        else:
            stats.skipped_files += 1

def main():
    global dry_run
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    
    print("=" * 60)
    print("字幕目录清理工具")
    print("=" * 60)
    print(f"  根目录: {BASE_DIR}")
    print(f"  回收站: {TRASH_DIR}")
    print(f"  模式:   {'DRY-RUN (预览)' if dry_run else '实际执行'}")
    print("=" * 60)
    
    if not BASE_DIR.exists():
        print(f"错误: 目录不存在: {BASE_DIR}")
        sys.exit(1)
    
    if not dry_run and not force:
        confirm = input("\n确定要清理吗？(y/N): ")
        if confirm.lower() not in ("y", "yes", "y", "是"):
            print("已取消")
            sys.exit(0)
    
    # 第一遍：清理所有不符合规则的文件和目录
    print("\n第一遍：清理不符合规则的文件和目录...")
    for cat in BASE_DIR.iterdir():
        if cat.is_dir() and cat.name != "_cleanup_trash":
            cleanup_category(cat)
    
    # 第二遍：递归清理空目录
    print("\n第二遍：清理空目录...")
    clean_empty_dirs(BASE_DIR)
    
    # 报告
    stats.report()
    
    if not dry_run and TRASH_DIR.exists() and any(TRASH_DIR.iterdir()):
        print(f"\n被移动的文件在: {TRASH_DIR}")
        print("确认无误后可手动删除回收站目录")

if __name__ == "__main__":
    main()
