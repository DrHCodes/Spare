"""Conversational effort calibration. Scores are preferences, NOT measured exertion."""
from __future__ import annotations
from dataclasses import dataclass
import math
import re

@dataclass(frozen=True)
class Effort:
    score: float
    raw: str
    anchor: str
    confidence: float
    needs_confirmation: bool
    capped: bool = False

    def public(self):
        return {'target_effort': self.score, 'source': self.raw, 'anchor': self.anchor,
                'confidence': self.confidence, 'needs_confirmation': self.needs_confirmation,
                'capped': self.capped, 'measured': False}


def interpret_effort(text: str, proposed_score: float | None = None,
                     confidence: float = 0.0, confirmed: bool = False) -> Effort:
    """Known anchors are deterministic; an LLM may propose others, with user confirmation.
    'Medium = Lagree-like' is this user's personal reference. No clinical equivalence.
    'Push-ups all the time' maps effort only, not exercise prescription.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 600:
        raise ValueError('Provide a short effort description.')
    t = text.lower().strip()
    # Only map a reference automatically when the user did not qualify/negate it.
    qualified = bool(re.search(r'\b(not|less|more|than|but|avoid|dont|don.t)\b', t))
    score = None; anchor = 'interpreted preference'; conf = confidence
    numeric = re.search(r'\b(10|[0-9](?:\.[0-9])?)\s*(?:/\s*10|out of (?:10|ten))\b', t)
    if numeric:
        score = float(numeric.group(1)); anchor = 'user-stated target'; conf = 1.0
    elif not qualified and re.search(r'\b(lagree|megaformer)\b', t):
        score = 6.0; anchor = 'your Lagree-like medium reference'; conf = .8
    elif not qualified and re.search(r'\b(easy|gentle|light|chill)\b', t):
        score = 3.0; anchor = 'easy'; conf = .9
    elif not qualified and re.search(r'\b(medium|moderate)\b', t):
        score = 6.0; anchor = 'medium'; conf = .9
    elif not qualified and re.search(r'\b(hard|difficult|intense)\b|fast push.?ups', t):
        score = 8.0; anchor = 'high effort, with recovery'; conf = .85
    elif proposed_score is not None:
        if isinstance(proposed_score, bool) or not isinstance(proposed_score, (int,float)) or not math.isfinite(proposed_score) or not 0 <= proposed_score <= 10:
            raise ValueError('Target effort must be between 0 and 10.')
        score = float(proposed_score)
    if score is None:
        raise ValueError('Ask what effort the user intends, or propose a score and confirm it.')
    if not isinstance(conf, (int,float)) or not math.isfinite(conf) or not 0 <= conf <= 1:
        raise ValueError('Confidence must be between 0 and 1.')
    capped = score > 8 or score < 1
    score = max(1., min(8., score))
    # Every first target requires a spoken confirmation; a model cannot declare accuracy.
    return Effort(score, text.strip(), anchor, float(conf), not confirmed, capped)
