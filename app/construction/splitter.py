"""The notebook's RegexTextSplitter (L8) as a neo4j-graphrag component.

Kept in its own module (no `from __future__ import annotations`) because
neo4j-graphrag inspects the *real* return annotation of `run()` at class
creation time. Imported lazily so API startup doesn't load neo4j-graphrag.
"""

import re

from neo4j_graphrag.components.text_splitters.base import TextSplitter
from neo4j_graphrag.components.types import TextChunk, TextChunks


class RegexTextSplitter(TextSplitter):
    """Split on a regex; with '---' each product review becomes one chunk."""

    def __init__(self, regex: str) -> None:
        self._re = regex

    async def run(self, text: str) -> TextChunks:
        parts = [p.strip() for p in re.split(self._re, text) if p.strip()]
        return TextChunks(chunks=[TextChunk(text=p, index=i) for i, p in enumerate(parts)])
