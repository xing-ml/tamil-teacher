#!/usr/bin/env python3
"""
系统完整性检查 - 验证所有组件就位
"""

import json
import sys
from pathlib import Path

def check_file(path: Path, description: str) -> bool:
    """Check if a file exists."""
    exists = path.exists()
    status = "✅" if exists else "❌"
    print(f"  {status} {description}: {path.name}")
    return exists

def check_directory(path: Path, description: str) -> bool:
    """Check if a directory exists and has files."""
    exists = path.exists()
    status = "✅" if exists else "❌"
    file_count = len(list(path.glob("*"))) if exists else 0
    print(f"  {status} {description}: {len(list(path.glob('*')))} items")
    return exists

def main() -> int:
    base_dir = Path(__file__).parent
    all_ok = True
    
    print("\n" + "="*70)
    print("  系统完整性检查 (System Integrity Check)")
    print("="*70 + "\n")
    
    # Core scripts
    print("📄 Core Collectors & Processors:")
    all_ok &= check_file(base_dir / "collector" / "tamil_collector.py", "Collector")
    all_ok &= check_file(base_dir / "collector" / "tamil_cleaner.py", "Cleaner")
    all_ok &= check_file(base_dir / "collector" / "tamil_corpus_manager.py", "Corpus Manager (新)")
    all_ok &= check_file(base_dir / "collector" / "url_deduplicator.py", "URL Deduplicator (新)")
    
    print("\n🚀 Entry Points:")
    all_ok &= check_file(base_dir / "bin" / "tamil_daily_lesson.py", "Daily Pipeline")
    all_ok &= check_file(base_dir / "demo.py", "Demo & Status")
    
    print("\n📚 Data & Config:")
    all_ok &= check_file(base_dir / "data" / "tamil_keywords.json", "Tamil Keywords")
    all_ok &= check_file(base_dir / "data" / "scenario_definitions.json", "Scenarios")
    all_ok &= check_file(base_dir / "data" / "difficulty_levels.json", "Difficulty Levels")
    all_ok &= check_directory(base_dir / "data" / "corpus", "Local Corpus (新)")
    all_ok &= check_directory(base_dir / "data" / "cache", "URL Cache (新)")
    
    print("\n📊 Output / Temp:")
    all_ok &= check_directory(base_dir / "temp", "Temp Files")
    
    print("\n📖 Documentation:")
    all_ok &= check_file(base_dir / "ARCHITECTURE.md", "Architecture Guide (新)")
    all_ok &= check_file(base_dir / "README.md", "README")
    
    print("\n" + "="*70)
    if all_ok:
        print("  ✅ 所有组件就位 (All components ready)")
        print("="*70 + "\n")
        print("  🎉 系统v2.0已完全部署!")
        print("\n  快速开始:")
        print("    1. python demo.py              # 查看系统状态")
        print("    2. python bin/tamil_daily_lesson.py  # 运行完整流程")
        print("    3. python collector/tamil_corpus_manager.py \\")
        print("         --corpus-dir data/corpus \\")
        print("         --get-lesson 2b_sentence   # 获取lesson给Hermes")
        print("\n" + "="*70 + "\n")
        return 0
    else:
        print("  ⚠️  缺失某些组件 (Missing components)")
        print("="*70 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
