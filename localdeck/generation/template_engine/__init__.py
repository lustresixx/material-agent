"""Template-frame matching and editable source-deck generation."""

from localdeck.generation.template_engine.matcher import (
    FrameMatchDecision,
    FrameMatchMap,
    ReuseMode,
    match_plan,
)

__all__ = ["FrameMatchDecision", "FrameMatchMap", "ReuseMode", "match_plan"]
