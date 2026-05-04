#!/usr/bin/env python3
"""Build deterministic lesson context for Hermes from cleaned Tamil dialogues."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


SCENARIO_KEYWORDS = {
    "greeting": ["hello", "hi", "vanakkam", "epdi", "how are", "name", "meet"],
    "social": ["friend", "weekend", "movie", "chat", "story", "bro", "machi"],
    "emotion": ["happy", "sad", "angry", "stress", "tired", "aiyyo", "feel"],
    "family": ["amma", "appa", "family", "sister", "brother", "partner"],
    "shopping": ["price", "shop", "buy", "sell", "discount", "cash", "bill"],
    "food": ["food", "sapdu", "saapdu", "tea", "coffee", "hungry", "taste"],
    "transport": ["bus", "train", "auto", "taxi", "ticket", "route", "ride"],
    "help": ["help", "please", "borrow", "explain", "clarify", "emergency"],
    "work": ["work", "office", "meeting", "deadline", "task", "colleague"],
    "service": ["hotel", "doctor", "repair", "service", "complain", "booking"],
    "conflict": ["poda", "podi", "dei", "problem", "fight", "angry", "stop"],
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_day_range(value: str) -> tuple[int, int]:
    start, end = value.split("-", 1)
    return int(start), int(end)


def determine_cycle_info(difficulty_data: dict, today: datetime) -> dict:
    day_of_cycle = min(365, int(today.strftime("%j")))
    curriculum = difficulty_data["curriculum"]
    round_id = "round_3"
    for candidate, config in curriculum.items():
        start, end = parse_day_range(config["days"])
        if start <= day_of_cycle <= end:
            round_id = candidate
            break
    config = curriculum[round_id]
    return {
        "day_of_cycle": day_of_cycle,
        "round_id": round_id,
        "round_name": round_id.replace("_", " ").title(),
        "target_levels": config["target_levels"],
        "focus": config["focus"],
        "description": config["description"],
    }


def dialogue_hash(dialogue: dict) -> str:
    payload = f"{dialogue.get('source_url', '')}|{dialogue.get('text', '')}".strip().lower()
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def scenario_score(dialogue: dict, scenario_id: str) -> int:
    haystack = f"{dialogue.get('text', '')} {dialogue.get('source_title', '')}".lower()
    score = 0
    for keyword in SCENARIO_KEYWORDS.get(scenario_id, []):
        if keyword in haystack:
            score += 2 if " " in keyword else 1
    if dialogue.get("candidate_type") == "dialogue_pair":
        score += 2
    return score


def level_window(difficulty_data: dict, target_levels: list[int]) -> tuple[int, int]:
    min_words: list[int] = []
    max_words: list[int] = []
    for level in target_levels:
        config = difficulty_data["difficulty_levels"][str(level)]
        min_words.append(config["sentence_words"][0])
        max_words.append(config["sentence_words"][1])
    return min(min_words), max(max_words)


def choose_scenario(
    cleaned_dialogues: list[dict],
    scenarios: list[dict],
    cache_hashes: set[str],
    target_window: tuple[int, int],
) -> tuple[dict, list[dict]]:
    candidates: list[tuple[float, dict, list[dict]]] = []
    min_words, max_words = target_window

    for scenario in scenarios:
        ranked: list[tuple[int, float, dict]] = []
        for dialogue in cleaned_dialogues:
            dialogue_id = dialogue["dialogue_id"]
            if dialogue_id in cache_hashes:
                continue
            word_count = dialogue.get("word_count", 0)
            if word_count < max(2, min_words - 1) or word_count > max_words + 6:
                continue
            score = scenario_score(dialogue, scenario["id"])
            if score <= 0 and dialogue.get("colloquial_score", 0) < 0.55:
                continue
            closeness = abs(word_count - ((min_words + max_words) / 2))
            ranked.append((score, -closeness, dialogue))

        ranked.sort(key=lambda item: (item[0], item[1], item[2]["colloquial_score"]), reverse=True)
        top_dialogues = [item[2] for item in ranked[:8]]
        effective_score = sum(max(1, item[0]) for item in ranked[:4]) + scenario.get("frequency_weight", 1)
        if top_dialogues:
            candidates.append((effective_score, scenario, top_dialogues))

    if not candidates:
        return scenarios[0], []

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_scenario, best_dialogues = candidates[0]
    if best_score <= 0:
        return scenarios[0], []
    return best_scenario, best_dialogues


def choose_subscenario(scenario: dict, day_of_cycle: int) -> dict:
    subscenarios = scenario.get("subscenarios", [])
    if not subscenarios:
        return {"id": "general", "desc": scenario.get("name", "General")}
    index = (day_of_cycle - 1) % len(subscenarios)
    return subscenarios[index]


def build_context(
    cleaned_data: dict,
    scenario_data: dict,
    difficulty_data: dict,
    cache_data: dict,
) -> dict:
    today = datetime.now().astimezone()
    cycle_info = determine_cycle_info(difficulty_data, today)
    cache_hashes = set(cache_data.get("dialogue_cache", {}).keys())
    target_window = level_window(difficulty_data, cycle_info["target_levels"])

    dialogues = []
    for dialogue in cleaned_data.get("dialogues", []):
        entry = dict(dialogue)
        entry["dialogue_id"] = dialogue_hash(entry)
        dialogues.append(entry)

    scenario, selected_dialogues = choose_scenario(
        dialogues,
        scenario_data.get("scenarios", []),
        cache_hashes,
        target_window,
    )
    subscenario = choose_subscenario(scenario, cycle_info["day_of_cycle"])

    insufficiency_reason = ""
    if len(selected_dialogues) < 3:
        insufficiency_reason = "Not enough high-quality dialogues for the selected day."

    return {
        "task_name": "tamil_colloquial_lesson_context",
        "generated_at": now_iso(),
        "cycle": cycle_info,
        "difficulty_window_words": {
            "min": target_window[0],
            "max": target_window[1],
        },
        "scenario": {
            "id": scenario["id"],
            "name": scenario["name"],
            "frequency_weight": scenario.get("frequency_weight", 1),
            "subscenario": subscenario,
        },
        "selected_dialogues_count": len(selected_dialogues),
        "selected_dialogues": selected_dialogues,
        "cache_candidate_hashes": [dialogue["dialogue_id"] for dialogue in selected_dialogues[:5]],
        "cache_stats": cache_data.get("stats", {}),
        "insufficient_data": len(selected_dialogues) < 3,
        "insufficiency_reason": insufficiency_reason,
        "generation_rules": {
            "must_keep_same_core_meaning": True,
            "must_ground_in_selected_dialogues": True,
            "minimum_colloquial_score": 0.5,
            "avoid_reusing_cached_dialogues": True,
        },
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Tamil lesson context JSON")
    parser.add_argument("--cleaned-dialogues", required=True)
    parser.add_argument("--scenarios-file", required=True)
    parser.add_argument("--difficulty-file", required=True)
    parser.add_argument("--cache-file", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    cleaned_data = load_json(args.cleaned_dialogues)
    scenario_data = load_json(args.scenarios_file)
    difficulty_data = load_json(args.difficulty_file)
    cache_data = load_json(args.cache_file)

    context = build_context(cleaned_data, scenario_data, difficulty_data, cache_data)
    output_file = Path(args.output_dir) / "tamil_lesson_context.json"
    write_json(output_file, context)
    print(str(output_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
