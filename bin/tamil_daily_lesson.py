#!/usr/bin/env python3
"""Run the Tamil daily lesson preprocessing pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_step(command: list[str], label: str) -> str:
    print(f"INFO {label}...", file=sys.stderr)
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")
    stdout = completed.stdout.strip().splitlines()
    if not stdout:
        raise RuntimeError(f"{label} did not produce an output path")
    return stdout[-1].strip()


def main() -> int:
    script_path = Path(__file__).resolve()
    project_dir = script_path.parent.parent
    temp_dir = project_dir / "temp"
    data_dir = project_dir / "data"
    collector_dir = project_dir / "collector"
    python_bin = sys.executable

    temp_dir.mkdir(parents=True, exist_ok=True)

    collector_output = run_step(
        [
            python_bin,
            str(collector_dir / "tamil_colloquial_collector.py"),
            "--output-dir",
            str(temp_dir),
            "--ddgs-queries",
            "tamil colloquial conversation",
            "அன்றாட தமிழ் பேச்சு",
            "tamil slang phrases",
            "tamil casual dialogue forum",
            "tamil street interview",
            "--youtube-queries",
            "tamil movie dialogue collection",
            "tamil vlog daily life",
            "tamil comedy scene",
            "tamil conversation video",
            "--youtube-max-per-query",
            "10",
        ],
        "Collecting source data (YouTube-focused)",
    )

    cleaned_output = run_step(
        [
            python_bin,
            str(collector_dir / "tamil_cleaner.py"),
            "--agent-input",
            collector_output,
            "--keywords-file",
            str(data_dir / "tamil_keywords.json"),
            "--output-dir",
            str(temp_dir),
            "--min-colloquial-score",
            "0.3",
        ],
        "Cleaning dialogue data",
    )

    context_output = run_step(
        [
            python_bin,
            str(collector_dir / "tamil_lesson_context_builder.py"),
            "--cleaned-dialogues",
            cleaned_output,
            "--scenarios-file",
            str(data_dir / "scenario_definitions.json"),
            "--difficulty-file",
            str(data_dir / "difficulty_levels.json"),
            "--cache-file",
            str(data_dir / "cache" / "dialogue_cache.json"),
            "--output-dir",
            str(temp_dir),
        ],
        "Building lesson context",
    )

    # Add to corpus and generate lessons
    corpus_output = run_step(
        [
            python_bin,
            str(collector_dir / "tamil_corpus_manager.py"),
            "--corpus-dir",
            str(data_dir / "corpus"),
            "--add-cleaned",
            cleaned_output,
            "--generate-lessons",
        ],
        "Adding to corpus and generating lessons",
    )

    context = json.loads(Path(context_output).read_text(encoding="utf-8"))
    print(
        "INFO Final output files:"
        f"\n  - Agent input: {collector_output}"
        f"\n  - Cleaned dialogues: {cleaned_output}"
        f"\n  - Lesson context: {context_output}"
        f"\n  - Selected dialogues: {context.get('selected_dialogues_count', 0)}",
        file=sys.stderr,
    )
    print(context_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
