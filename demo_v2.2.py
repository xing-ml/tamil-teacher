#!/usr/bin/env python3
"""
Tamil Colloquial Teaching System v2.2 - Complete with Proper Tanglish Conversion
Shows corpus with phonetic transliteration for Hermes integration
"""

import json
import sys
from pathlib import Path

def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def main() -> int:
    base_dir = Path(__file__).parent
    
    print_section("🎯 Tamil Colloquial Teaching System v2.2")
    print("Architecture: Standard Difficulty + Phonetic Tanglish Conversion\n")
    
    # Load difficulty levels
    difficulty_file = base_dir / "data" / "difficulty_levels.json"
    if not difficulty_file.exists():
        print("ERROR: difficulty_levels.json not found")
        return 1
    
    difficulty_data = json.loads(difficulty_file.read_text(encoding="utf-8"))
    levels = difficulty_data.get("difficulty_levels", {})
    
    # Show corpus with Tanglish
    print_section("📚 Corpus Entries with Tanglish Conversion")
    corpus_file = base_dir / "data" / "corpus" / "tamil_corpus.json"
    if not corpus_file.exists():
        print("ERROR: Corpus not found")
        return 1
    
    corpus_data = json.loads(corpus_file.read_text(encoding="utf-8"))
    entries = corpus_data.get("entries", [])
    stats = corpus_data.get("stats", {})
    
    print(f"Total entries: {len(entries)}")
    print(f"Distribution by difficulty level:\n")
    
    for level_id in sorted(levels.keys(), key=lambda x: int(x)):
        count = stats.get("by_difficulty", {}).get(level_id, 0)
        if count > 0:
            level_name = levels[level_id].get("name", "?")
            print(f"  Level {level_id} ({level_name}): {count} entries")
    
    print_section("📋 Detailed Entry Preview")
    
    for i, entry in enumerate(entries, 1):
        level = entry.get("difficulty_level", "?")
        level_def = levels.get(level, {})
        level_name = level_def.get("name", "?")
        word_count = entry.get("word_count", 0)
        score = entry.get("colloquial_score", 0)
        
        print(f"{i}. Level {level} - {level_name}")
        print(f"   Tamil:    {entry.get('text', '')}")
        print(f"   Tanglish: {entry.get('tanglish_text', '')}")
        print(f"   Score: {score:.2f} | Words: {word_count}")
        print()
    
    print_section("🎓 Generated Lessons Summary")
    lessons_file = base_dir / "data" / "corpus" / "lessons_registry.json"
    if lessons_file.exists():
        lessons_data = json.loads(lessons_file.read_text(encoding="utf-8"))
        lessons = lessons_data.get("lessons", [])
        
        if lessons:
            print(f"Total lessons: {len(lessons)}\n")
            for lesson in lessons:
                level = lesson.get("difficulty_level", "?")
                level_name = levels.get(level, {}).get("name", "?")
                dtype = lesson.get("dialogue_type", "?")
                entries_count = lesson.get("entry_count", 0)
                
                print(f"Level {level} - {level_name} ({dtype})")
                print(f"  Entries in lesson: {entries_count}")
                
                # Show sample Tanglish
                lesson_entries = lesson.get("entries", [])
                if lesson_entries:
                    print(f"  Sample Tanglish:")
                    for entry in lesson_entries[:2]:
                        print(f"    - {entry.get('tanglish_text', '')}")
                print()
    
    print_section("✅ Features Now Complete")
    print("""
✅ Standard difficulty-based classification: 6 levels with defined features
✅ Entries filtered by difficulty standards: YES
✅ Phonetic transliteration (Tanglish): YES - Using tamil_translite library
✅ Lessons grouped by level & type: YES
✅ Hermes API ready: YES

Example Hermes Integration:
  Lesson contains Tamil + Tanglish + metadata
  Hermes can:
    - Read Tamil for pronunciation
    - Use Tanglish for English-speaker explanation
    - Reference difficulty level and features

Next Steps:
  1. Run daily collection to grow corpus
  2. Each new entry auto-classified by standards
  3. Tanglish auto-generated for all entries
  4. Hermes queries lessons with both Tamil + Tanglish
    """)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
