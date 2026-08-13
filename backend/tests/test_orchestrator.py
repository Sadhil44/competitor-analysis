"""Tests for orchestrator.py's pure helper functions.

_extract_text is a regression test for a real bug: claude-sonnet-5 runs
adaptive thinking by default, so AIMessage.content is normally a list of
content blocks (thinking + text), not a plain string. orchestrator.py
originally assumed it was always a string and every real (thinking-enabled)
response crashed the /agent/ask endpoint with a Pydantic validation error.
"""

from app.agent.orchestrator import OrchestratorState, _extract_text, _route_selector


class TestExtractText:
    def test_plain_string_passthrough(self):
        # A model response with thinking disabled is still a plain string —
        # this path has to keep working too.
        assert _extract_text("just an answer") == "just an answer"

    def test_extracts_text_block_from_thinking_response(self):
        content = [
            {"type": "thinking", "thinking": "let me consider...", "signature": "abc"},
            {"type": "text", "text": "Here is the answer."},
        ]
        assert _extract_text(content) == "Here is the answer."

    def test_joins_multiple_text_blocks(self):
        content = [{"type": "text", "text": "Part one. "}, {"type": "text", "text": "Part two."}]
        assert _extract_text(content) == "Part one. Part two."

    def test_no_text_blocks_returns_empty_string(self):
        content = [{"type": "thinking", "thinking": "...", "signature": "abc"}]
        assert _extract_text(content) == ""


class TestRouteSelector:
    def test_returns_the_route_field(self):
        state: OrchestratorState = {"messages": [], "route": "swot"}
        assert _route_selector(state) == "swot"
