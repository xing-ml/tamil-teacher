#!/usr/bin/env python3
"""
LLM Evaluator - Evaluates lessons and provides feedback on classification accuracy.
Supports multiple LLM providers (OpenAI, Anthropic, etc).
"""

import os
import json
import sys
from typing import Dict, List, Optional
from pathlib import Path


class LLMEvaluator:
    """Base class for LLM-based evaluation."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.model = model or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    
    def evaluate_lesson(self,
                       lesson_data: Dict,
                       level: str,
                       vocabularies: Dict[str, List[str]]) -> Dict:
        """
        Evaluate a generated lesson.
        
        Args:
            lesson_data: Lesson content and metadata
            level: Difficulty level (L1-L6)
            vocabularies: Current vocabulary classifications
        
        Returns:
            Dict with evaluation results and suggestions
        """
        raise NotImplementedError("Subclasses must implement evaluate_lesson()")
    
    def suggest_vocabulary_improvements(self,
                                       misclassified_terms: List[str],
                                       vocabularies: Dict[str, List[str]]) -> Dict:
        """
        Get LLM suggestions for vocabulary reclassification.
        
        Args:
            misclassified_terms: Terms that may be incorrectly classified
            vocabularies: Current vocabulary classifications
        
        Returns:
            Dict with suggested changes
        """
        raise NotImplementedError("Subclasses must implement suggest_vocabulary_improvements()")


class MockLLMEvaluator(LLMEvaluator):
    """Mock evaluator for testing (doesn't require API key)."""
    
    def evaluate_lesson(self,
                       lesson_data: Dict,
                       level: str,
                       vocabularies: Dict[str, List[str]]) -> Dict:
        """Mock evaluation - returns dummy results."""
        
        entry_count = len(lesson_data.get("entries", []))
        avg_score = lesson_data.get("metadata", {}).get("avg_score", 0)
        
        return {
            "level": level,
            "evaluation": {
                "is_appropriate_difficulty": entry_count >= 2 and avg_score > 0.25,
                "appropriateness_score": min(avg_score * 2, 1.0),
                "lesson_quality": "good" if entry_count >= 3 else "fair",
                "context_coverage": "good" if entry_count > 5 else "fair",
            },
            "suggestions": [
                "Ensure lesson includes diverse sources for better context variety.",
                "Monitor colloquial score consistency across entries.",
                f"Level {level} has {entry_count} entries; aim for 5-10 for comprehensive coverage.",
            ],
            "vocabulary_issues": [],
            "provider": "mock",
        }
    
    def suggest_vocabulary_improvements(self,
                                       misclassified_terms: List[str],
                                       vocabularies: Dict[str, List[str]]) -> Dict:
        """Mock suggestions for vocabulary."""
        
        return {
            "provider": "mock",
            "suggestions": [
                "Review particle classification - ensure all markers are covered.",
                "Consider adding context-dependent slang terms.",
                "Verify aggressive term boundaries - some may be borderline.",
            ],
            "proposed_changes": {},
        }


class OpenAILLMEvaluator(LLMEvaluator):
    """OpenAI-based LLM evaluator."""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key, "gpt-3.5-turbo")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        try:
            import openai
            openai.api_key = self.api_key
            self.client = openai
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")
    
    def evaluate_lesson(self,
                       lesson_data: Dict,
                       level: str,
                       vocabularies: Dict[str, List[str]]) -> Dict:
        """Evaluate using OpenAI API."""
        
        entries_summary = "\n".join([
            f"- '{e.get('target_tanglish', '')[:60]}...' (score: {e.get('final_score', 0)})"
            for e in lesson_data.get("entries", [])[:5]
        ])
        
        prompt = f"""
You are a Tamil language expert evaluating a colloquial Tamil lesson.

Lesson Level: {level}
Entry Count: {len(lesson_data.get('entries', []))}
Average Colloquial Score: {lesson_data.get('metadata', {}).get('avg_score', 0)}

Sample Entries:
{entries_summary}

Current Vocabulary Classifications:
- BASIC_VOCAB: {len(vocabularies.get('BASIC_VOCAB', []))} terms
- PARTICLES: {len(vocabularies.get('PARTICLES', []))} terms
- SLANG: {len(vocabularies.get('SLANG', []))} terms
- AGGRESSIVE: {len(vocabularies.get('AGGRESSIVE', []))} terms

Please evaluate:
1. Is this lesson appropriate for its difficulty level?
2. Are the entries consistent with the Tamil colloquial style?
3. What are 2-3 specific suggestions for improvement?

Respond in JSON format:
{{
    "is_appropriate": true/false,
    "appropriateness_score": 0.0-1.0,
    "quality_feedback": "string",
    "suggestions": ["suggestion1", "suggestion2", "suggestion3"]
}}
"""
        
        try:
            response = self.client.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            
            result_text = response.choices[0].message.content
            result_json = json.loads(result_text)
            
            return {
                "level": level,
                "evaluation": result_json,
                "provider": "openai",
            }
        except Exception as e:
            print(f"ERROR OpenAI evaluation failed: {e}", file=sys.stderr)
            # Fallback to mock
            return MockLLMEvaluator().evaluate_lesson(lesson_data, level, vocabularies)
    
    def suggest_vocabulary_improvements(self,
                                       misclassified_terms: List[str],
                                       vocabularies: Dict[str, List[str]]) -> Dict:
        """Get vocabulary improvement suggestions from OpenAI."""
        
        prompt = f"""
You are a Tamil colloquial language expert. Review the following terms and their current classification:

Terms to Review: {', '.join(misclassified_terms[:10])}

Current Classifications:
- BASIC_VOCAB: {', '.join(vocabularies.get('BASIC_VOCAB', [])[:10])}...
- PARTICLES: {', '.join(vocabularies.get('PARTICLES', [])[:10])}...
- SLANG: {', '.join(vocabularies.get('SLANG', [])[:10])}...
- AGGRESSIVE: {', '.join(vocabularies.get('AGGRESSIVE', [])[:10])}...

For each term, suggest:
1. Is the current classification correct?
2. Should it be moved to a different category?
3. Any new terms that should be added?

Respond in JSON:
{{
    "term_reviews": {{"term": "current_category or suggested_change"}},
    "new_terms_to_add": {{"category": ["term1", "term2"]}},
    "categories_needing_expansion": ["category1", "category2"]
}}
"""
        
        try:
            response = self.client.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            
            result_text = response.choices[0].message.content
            result_json = json.loads(result_text)
            
            return {
                "provider": "openai",
                "suggestions": result_json,
            }
        except Exception as e:
            print(f"ERROR OpenAI vocabulary suggestion failed: {e}", file=sys.stderr)
            return MockLLMEvaluator().suggest_vocabulary_improvements(misclassified_terms, vocabularies)


def get_evaluator(provider: str = "mock") -> LLMEvaluator:
    """
    Factory function to get appropriate LLM evaluator.
    
    Args:
        provider: "mock", "openai", "anthropic", etc
    
    Returns:
        LLMEvaluator instance
    """
    if provider == "mock":
        return MockLLMEvaluator()
    elif provider == "openai":
        return OpenAILLMEvaluator()
    else:
        print(f"WARNING Unknown provider '{provider}', using mock", file=sys.stderr)
        return MockLLMEvaluator()
