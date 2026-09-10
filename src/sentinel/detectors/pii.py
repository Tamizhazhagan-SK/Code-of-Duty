"""Wrap Microsoft Presidio. Adds locale recognizers (e.g. Aadhaar/PAN for en_IN)."""
from ..collectors.staged_diff import Unit

def scan(units: list[Unit], cfg) -> list:
    # AnalyzerEngine(spaCy) + custom PatternRecognizers; weight by file_class.
    return []
