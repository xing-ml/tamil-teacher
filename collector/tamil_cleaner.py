#!/usr/bin/env python3
"""Clean, filter, and structure Tamil colloquial dialogue data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SOURCE_TITLE_BLOCKLIST = {
    "dictionary",
    "announcement",
    "megathread",
    "wall art",
    "article",
}
CONTENT_BLOCKLIST = {
    "all rights reserved",
    "submitted",
    "share save hide report",
    "important topic",
    "subscribe",
}


@dataclass
class CleanedDialogue:
    dialogue_id: str
    text: str
    source_type: str
    source_url: str
    source_title: str
    colloquial_score: float
    language: str
    detected_keywords: list[str]
    candidate_type: str
    word_count: int
    cleaned_at: str
    english_translation: str = ""  # English translation (from subtitles or machine translation)
    translation_source: str = ""  # "subtitle" if from YouTube subtitles, "machine" if from Google Translate


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def remove_emoji(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\u2702-\u27B0"
        "\u24C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)


def fix_repeated_chars(text: str) -> str:
    return re.sub(r"([a-zA-Z\u0b80-\u0bff])\1{2,}", r"\1\1", text)


def normalize_punctuation(text: str) -> str:
    text = re.sub(r"[!?]{2,}", "!", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s*[:：]\s*", ": ", text)
    return text.strip(" -\n\t")


def remove_urls(text: str) -> str:
    return re.sub(r"https?://\S+|www\.\S+", "", text)


def remove_mentions_hashtags(text: str) -> str:
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    return text


def remove_platform_boilerplate(text: str) -> str:
    patterns = [
        r"\bsubmitted\d+\s+\w+\s+ago\b",
        r"\bcommentsharesavehidereportloading\b",
        r"\bself\.[A-Za-z]+\b",
        r"\bcomment \d+\b",
        r"\bannouncement\b",
        r"\bAutoModerator\b",
        r"\(reddit\.com\)",
        r"\(i\.redd\.it\)",
        r"\bsubscribers subscribe\b",
    ]
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return text


def clean_text(text: str) -> str:
    text = normalize_whitespace(text)
    text = remove_emoji(text)
    text = remove_urls(text)
    text = remove_mentions_hashtags(text)
    text = remove_platform_boilerplate(text)
    text = fix_repeated_chars(text)
    text = normalize_punctuation(text)
    text = normalize_whitespace(text)
    return text


def load_tamil_keywords(keywords_file: str) -> dict:
    try:
        return json.loads(Path(keywords_file).read_text(encoding="utf-8")).get("colloquial_keywords", {})
    except Exception as exc:
        print(f"WARNING Failed to load keywords file: {exc}", file=sys.stderr)
        return {}


def get_all_keywords(keywords_data: dict) -> list[str]:
    all_keywords = []
    for keywords in keywords_data.values():
        if isinstance(keywords, list):
            all_keywords.extend(keywords)
    return [k.lower() for k in all_keywords]


def count_tamil_chars(text: str) -> int:
    return len(re.findall(r"[\u0b80-\u0bff]", text))


def looks_low_signal(title: str, text: str) -> bool:
    lowered_title = title.lower()
    lowered_text = text.lower()
    if any(token in lowered_title for token in SOURCE_TITLE_BLOCKLIST):
        return True
    if any(token in lowered_text for token in CONTENT_BLOCKLIST):
        return True
    if "dictionary" in lowered_text and "slang" not in lowered_text:
        return True
    return False


def detect_colloquial_score(text: str, keywords: list[str]) -> tuple[float, list[str]]:
    """Detect how colloquial/authentic a text is.
    
    For Tamil movie subtitles, we need to be more lenient since:
    - Movie dialogue may not contain our specific colloquial keywords
    - But it IS authentic Tamil spoken language
    - High Tamil char ratio IS the strongest signal of colloquial Tamil
    """
    text_lower = text.lower()
    detected: list[str] = []
    keyword_count = 0

    for keyword in keywords:
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text_lower):
            detected.append(keyword)
            keyword_count += 1

    tamil_chars = count_tamil_chars(text)
    total_chars = max(1, len(text))
    tamil_ratio = tamil_chars / total_chars
    word_count = max(1, len(text.split()))
    line_count = len([line for line in re.split(r"[\n\r]+", text) if line.strip()])
    has_dialogue_marker = bool(re.search(r"\b(comment \d+:|[A-Za-z]+:\s|[அ-ஹ]+:\s)", text))
    has_code_switch = tamil_chars > 0 and bool(re.search(r"[A-Za-z]{2,}", text))
    has_particles = any(token in text_lower for token in (" da", " di", " pa", " ma", "dei", "machi", "bro"))
    
    # Detect Tanglish pattern
    has_tanglish = bool(re.search(r"[A-Za-z]{3,}\s+[அ-ஹ]{2,}", text)) or \
                   bool(re.search(r"[அ-ஹ]{2,}\s+[A-Za-z]{3,}", text))
    
    # Detect Tamil movie subtitle markers (sound effects, music cues)
    has_subtitle_markers = bool(re.search(r"\[(?:இசை|கரகோஷம்|பின்னணி|திருவிழா|காட்சி)\]", text))

    score = 0.0
    
    # ===== PRIMARY SIGNAL: Tamil content ratio =====
    # This is the strongest indicator of authentic spoken Tamil
    if tamil_ratio > 0.8:
        score += 0.35  # Very strong signal
    elif tamil_ratio > 0.6:
        score += 0.25
    elif tamil_ratio > 0.4:
        score += 0.15
    elif tamil_ratio > 0.2:
        score += 0.08
    
    # ===== KEYWORD MATCHING =====
    score += min(0.25, keyword_count * 0.05)
    
    # ===== SPEECH SIGNALS =====
    # Dialogue markers (speaker labels)
    score += 0.12 if has_dialogue_marker else 0.0
    
    # Code switching / Tanglish
    if has_tanglish:
        score += 0.10
    elif has_code_switch:
        score += 0.06
    
    # Particles
    score += 0.06 if has_particles else 0.0
    
    # Sentence length (shorter = more colloquial)
    score += 0.04 if 3 <= word_count <= 18 else 0.0
    
    # Multi-line content
    score += 0.03 if line_count >= 2 else 0.0
    
    # Tamil subtitle markers (confirms it's movie dialogue)
    score += 0.05 if has_subtitle_markers else 0.0

    # Penalties
    if word_count < 3:
        score -= 0.2
    if word_count > 40:
        score -= 0.03  # Mild penalty for longer content

    return round(max(0.0, min(1.0, score)), 2), detected


def candidate_id(source_url: str, text: str) -> str:
    payload = f"{source_url}|{text}".lower().strip()
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def split_lines(text: str) -> list[str]:
    parts = re.split(r"(?:\n|Comment \d+:)", text)
    lines = [normalize_whitespace(part) for part in parts if normalize_whitespace(part)]
    return lines


def extract_dialogues(text: str) -> list[tuple[str, str]]:
    dialogues: list[tuple[str, str]] = []
    named_turns = re.findall(r"([A-Za-zஅ-ஹ]+):\s*([^:\n]{3,120})", text)
    if len(named_turns) >= 2:
        for idx in range(0, len(named_turns) - 1, 2):
            left = f"{named_turns[idx][0]}: {normalize_whitespace(named_turns[idx][1])}"
            right = f"{named_turns[idx + 1][0]}: {normalize_whitespace(named_turns[idx + 1][1])}"
            dialogues.append((left, right))

    lines = split_lines(text)
    for idx in range(0, len(lines) - 1, 2):
        left = lines[idx]
        right = lines[idx + 1]
        if 3 <= len(left.split()) <= 18 and 3 <= len(right.split()) <= 18:
            dialogues.append((left, right))

    unique_pairs: list[tuple[str, str]] = []
    seen = set()
    for left, right in dialogues:
        pair = (left, right)
        if pair in seen:
            continue
        seen.add(pair)
        unique_pairs.append(pair)
    return unique_pairs


def extract_sentence_candidates(text: str) -> list[str]:
    """Extract sentence candidates from text.
    
    Handles:
    - Standard punctuation (.!?;) and newlines
    - Tamil text without standard punctuation (splits by Tamil sentence patterns)
    - Mixed Tamil-English (Tanglish) content
    """
    # First try standard punctuation split
    sentences = re.split(r"[.!?;\n]+", text)
    
    # If that gives us nothing useful, try Tamil-aware splitting
    # Tamil sentences often end with: ன், ற், ட், ன், ற், ல், ங், ண், ன், ம், ன்
    # followed by a space or end of text
    if len(sentences) <= 1:
        # Split on Tamil sentence patterns: word + Tamil conjunct + space
        tamil_sentence_pattern = r"[அ-ஹ]{2,}(?:ன்|று|டு|ன|ற|ல|ங்|ண்|ம்|ன்|ய்|ள்|ர்|த்|ப்|க்|ப்|ம்|ன்)[\s\n]+"
        tamil_sentences = re.split(tamil_sentence_pattern, text)
        if len(tamil_sentences) >= 2:
            sentences = tamil_sentences
    
    # Also try splitting by Tamil full stop (U+0BE2)
    if len(sentences) <= 1:
        sentences = re.split(r"\u0BE2\s*|\u0BE4\s*|\u0BE6\s*", text)
    
    results = []
    for sentence in sentences:
        sentence = normalize_whitespace(sentence)
        if not sentence:
            continue
        word_count = len(sentence.split())
        tamil_chars = sum(1 for c in sentence if '\u0b80' <= c <= '\u0bff')
        # Accept: Tamil sentences with >= 3 chars OR English sentences with 2-25 words
        if (tamil_chars >= 3 and word_count >= 1) or (2 <= word_count <= 25):
            results.append(sentence)
    return results


def build_dialogue_entry(
    source: dict,
    text: str,
    score: float,
    detected_keywords: list[str],
    candidate_type: str,
    english_translation: str = "",
    translation_source: str = "",
) -> CleanedDialogue:
    return CleanedDialogue(
        dialogue_id=candidate_id(source.get("url", ""), text),
        text=text,
        source_type=source.get("source_type", "unknown"),
        source_url=source.get("url", ""),
        source_title=source.get("title", ""),
        colloquial_score=score,
        language=source.get("language", "unknown"),
        detected_keywords=detected_keywords,
        candidate_type=candidate_type,
        word_count=len(text.replace("\n", " ").split()),
        cleaned_at=now_iso(),
        english_translation=english_translation,
        translation_source=translation_source,
    )


def process_sources(agent_data: dict, keywords: list[str], min_colloquial_score: float = 0.5) -> list[CleanedDialogue]:
    cleaned_dialogues: list[CleanedDialogue] = []
    seen_ids: set[str] = set()
    
    stats = {
        "total_sources": 0,
        "filtered_empty": 0,
        "filtered_low_signal": 0,
        "filtered_low_score": 0,
        "passed_filters": 0,
        "extracted_pairs": 0,
        "extracted_sentences": 0,
    }

    for source in agent_data.get("sources", []):
        stats["total_sources"] += 1
        content = source.get("content", "")
        if not content or len(content.strip()) < 20:
            stats["filtered_empty"] += 1
            continue

        cleaned_content = clean_text(content)
        if looks_low_signal(source.get("title", ""), cleaned_content):
            stats["filtered_low_signal"] += 1
            continue

        colloquial_score, detected_keywords = detect_colloquial_score(cleaned_content, keywords)
        if colloquial_score < min_colloquial_score:
            stats["filtered_low_score"] += 1
            continue
        
        stats["passed_filters"] += 1
        
        # Check if source has dual subtitles (Tamil + English)
        metadata = source.get("metadata", {})
        has_dual_subtitles = metadata.get("has_dual_subtitles", False)
        english_subtitle_text = metadata.get("english_subtitle")
        
        # If we have dual subtitles, extract English translation
        english_translation = ""
        translation_source = ""
        if has_dual_subtitles and english_subtitle_text:
            # Use the English subtitle as the translation
            english_translation = clean_text(english_subtitle_text)
            translation_source = "subtitle"

        for left, right in extract_dialogues(cleaned_content):
            dialogue_text = f"A: {left}\nB: {right}"
            entry = build_dialogue_entry(
                source, dialogue_text, colloquial_score, detected_keywords, "dialogue_pair",
                english_translation=english_translation,
                translation_source=translation_source,
            )
            if entry.dialogue_id not in seen_ids:
                seen_ids.add(entry.dialogue_id)
                cleaned_dialogues.append(entry)
                stats["extracted_pairs"] += 1

        for sentence in extract_sentence_candidates(cleaned_content):
            if len(detected_keywords) == 0 and count_tamil_chars(sentence) < 8:
                continue
            entry = build_dialogue_entry(
                source, sentence, colloquial_score, detected_keywords, "sentence",
                english_translation=english_translation,
                translation_source=translation_source,
            )
            if entry.dialogue_id not in seen_ids:
                seen_ids.add(entry.dialogue_id)
                cleaned_dialogues.append(entry)
                stats["extracted_sentences"] += 1
    
    # Print diagnostic info
    print(f"\nDIAG Process Sources Stats:", file=sys.stderr)
    for key, val in sorted(stats.items()):
        print(f"  {key}: {val}", file=sys.stderr)

    cleaned_dialogues.sort(
        key=lambda item: (
            item.candidate_type != "dialogue_pair",
            -item.colloquial_score,
            item.word_count,
        )
    )
    return cleaned_dialogues


def build_structured_output(cleaned_dialogues: list[CleanedDialogue]) -> dict:
    return {
        "version": "v2.0",
        "generated_at": now_iso(),
        "stats": {
            "total_dialogues": len(cleaned_dialogues),
            "by_source_type": {
                source_type: len([d for d in cleaned_dialogues if d.source_type == source_type])
                for source_type in sorted({d.source_type for d in cleaned_dialogues})
            },
            "by_language": {
                lang: len([d for d in cleaned_dialogues if d.language == lang])
                for lang in sorted({d.language for d in cleaned_dialogues})
            },
            "by_candidate_type": {
                candidate_type: len([d for d in cleaned_dialogues if d.candidate_type == candidate_type])
                for candidate_type in sorted({d.candidate_type for d in cleaned_dialogues})
            },
            "average_colloquial_score": round(
                sum(d.colloquial_score for d in cleaned_dialogues) / len(cleaned_dialogues),
                2,
            )
            if cleaned_dialogues
            else 0,
        },
        "dialogues": [
            {
                "dialogue_id": d.dialogue_id,
                "text": d.text,
                "source_type": d.source_type,
                "source_url": d.source_url,
                "source_title": d.source_title,
                "colloquial_score": d.colloquial_score,
                "language": d.language,
                "detected_keywords": d.detected_keywords,
                "candidate_type": d.candidate_type,
                "word_count": d.word_count,
            }
            for d in cleaned_dialogues
        ],
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean Tamil colloquial dialogue data")
    parser.add_argument("--agent-input", required=True)
    parser.add_argument("--keywords-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-colloquial-score", type=float, default=0.3)
    args = parser.parse_args()

    print("INFO Tamil Cleaner starting...", file=sys.stderr)
    agent_data = json.loads(Path(args.agent_input).read_text(encoding="utf-8"))
    keywords_data = load_tamil_keywords(args.keywords_file)
    all_keywords = get_all_keywords(keywords_data)

    print(f"INFO Loaded {len(all_keywords)} Tamil keywords", file=sys.stderr)
    print(f"INFO Processing {len(agent_data.get('sources', []))} sources...", file=sys.stderr)

    cleaned_dialogues = process_sources(agent_data, all_keywords, args.min_colloquial_score)
    print(f"INFO Extracted {len(cleaned_dialogues)} cleaned dialogues", file=sys.stderr)

    structured = build_structured_output(cleaned_dialogues)
    output_file = Path(args.output_dir) / "tamil_cleaned_dialogues.json"
    write_json(output_file, structured)
    print(f"INFO Output: {output_file}", file=sys.stderr)
    print(str(output_file), file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
