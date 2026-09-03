"""Structured input contracts for LocalDeck generation."""

from localdeck.inputs.models import OutlineChapter, OutlineDocument
from localdeck.inputs.normalizer import normalize_outline_payload

__all__ = ["OutlineChapter", "OutlineDocument", "normalize_outline_payload"]
