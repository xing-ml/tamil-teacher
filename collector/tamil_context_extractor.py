#!/usr/bin/env python3
"""
Tamil Context Extractor - Extracts surrounding context for classified utterances.
For each classified utterance, extracts preceding 2 and following 2 utterances.
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional


@dataclass
class ContextualUtterance:
    """A classified utterance with surrounding context."""
    utterance_id: str
    level: str
    target_text: str
    target_tanglish: str
    preceding_2: List[str]  # Previous 2 utterances (tanglish)
    following_2: List[str]  # Next 2 utterances (tanglish)
    linguistic_score: float
    pragmatic_score: float
    final_score: float


class TamilContextExtractor:
    """Extracts context windows for classified utterances."""
    
    def __init__(self):
        pass
    
    def extract_contexts(self, 
                        utterances: List[str],
                        classifications: Dict[int, Dict],
                        min_level: str = "L1") -> List[ContextualUtterance]:
        """
        Extract context for all classified utterances.
        
        Args:
            utterances: List of tanglish utterances
            classifications: Dict mapping utterance index to classification result
            min_level: Minimum level to include (default all levels)
        
        Returns:
            List of ContextualUtterance objects
        """
        contexts = []
        
        for idx, classification in classifications.items():
            # Skip if index out of bounds
            if idx < 0 or idx >= len(utterances):
                continue
            
            # Extract preceding 2 (go back max 2, but allow fewer)
            preceding = []
            for i in range(max(0, idx - 2), idx):
                if i >= 0 and i < len(utterances):
                    preceding.append(utterances[i])
            # Pad to exactly 2 if needed
            while len(preceding) < 2:
                preceding.insert(0, "[START]")
            
            # Extract following 2 (go forward max 2, but allow fewer)
            following = []
            for i in range(idx + 1, min(len(utterances), idx + 3)):
                if i < len(utterances):
                    following.append(utterances[i])
            # Pad to exactly 2 if needed
            while len(following) < 2:
                following.append("[END]")
            
            # Create context object
            context = ContextualUtterance(
                utterance_id=self._generate_id(utterances[idx]),
                level=classification.get("level", "UNKNOWN"),
                target_text=utterances[idx],
                target_tanglish=utterances[idx],
                preceding_2=preceding,
                following_2=following,
                linguistic_score=classification.get("linguistic_score", 0),
                pragmatic_score=classification.get("pragmatic_score", 0),
                final_score=classification.get("final_score", 0),
            )
            
            contexts.append(context)
        
        return contexts
    
    def _generate_id(self, text: str) -> str:
        """Generate unique ID for an utterance."""
        return hashlib.sha1(text.encode()).hexdigest()[:12]
    
    def save_contexts_by_level(self, contexts: List[ContextualUtterance], output_dir: Path) -> Dict[str, int]:
        """
        Save contexts grouped by difficulty level.
        
        Args:
            contexts: List of ContextualUtterance objects
            output_dir: Output directory path
        
        Returns:
            Dict mapping level → count saved
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Group by level
        by_level = {}
        for context in contexts:
            if context.level not in by_level:
                by_level[context.level] = []
            by_level[context.level].append(context)
        
        # Save each level
        counts = {}
        for level in sorted(by_level.keys()):
            level_dir = output_dir / level
            level_dir.mkdir(exist_ok=True)
            
            utterances_file = level_dir / "utterances.json"
            
            # Load existing data if present
            existing_data = []
            if utterances_file.exists():
                try:
                    existing_data = json.loads(utterances_file.read_text(encoding="utf-8"))
                except:
                    existing_data = []
            
            # Add new utterances
            for context in by_level[level]:
                existing_data.append(asdict(context))
            
            # Save
            utterances_file.write_text(
                json.dumps(existing_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            
            counts[level] = len(by_level[level])
        
        return counts
    
    def get_level_summary(self, output_dir: Path) -> Dict[str, Dict]:
        """
        Get summary of contexts by level.
        
        Returns:
            Dict: {level: {count: int, sample_utterance: str}}
        """
        output_dir = Path(output_dir)
        summary = {}
        
        for level_dir in sorted(output_dir.glob("L*")):
            if level_dir.is_dir():
                level = level_dir.name
                utterances_file = level_dir / "utterances.json"
                
                if utterances_file.exists():
                    try:
                        data = json.loads(utterances_file.read_text(encoding="utf-8"))
                        summary[level] = {
                            "count": len(data),
                            "sample": data[0]["target_tanglish"] if data else None
                        }
                    except:
                        summary[level] = {"count": 0, "sample": None}
        
        return summary
