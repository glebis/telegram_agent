"""
Transcript Corrector Service (#12)

Applies vocabulary corrections and filler word removal to transcripts.
Supports configurable correction levels.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default corrections file location
DEFAULT_CORRECTIONS_FILE = Path(__file__).parent.parent.parent / "config" / "corrections_map.json"

# Filler words to remove (English and Russian)
FILLER_WORDS_EN = [
    r"\bum\b",
    r"\buh\b",
    r"\blike\b(?=\s+(?:I|you|he|she|it|we|they|so|um|uh))",  # Only "like" as filler
    r"\byou know\b",
    r"\bI mean\b",
    r"\bso\b(?=\s*,)",  # "so," at start
    r"\bactually\b(?=\s*,)",
    r"\bbasically\b(?=\s*,)",
]

FILLER_WORDS_RU = [
    r"\bэээ+\b",
    r"\bммм+\b",
    r"\bаааа+\b",
    r"\bну\b(?=\s*,)",  # "ну," as filler
    r"\bвот\b(?=\s*,)",  # "вот," as filler
    r"\bзначит\b(?=\s*,)",
    r"\bкороче\b(?=\s*,)",
    r"\bтипа\b",
    r"\bкак бы\b",
    r"\bтак сказать\b",
]


class TranscriptCorrector:
    """
    Service for correcting transcripts with vocabulary fixes and filler removal.

    Correction levels:
    - "none": No corrections, return original text
    - "vocabulary": Only apply vocabulary corrections (term fixes)
    - "full": Apply vocabulary + filler word removal
    """

    # Terms to skip - too short or ambiguous
    SKIP_TERMS = {
        'ai', 'ml', 'db', 'ui', 'ux', 'id', 'os', 'ip', 'io',
        'a', 'i', 'to', 'is', 'it', 'in', 'on', 'or', 'an',
        'время', 'time', 'llm', 'lmm', 'api', 'url', 'css', 'html',
        'пол', 'все', 'мы', 'вы', 'он', 'она', 'это', 'как', 'что',
    }

    def __init__(self, corrections_file: Path = DEFAULT_CORRECTIONS_FILE):
        """
        Initialize the corrector.

        Args:
            corrections_file: Path to JSON file with term corrections
        """
        self.corrections: Dict[str, str] = {}
        self.pattern: Optional[re.Pattern] = None
        self.filler_pattern: Optional[re.Pattern] = None

        self._load_corrections(corrections_file)
        self._build_filler_pattern()

    def _load_corrections(self, corrections_file: Path) -> None:
        """Load corrections from JSON file."""
        if not corrections_file.exists():
            logger.warning(f"Corrections file not found: {corrections_file}")
            return

        try:
            with open(corrections_file, 'r', encoding='utf-8') as f:
                raw_corrections = json.load(f)

            # Filter out problematic short terms
            self.corrections = {
                k.lower(): v for k, v in raw_corrections.items()
                if k.lower() not in self.SKIP_TERMS and len(k) >= 3
            }

            self._build_correction_pattern()
            logger.info(f"Loaded {len(self.corrections)} correction rules")

        except Exception as e:
            logger.error(f"Failed to load corrections: {e}")

    def _build_correction_pattern(self) -> None:
        """Build regex pattern for vocabulary corrections."""
        if not self.corrections:
            return

        # Sort by length (longest first) to avoid partial matches
        sorted_terms = sorted(self.corrections.keys(), key=len, reverse=True)

        # Escape special regex chars
        escaped = [re.escape(term) for term in sorted_terms]
        pattern_str = '|'.join(escaped)

        # Word boundary pattern supporting Cyrillic
        word_char = r'a-zA-Z0-9а-яА-ЯёЁ'
        self.pattern = re.compile(
            rf'(?<![{word_char}])({pattern_str})(?![{word_char}])',
            re.IGNORECASE
        )

    def _build_filler_pattern(self) -> None:
        """Build regex pattern for filler word removal."""
        all_fillers = FILLER_WORDS_EN + FILLER_WORDS_RU
        if all_fillers:
            self.filler_pattern = re.compile(
                '|'.join(all_fillers),
                re.IGNORECASE
            )

    def correct_text(
        self,
        text: str,
        level: str = "vocabulary",
        remove_fillers: bool = False,
    ) -> str:
        """
        Apply corrections to text.

        Args:
            text: Input text to correct
            level: Correction level ("none", "vocabulary", "full")
            remove_fillers: Whether to remove filler words (overrides level)

        Returns:
            Corrected text
        """
        if not text:
            return text

        if level == "none":
            return text

        result = text

        # Apply vocabulary corrections
        if level in ("vocabulary", "full") and self.pattern:
            result = self._apply_vocabulary_corrections(result)

        # Apply filler removal
        should_remove_fillers = remove_fillers or level == "full"
        if should_remove_fillers and self.filler_pattern:
            result = self._remove_fillers(result)

        return result

    def correct_text_with_stats(
        self,
        text: str,
        level: str = "vocabulary",
    ) -> Tuple[str, Dict]:
        """
        Apply corrections and return statistics.

        Args:
            text: Input text to correct
            level: Correction level

        Returns:
            Tuple of (corrected_text, stats_dict)
        """
        if not text or level == "none":
            return text, {"corrections_count": 0, "terms_corrected": []}

        terms_corrected = []

        def replace_with_tracking(match):
            term = match.group(1)
            term_lower = term.lower()
            if term_lower in self.corrections:
                terms_corrected.append({
                    "original": term,
                    "corrected": self.corrections[term_lower]
                })
                return self.corrections[term_lower]
            return term

        result = text
        if self.pattern:
            result = self.pattern.sub(replace_with_tracking, result)

        if level == "full" and self.filler_pattern:
            result = self._remove_fillers(result)

        stats = {
            "corrections_count": len(terms_corrected),
            "terms_corrected": terms_corrected,
        }

        return result, stats

    def _apply_vocabulary_corrections(self, text: str) -> str:
        """Apply vocabulary corrections to text."""
        if not self.pattern:
            return text

        def replace(match):
            term = match.group(1)
            term_lower = term.lower()
            if term_lower in self.corrections:
                return self.corrections[term_lower]
            return term

        return self.pattern.sub(replace, text)

    def _remove_fillers(self, text: str) -> str:
        """Remove filler words from text."""
        if not self.filler_pattern:
            return text

        # Remove fillers
        result = self.filler_pattern.sub('', text)

        # Clean up extra spaces
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'\s+,', ',', result)
        result = re.sub(r',\s*,', ',', result)

        return result.strip()

    def get_correction_count(self) -> int:
        """Get number of loaded correction rules."""
        return len(self.corrections)


# Global singleton
_transcript_corrector: Optional[TranscriptCorrector] = None


def get_transcript_corrector() -> TranscriptCorrector:
    """Get the transcript corrector singleton."""
    global _transcript_corrector
    if _transcript_corrector is None:
        _transcript_corrector = TranscriptCorrector()
    return _transcript_corrector
