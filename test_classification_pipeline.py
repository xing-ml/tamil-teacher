#!/usr/bin/env python3
"""
Integration test for Tamil classification pipeline.
Tests: classifier → context extractor → LLM evaluator
"""

import json
import sys
from pathlib import Path

# Add collector to path
sys.path.insert(0, str(Path(__file__).parent / "collector"))

from tamil_linguistic_classifier import TamilLinguisticClassifier
from tamil_context_extractor import TamilContextExtractor
from llm_evaluator import get_evaluator


def test_classification_pipeline():
    """Test the complete classification pipeline."""
    
    print("\n" + "="*70)
    print("🧪 Testing Tamil Classification Pipeline")
    print("="*70)
    
    # Sample Tamil utterances (Tanglish)
    sample_utterances = [
        "hello seri enna irukku",  # Basic greeting
        "nee enna panren",  # What are you doing?
        "apram oru mass scene",  # Then some cool scene
        "dei dei poda loosu",  # Aggressive expression
        "theriyum theriyum seri seri",  # Understanding repeated
        "kolaveri kolaveri semma mass",  # Slang heavy
        "namma enga ponitu ellam polambitu vendam",  # Complex sentence
        "molaga molaga poda dei",  # Colloquial with particles
    ]
    
    # Step 1: Classify utterances
    print("\n📊 STEP 1: Classifying Utterances")
    print("-" * 70)
    
    classifier = TamilLinguisticClassifier()
    classifications = {}
    
    for idx, utterance in enumerate(sample_utterances):
        result = classifier.classify(utterance)
        classifications[idx] = {
            "text": result.text,
            "level": result.level,
            "linguistic_score": result.linguistic_score,
            "pragmatic_score": result.pragmatic_score,
            "final_score": result.final_score,
            "features": result.features,
        }
        
        print(f"\n{idx+1}. '{utterance}'")
        print(f"   Level: {result.level} | Score: {result.final_score}")
        print(f"   Ling: {result.linguistic_score} | Prag: {result.pragmatic_score}")
        print(f"   Features: {result.features}")
    
    # Step 2: Extract contexts
    print("\n\n📍 STEP 2: Extracting Context (prev 2 + target + next 2)")
    print("-" * 70)
    
    extractor = TamilContextExtractor()
    contexts = extractor.extract_contexts(sample_utterances, classifications)
    
    for ctx in contexts[:3]:  # Show first 3 contexts
        print(f"\n➤ Level {ctx.level}: '{ctx.target_text}'")
        print(f"  Preceding: {ctx.preceding_2}")
        print(f"  Following: {ctx.following_2}")
    
    # Step 3: Save contexts by level
    print("\n\n💾 STEP 3: Saving Contexts by Level")
    print("-" * 70)
    
    output_dir = Path(__file__).parent / "data" / "intermediate"
    counts = extractor.save_contexts_by_level(contexts, output_dir)
    
    print("\nContexts saved by level:")
    for level, count in sorted(counts.items()):
        print(f"  {level}: {count} utterances")
    
    # Step 4: Get level summary
    summary = extractor.get_level_summary(output_dir)
    print("\nLevel summary:")
    for level, data in sorted(summary.items()):
        print(f"  {level}: {data['count']} total entries")
    
    # Step 5: LLM Evaluation (using mock)
    print("\n\n🤖 STEP 5: LLM Evaluation (Mock Provider)")
    print("-" * 70)
    
    evaluator = get_evaluator("mock")
    vocabularies = classifier.get_vocabularies()
    
    # Create mock lesson data
    lesson_data = {
        "level": "L2",
        "entries": contexts[:3],
        "metadata": {"avg_score": 0.45},
    }
    
    evaluation = evaluator.evaluate_lesson(lesson_data, "L2", vocabularies)
    print(f"\nEvaluation Results:")
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    
    # Step 6: Vocabulary suggestions
    vocab_suggestions = evaluator.suggest_vocabulary_improvements(
        ["loosu", "mass", "scene"],
        vocabularies
    )
    print(f"\nVocabulary Improvement Suggestions:")
    print(json.dumps(vocab_suggestions, ensure_ascii=False, indent=2))
    
    print("\n" + "="*70)
    print("✅ Pipeline test completed successfully!")
    print("="*70 + "\n")


if __name__ == "__main__":
    test_classification_pipeline()
