#!/usr/bin/env python3
"""Tamil Colloquial Corpus Manager - manages local dialogue corpus and lesson generation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

try:
    from tamil_translite import translite
except ImportError:
    translite = None

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None


@dataclass
class CorpusEntry:
    """A single dialogue entry in the corpus."""
    entry_id: str
    text: str
    source_type: str
    source_url: str
    source_title: str
    language: str
    difficulty_level: str
    dialogue_type: str  # "sentence", "dialogue_pair", "conversation_chunk"
    colloquial_score: float
    tanglish_text: str  # Tamil converted to Tanglish
    word_count: int
    added_at: str
    metadata: dict


@dataclass
class Lesson:
    """A generated lesson from corpus entries."""
    lesson_id: str
    title: str
    difficulty_level: str
    dialogue_type: str
    entries: List[CorpusEntry]
    generated_at: str
    metadata: dict


class TamilCorpusManager:
    """Manages the Tamil colloquial dialogue corpus."""

    def __init__(self, corpus_dir: str | Path):
        self.corpus_dir = Path(corpus_dir)
        self.corpus_dir.mkdir(parents=True, exist_ok=True)
        self.corpus_file = self.corpus_dir / "tamil_corpus.json"
        self.lessons_file = self.corpus_dir / "lessons_registry.json"
        self.lessons_data = []
        self.difficulty_levels = self._load_difficulty_levels()
        self._load_corpus()
        self._load_lessons()
    
    def _load_difficulty_levels(self) -> dict:
        """Load difficulty level definitions."""
        difficulty_file = self.corpus_dir.parent / "difficulty_levels.json"
        if difficulty_file.exists():
            try:
                data = json.loads(difficulty_file.read_text(encoding="utf-8"))
                return data.get("difficulty_levels", {})
            except Exception as e:
                print(f"WARNING Failed to load difficulty levels: {e}")
        return {}

    def _load_corpus(self) -> None:
        """Load existing corpus from disk."""
        if self.corpus_file.exists():
            try:
                data = json.loads(self.corpus_file.read_text(encoding="utf-8"))
                self.entries = [CorpusEntry(**entry) for entry in data.get("entries", [])]
                self.stats = data.get("stats", {})
            except Exception as e:
                print(f"WARNING Failed to load corpus: {e}")
                self.entries = []
                self.stats = {}
        else:
            self.entries = []
            self.stats = {}

    def _load_lessons(self) -> None:
        """Load existing lessons registry."""
        if self.lessons_file.exists():
            try:
                data = json.loads(self.lessons_file.read_text(encoding="utf-8"))
                # Don't try to recreate Lesson objects - keep raw dict for simpler serialization
                self.lessons_data = data.get("lessons", [])
            except Exception as e:
                print(f"WARNING Failed to load lessons: {e}")
                self.lessons_data = []
        else:
            self.lessons_data = []

    def _save_corpus(self) -> None:
        """Save corpus to disk."""
        try:
            data = {
                "entries": [vars(entry) for entry in self.entries],
                "stats": self.stats,
                "updated_at": datetime.now().isoformat(),
            }
            self.corpus_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"WARNING Failed to save corpus: {e}")

    def _save_lessons(self) -> None:
        """Save lessons registry to disk."""
        try:
            data = {
                "lessons": self.lessons_data,
                "updated_at": datetime.now().isoformat(),
            }
            self.lessons_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"WARNING Failed to save lessons: {e}")

    def _tamil_to_tanglish(self, tamil_text: str) -> str:
        """Convert Tamil script to Tanglish (Tamil in English phonetic letters)."""
        if not translite:
            return tamil_text
        try:
            return translite(tamil_text)
        except Exception as e:
            print(f"WARNING Failed to convert to Tanglish: {e}")
            return tamil_text

    def _translate_to_english(self, tamil_text: str) -> str:
        """Translate Tamil text into English using deep-translator."""
        if not GoogleTranslator:
            return ""
        try:
            translator = GoogleTranslator(source='ta', target='en')
            return translator.translate(tamil_text)
        except Exception as e:
            print(f"WARNING Failed to translate to English: {e}")
            return ""

    def _determine_difficulty(self, text: str, score: float) -> str | None:
        """
        Determine difficulty level based on defined standards.
        Returns level 1-6 if it matches criteria, else None.
        """
        if not self.difficulty_levels:
            return None
        
        word_count = len(text.split())
        tamil_chars = len(re.findall(r"[\u0b80-\u0bff]", text))
        
        # Check each difficulty level (1-6) in order
        for level in range(1, 7):
            level_def = self.difficulty_levels.get(str(level))
            if not level_def:
                continue
            
            # Check word count range
            min_words, max_words = level_def.get("sentence_words", [0, 0])
            if not (min_words <= word_count <= max_words):
                continue
            
            # Check for required features
            features = level_def.get("features", [])
            if not features:
                # No specific features required, can assign this level
                return str(level)
            
            # Check if content matches feature requirements
            feature_match = self._check_features(text, score, tamil_chars, features)
            if feature_match:
                return str(level)
        
        # If no level matches exactly, try to find best fit based on word_count alone
        # This is a fallback for edge cases
        for level in range(1, 7):
            level_def = self.difficulty_levels.get(str(level))
            if level_def:
                min_words, max_words = level_def.get("sentence_words", [0, 0])
                if min_words <= word_count <= max_words:
                    return str(level)
        
        return None
    
    def _check_features(self, text: str, score: float, tamil_chars: int, features: list) -> bool:
        """Check if text matches required features for a difficulty level."""
        text_lower = text.lower()
        
        for feature in features:
            if feature == "single_words":
                # Should be mostly Tamil characters, single word-like
                if len(text.split()) > 1:
                    return False
            
            elif feature == "basic_questions":
                # Contains question marks or question words
                if "?" not in text and not any(q in text_lower for q in ["enna", "epdi", "enga", "yen"]):
                    return False
            
            elif feature == "high_repetition":
                # High colloquial score or repeated words
                if score < 0.3:
                    return False
            
            elif feature == "short_sentences":
                # Already checked by word count, OK
                continue
            
            elif feature == "basic_verbs":
                # Contains basic Tamil verbs
                basic_verbs = ["panra", "varra", "pora", "solvra", "kudikra", "sapdu"]
                if not any(verb in text_lower for verb in basic_verbs):
                    return False
            
            elif feature == "simple_responses":
                # Short, affirmative/negative responses
                if len(text.split()) > 4:
                    return False
            
            elif feature == "compound_phrases":
                # Multiple parts or conjunctions
                if "," not in text and " and " not in text_lower:
                    return False
            
            elif feature == "tense_usage":
                # Contains tense markers
                tense_markers = ["irukku", "irundhena", "poren", "panren", "varen"]
                if not any(marker in text_lower for marker in tense_markers):
                    return False
            
            elif feature == "common_slang":
                # High colloquial score indicates slang
                if score < 0.4:
                    return False
            
            elif feature == "longer_sentences":
                # Already checked by word count, OK
                continue
            
            elif feature == "emotion_expression":
                # Contains emotion words
                emotions = ["happy", "sad", "angry", "stressed", "aiyyo", "yean", "dei", "machi"]
                if not any(em in text_lower for em in emotions):
                    return False
            
            elif feature == "code_switching":
                # Mix of Tamil and English
                has_tamil = tamil_chars > 0
                has_english = bool(re.search(r"[A-Za-z]", text))
                if not (has_tamil and has_english):
                    return False
            
            elif feature == "multi_clause":
                # Multiple sentences or clauses
                if text.count(".") < 1 and text.count(",") < 1:
                    return False
            
            elif feature == "implicit_meaning":
                # High score and longer text (complex meaning)
                if score < 0.3 or len(text.split()) < 6:
                    return False
            
            elif feature == "fast_speech_patterns":
                # Short words strung together (colloquial speech)
                avg_word_len = sum(len(w) for w in text.split()) / max(1, len(text.split()))
                if avg_word_len > 7:  # Average word too long for fast speech
                    return False
            
            elif feature == "context_heavy":
                # Long, complex text with references
                if len(text.split()) < 8:
                    return False
            
            elif feature == "sarcasm":
                # Harder to detect programmatically, use score as proxy
                if score < 0.4:
                    return False
            
            elif feature == "regional_variation":
                # Non-standard spelling or dialect markers
                # Use high score as indicator of colloquial/regional
                if score < 0.3:
                    return False
        
        return True

    def add_entries_from_cleaned(self, cleaned_dialogues: List[dict]) -> dict:
        """Add entries from cleaned dialogues JSON, filtering by difficulty standards."""
        added_count = 0
        skipped_count = 0
        skipped_reason = {"no_difficulty": 0, "low_score": 0, "already_exists": 0}
        
        seen_ids = {entry.entry_id for entry in self.entries}

        for dialogue in cleaned_dialogues:
            entry_id = dialogue["dialogue_id"]
            if entry_id in seen_ids:
                skipped_count += 1
                skipped_reason["already_exists"] += 1
                continue
            
            # Determine difficulty using standard-based method
            difficulty_level = self._determine_difficulty(
                dialogue["text"],
                dialogue["colloquial_score"]
            )
            
            if difficulty_level is None:
                skipped_count += 1
                skipped_reason["no_difficulty"] += 1
                continue
            
            # Additional quality check
            if dialogue["colloquial_score"] < 0.2:
                skipped_count += 1
                skipped_reason["low_score"] += 1
                continue

            tanglish_text = self._tamil_to_tanglish(dialogue["text"])

            entry = CorpusEntry(
                entry_id=entry_id,
                text=dialogue["text"],
                source_type=dialogue["source_type"],
                source_url=dialogue["source_url"],
                source_title=dialogue["source_title"],
                language=dialogue["language"],
                difficulty_level=difficulty_level,
                dialogue_type=dialogue["candidate_type"],
                colloquial_score=dialogue["colloquial_score"],
                tanglish_text=tanglish_text,
                word_count=dialogue["word_count"],
                added_at=datetime.now().isoformat(),
                metadata={
                    "detected_keywords": dialogue.get("detected_keywords", []),
                    "source_fingerprint": hashlib.sha1(dialogue["text"].encode()).hexdigest(),
                }
            )

            self.entries.append(entry)
            added_count += 1

        if added_count > 0:
            self._update_stats()
            self._save_corpus()

        return {
            "added": added_count,
            "skipped": skipped_count,
            "skipped_details": skipped_reason,
        }

    def _update_stats(self) -> None:
        """Update corpus statistics."""
        self.stats = {
            "total_entries": len(self.entries),
            "by_source_type": {},
            "by_difficulty": {},
            "by_dialogue_type": {},
            "by_language": {},
            "avg_colloquial_score": 0.0,
        }

        if self.entries:
            scores = [e.colloquial_score for e in self.entries]
            self.stats["avg_colloquial_score"] = round(sum(scores) / len(scores), 2)

            for entry in self.entries:
                self.stats["by_source_type"][entry.source_type] = self.stats["by_source_type"].get(entry.source_type, 0) + 1
                self.stats["by_difficulty"][entry.difficulty_level] = self.stats["by_difficulty"].get(entry.difficulty_level, 0) + 1
                self.stats["by_dialogue_type"][entry.dialogue_type] = self.stats["by_dialogue_type"].get(entry.dialogue_type, 0) + 1
                self.stats["by_language"][entry.language] = self.stats["by_language"].get(entry.language, 0) + 1

    def generate_lessons(self, difficulty_level: str | None = None, max_entries_per_lesson: int = 10) -> List[dict]:
        """Generate lessons from corpus entries using standard difficulty levels."""
        # Filter entries by difficulty if specified
        candidates = self.entries
        if difficulty_level:
            candidates = [e for e in candidates if e.difficulty_level == difficulty_level]

        if not candidates:
            return []

        # Group by difficulty, dialogue type and source_url to preserve context
        groups = {}
        for entry in candidates:
            key = f"level{entry.difficulty_level}_{entry.dialogue_type}_{hashlib.sha1(entry.source_url.encode()).hexdigest()}"
            if key not in groups:
                groups[key] = {
                    "entries": [],
                    "difficulty_level": entry.difficulty_level,
                    "dialogue_type": entry.dialogue_type,
                    "source_url": entry.source_url,
                }
            groups[key]["entries"].append(entry)

        new_lessons = []
        for group_key, group_data in groups.items():
            entries = group_data["entries"]
            # A lesson must contain at least two entries for sentence-only groups.
            if group_data["dialogue_type"] == "sentence" and len(entries) < 2:
                continue
            if len(entries) < 1:
                continue

            # Create lessons in chunks
            for i in range(0, len(entries), max_entries_per_lesson):
                chunk = entries[i:i + max_entries_per_lesson]
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                lesson_id = f"{group_key}_{timestamp}_{i//max_entries_per_lesson}"

                # Get difficulty name from definitions
                level_num = chunk[0].difficulty_level
                level_def = self.difficulty_levels.get(level_num, {})
                level_name = level_def.get("name", f"Level {level_num}")

                lesson_dict = {
                    "lesson_id": lesson_id,
                    "title": f"Tamil Colloquial Level {level_num} - {level_name} ({chunk[0].dialogue_type})",
                    "difficulty_level": level_num,
                    "dialogue_type": chunk[0].dialogue_type,
                    "entry_count": len(chunk),
                    "generated_at": datetime.now().isoformat(),
                    "metadata": {
                        "entry_count": len(chunk),
                        "avg_score": round(sum(e.colloquial_score for e in chunk) / len(chunk), 2),
                        "source_types": list(set(e.source_type for e in chunk)),
                        "level_definition": level_def,
                    },
                    "entries": [
                        {
                            "text": e.text,
                            "tanglish_text": e.tanglish_text,
                            "english_translation": self._translate_to_english(e.text),
                            "colloquial_score": e.colloquial_score,
                            "source_type": e.source_type,
                            "word_count": e.word_count,
                        }
                        for e in chunk
                    ]
                }

                self.lessons_data.append(lesson_dict)
                new_lessons.append(lesson_dict)

        if new_lessons:
            self._save_lessons()

        return new_lessons

    def get_lesson_for_hermes(self, difficulty_level: str, dialogue_type: str = "sentence") -> dict | None:
        """
        Get a lesson suitable for Hermes processing.
        difficulty_level: "1", "2", "3", "4", "5", or "6"
        dialogue_type: "sentence" or "dialogue_pair" or "conversation_chunk"
        """
        # Find matching lessons
        candidates = [
            lesson for lesson in self.lessons_data
            if lesson.get("difficulty_level") == difficulty_level and lesson.get("dialogue_type") == dialogue_type
        ]

        if not candidates:
            return None

        # Return the most recent lesson
        lesson = max(candidates, key=lambda l: l.get("generated_at", ""))

        return {
            "lesson_id": lesson["lesson_id"],
            "title": lesson["title"],
            "difficulty_level": lesson["difficulty_level"],
            "difficulty_name": self.difficulty_levels.get(difficulty_level, {}).get("name", "Unknown"),
            "entries": lesson.get("entries", []),
            "metadata": lesson.get("metadata", {}),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tamil Colloquial Corpus Manager")
    parser.add_argument("--corpus-dir", required=True, help="Corpus directory path")
    parser.add_argument("--add-cleaned", help="Add entries from cleaned dialogues JSON file")
    parser.add_argument("--generate-lessons", action="store_true", help="Generate lessons from corpus")
    parser.add_argument("--difficulty-level", help="Filter by difficulty level when generating lessons")
    parser.add_argument("--get-lesson", help="Get lesson for Hermes (format: difficulty_dialogue_type)")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    manager = TamilCorpusManager(corpus_dir)

    print(f"INFO Corpus loaded: {manager.stats.get('total_entries', 0)} entries", file=sys.stderr)

    if args.add_cleaned:
        cleaned_file = Path(args.add_cleaned)
        if cleaned_file.exists():
            cleaned_data = json.loads(cleaned_file.read_text(encoding="utf-8"))
            result = manager.add_entries_from_cleaned(cleaned_data.get("dialogues", []))
            print(f"INFO Added {result['added']} new entries to corpus", file=sys.stderr)
            if result['skipped'] > 0:
                print(f"INFO Skipped {result['skipped']} entries:", file=sys.stderr)
                for reason, count in result['skipped_details'].items():
                    if count > 0:
                        print(f"     - {reason}: {count}", file=sys.stderr)
        else:
            print(f"ERROR Cleaned file not found: {cleaned_file}", file=sys.stderr)
            return 1

    if args.generate_lessons:
        lessons = manager.generate_lessons(args.difficulty_level)
        print(f"INFO Generated {len(lessons)} new lessons", file=sys.stderr)
        for lesson in lessons:
            print(f"  - {lesson['lesson_id']}: {lesson['title']} ({lesson['entry_count']} entries)", file=sys.stderr)

    if args.get_lesson:
        # Format: "2_sentence" or just "2" (defaults to sentence)
        parts = args.get_lesson.split("_", 1)
        difficulty = parts[0]
        dialogue_type = parts[1] if len(parts) > 1 else "sentence"
        
        lesson = manager.get_lesson_for_hermes(difficulty, dialogue_type)
        if lesson:
            print(json.dumps(lesson, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR No lesson found for level {difficulty} / {dialogue_type}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())