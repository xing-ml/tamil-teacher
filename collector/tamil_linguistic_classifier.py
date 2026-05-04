#!/usr/bin/env python3
"""
Tamil Linguistic Classifier - Classifies Tamil colloquial utterances by difficulty level.
Uses Tanglish (Tamil in English script) for analysis.
"""

from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class ClassificationResult:
    """Result of classifying a single utterance."""
    text: str
    tokens: List[str]
    linguistic_score: float
    pragmatic_score: float
    final_score: float
    level: str
    features: Dict[str, int]  # {feature_type: count}


class TamilLinguisticClassifier:
    """Classifies Tamil utterances using linguistic and pragmatic features."""
    
    def __init__(self):
        self.basic_vocab = self._load_basic_vocab()
        self.particles = self._load_particles()
        self.slang = self._load_slang()
        self.aggressive = self._load_aggressive()
    
    def _load_basic_vocab(self) -> Set[str]:
        """Load basic Tamil vocabulary."""
        return {
            "enna", "epdi", "eppadi", "enga", "yen",
            "ippo", "apram", "seri", "illa", "irukku",
            "naan", "nee", "avan", "aval", "namma", "unga", "enga",
            "idhu", "adhu", "inga", "anga",
            "sapdu", "saptiya", "sapdra", "sapdringa",
            "pannu", "panra", "pannen", "panrom",
            "varra", "varen", "vandha", "vandhen",
            "pora", "poren", "poita", "poitu",
            "irukku", "iruken", "iruka", "irukaanga",
            "theriyum", "theriyala",
            "paathu", "paakra", "paatha",
            "keka", "kekren", "kettan",
            "solra", "solren", "sonna", "sonnen",
            "eduthu", "edutha",
            "vechu", "vechitu",
            "kooda", "mela", "keela", "pakka",
            "innikku", "nethu", "naalaiku",
            "yaar", "yaru",
            "venum", "venuma", "vendam",
            "mudiyum", "mudiyala",
            "pannunga", "kudunga", "irunga",
            "start", "stop", "wait"
        }
    
    def _load_particles(self) -> Set[str]:
        """Load Tamil particles."""
        return {
            "da", "dei", "di", "pa", "ma", "ya", "la", "le", "lo", "yo", "eh", "hey", "oi"
        }
    
    def _load_slang(self) -> Set[str]:
        """Load Tamil slang terms."""
        return {
            "semma", "mass", "mokka", "scene", "figure", "jollu", "matter",
            "gethu", "kethu", "summa", "build", "over",
            "feeling", "crush", "local", "pullingo",
            "set", "group", "drama", "acting", "waste", "dummy", "loosu", "mental",
            "killadi", "sappa", "kasmalam", "peter", "bongu", "pistha",
            "kolaveri", "aapu", "bulb", "sothappal", "vetti"
        }
    
    def _load_aggressive(self) -> Set[str]:
        """Load aggressive/strong terms."""
        return {
            "poda", "podi", "dei", "da", "di",
            "loosu", "mental", "dummy", "idiot", "madaya",
            "waste", "useless", "nonsense",
            "payale", "payal", "paiyan",
            "kirukku", "kirukkan", "kirukki", "peithyam", "pey",
            "saniyan", "rowdy", "thirudan", "moodu", "mooditu",
            "setha", "sethan", "kedukkaravan", "thiruttu"
        }
    
    def compute_linguistic_score(self, tokens: List[str]) -> float:
        """
        Compute linguistic complexity score.
        Higher = more complex vocabulary, longer utterance.
        """
        score = 0.0
        
        # Token count contribution (max 5 points for 5+ tokens)
        score += min(len(tokens), 5)
        
        # Rare word count (words NOT in basic vocab)
        rare_count = sum(1 for t in tokens if t.lower() not in self.basic_vocab)
        score += min(rare_count, 4)
        
        return score
    
    def compute_pragmatic_score(self, tokens: List[str]) -> float:
        """
        Compute pragmatic/stylistic score.
        Based on presence of particles, slang, and aggressive language.
        """
        score = 0.0
        tokens_lower = [t.lower() for t in tokens]
        
        # Particles: +1 point
        if any(t in self.particles for t in tokens_lower):
            score += 1.0
        
        # Slang: +1 point
        if any(t in self.slang for t in tokens_lower):
            score += 1.0
        
        # Aggressive: +1 point (not 2)
        if any(t in self.aggressive for t in tokens_lower):
            score += 1.0
        
        return score
    
    def map_level(self, final_score: float) -> str:
        """Map numerical score to difficulty level."""
        if final_score <= 1.5:
            return "L1"
        elif final_score <= 2.8:
            return "L2"
        elif final_score <= 4.2:
            return "L3"
        elif final_score <= 5.8:
            return "L4"
        elif final_score <= 7.8:
            return "L5"
        else:
            return "L6"
    
    def classify(self, text: str) -> ClassificationResult:
        """
        Classify a single Tamil utterance.
        
        Returns:
            ClassificationResult with linguistic score, pragmatic score, final score, and level
        """
        # Tokenize (simple space-based split, can be improved with proper Tamil tokenizer)
        tokens = text.lower().split()
        
        # Compute component scores
        ling_score = self.compute_linguistic_score(tokens)
        prag_score = self.compute_pragmatic_score(tokens)
        
        # Weighted combination: 75% linguistic, 25% pragmatic
        final_score = 0.75 * ling_score + 0.25 * prag_score
        
        # Map to level
        level = self.map_level(final_score)
        
        # Track features
        features = {
            "token_count": len(tokens),
            "rare_words": sum(1 for t in tokens if t not in self.basic_vocab),
            "has_particles": 1 if any(t in self.particles for t in tokens) else 0,
            "has_slang": 1 if any(t in self.slang for t in tokens) else 0,
            "has_aggressive": 1 if any(t in self.aggressive for t in tokens) else 0,
        }
        
        return ClassificationResult(
            text=text,
            tokens=tokens,
            linguistic_score=round(ling_score, 2),
            pragmatic_score=round(prag_score, 2),
            final_score=round(final_score, 2),
            level=level,
            features=features
        )
    
    def get_vocabularies(self) -> Dict[str, List[str]]:
        """Return all vocabularies for LLM review."""
        return {
            "BASIC_VOCAB": sorted(list(self.basic_vocab)),
            "PARTICLES": sorted(list(self.particles)),
            "SLANG": sorted(list(self.slang)),
            "AGGRESSIVE": sorted(list(self.aggressive)),
        }
