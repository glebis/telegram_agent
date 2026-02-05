"""
Tests for TranscriptCorrector service (#12).

Tests cover:
- Vocabulary corrections (corrections_map.json)
- Filler word removal
- Full transcript output (no cropping)
- Correction levels configuration
"""

from pathlib import Path

# =============================================================================
# Test: TranscriptCorrector Service
# =============================================================================


class TestTranscriptCorrectorExists:
    """Test that TranscriptCorrector service exists."""

    def test_transcript_corrector_class_exists(self):
        """TranscriptCorrector class should exist."""
        from src.services.transcript_corrector import TranscriptCorrector

        assert TranscriptCorrector is not None

    def test_transcript_corrector_has_correct_text_method(self):
        """TranscriptCorrector should have correct_text method."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()
        assert hasattr(corrector, "correct_text")
        assert callable(corrector.correct_text)


class TestVocabularyCorrections:
    """Test vocabulary-based corrections."""

    def test_corrects_claude_code_variants(self):
        """Should correct various Claude Code misspellings."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        # Test various misspellings
        test_cases = [
            ("я использую кладкод", "я использую Claude code"),
            ("открой клоткод", "открой Claude code"),
            ("cloth code помоги", "Claude code помоги"),
        ]

        for input_text, expected in test_cases:
            result = corrector.correct_text(input_text)
            assert "Claude code" in result, f"Failed for: {input_text}"

    def test_corrects_obsidian_variants(self):
        """Should correct Obsidian misspellings."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        result = corrector.correct_text("сохрани в обсидиан")
        assert "Obsidian" in result

    def test_corrects_n8n_variants(self):
        """Should correct n8n misspellings."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        result = corrector.correct_text("настрой na10 workflow")
        assert "n8n" in result

    def test_preserves_correct_terms(self):
        """Should not change already correct terms."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "Claude code and Obsidian work great"
        result = corrector.correct_text(text)
        assert result == text

    def test_case_insensitive_matching(self):
        """Should match terms regardless of case."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        result = corrector.correct_text("КЛАДКОД помоги")
        assert "Claude code" in result


class TestFillerWordRemoval:
    """Test filler word removal."""

    def test_removes_um_uh_fillers(self):
        """Should remove um, uh, and similar fillers."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "So um I was thinking uh about this"
        result = corrector.correct_text(text, remove_fillers=True)

        assert "um" not in result.lower()
        assert "uh" not in result.lower()
        assert "thinking" in result
        assert "about" in result

    def test_removes_russian_fillers(self):
        """Should remove Russian filler words."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "Ну вот значит я думаю эээ что это"
        result = corrector.correct_text(text, remove_fillers=True)

        # Common Russian fillers: ну, вот, значит, эээ, ммм
        assert "эээ" not in result

    def test_filler_removal_optional(self):
        """Filler removal should be optional (default off)."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "So um I was thinking"
        result_without = corrector.correct_text(text, remove_fillers=False)
        result_with = corrector.correct_text(text, remove_fillers=True)

        assert "um" in result_without
        assert "um" not in result_with


class TestCorrectionLevels:
    """Test configurable correction levels."""

    def test_level_none_returns_original(self):
        """Level 'none' should return original text."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "кладкод um помоги"
        result = corrector.correct_text(text, level="none")
        assert result == text

    def test_level_vocabulary_only(self):
        """Level 'vocabulary' should only fix term corrections."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "кладкод um помоги"
        result = corrector.correct_text(text, level="vocabulary")

        assert "Claude code" in result
        assert "um" in result  # Fillers kept

    def test_level_full_applies_all(self):
        """Level 'full' should apply all corrections."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "кладкод um помоги"
        result = corrector.correct_text(text, level="full")

        assert "Claude code" in result
        assert "um" not in result  # Fillers removed


class TestFullTranscriptOutput:
    """Test that full transcript is returned (no cropping)."""

    def test_long_text_not_cropped(self):
        """Long transcripts should not be cropped."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        # Create a long text
        long_text = "This is a test sentence. " * 100
        result = corrector.correct_text(long_text)

        assert len(result) == len(long_text)
        assert result.count("sentence") == 100

    def test_multiline_preserved(self):
        """Multi-line transcripts should be preserved."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "Line 1\nLine 2\nLine 3"
        result = corrector.correct_text(text)

        assert result.count("\n") == 2


class TestCorrectionStats:
    """Test correction statistics."""

    def test_returns_correction_count(self):
        """Should return number of corrections made."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "кладкод и обсидиан"
        result, stats = corrector.correct_text_with_stats(text)

        assert "corrections_count" in stats
        assert stats["corrections_count"] >= 2

    def test_returns_terms_corrected(self):
        """Should return list of corrected terms."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        text = "кладкод помоги"
        result, stats = corrector.correct_text_with_stats(text)

        assert "terms_corrected" in stats
        assert len(stats["terms_corrected"]) > 0


class TestCorrectionsMapLoading:
    """Test loading corrections from JSON file."""

    def test_loads_corrections_from_file(self):
        """Should load corrections from corrections_map.json."""
        from src.services.transcript_corrector import TranscriptCorrector

        corrector = TranscriptCorrector()

        # Should have loaded corrections
        assert len(corrector.corrections) > 0

    def test_handles_missing_file_gracefully(self):
        """Should handle missing corrections file gracefully."""
        from src.services.transcript_corrector import TranscriptCorrector

        # Should not raise, just have empty corrections
        corrector = TranscriptCorrector(corrections_file=Path("/nonexistent/file.json"))
        assert corrector.corrections == {}
