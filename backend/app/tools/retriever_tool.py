"""Knowledge retrieval."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.core.result_cache import ResultCache

logger = get_logger("arcas.tools.retriever")

_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

# Map a normalised language to its dedicated knowledge file.
_LANGUAGE_FILES = {
    "python": "python_secure_coding.md",
    "java": "java_secure_coding.md",
    "javascript": "javascript_secure_coding.md",
    "typescript": "javascript_secure_coding.md",
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "use", "using", "do", "not", "no", "is", "are", "be", "all", "any",
    "your", "you", "this", "that", "it", "as", "at", "by", "from",
}

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]+")

# BM25 parameters.
_BM25_K1 = 1.5
_BM25_B = 0.75


def _tokenize(text: str) -> List[str]:
    return [
        token.lower()
        for token in _WORD_RE.findall(text or "")
        if token.lower() not in _STOPWORDS and len(token) > 2
    ]


@dataclass(frozen=True)
class Document:
    """One retrievable unit of knowledge."""

    doc_id: str
    source: str
    language: str
    title: str
    text: str
    tokens: Tuple[str, ...]

    @property
    def length(self) -> int:
        return len(self.tokens)


@dataclass
class Index:
    documents: Tuple[Document, ...]
    doc_frequency: Dict[str, int]
    average_length: float

    @property
    def size(self) -> int:
        return len(self.documents)


@lru_cache(maxsize=1)
def _build_index() -> Index:
    """Load and index every knowledge source once."""
    documents: List[Document] = []

    # Source 1: curated markdown guides, chunked by heading
    if _KNOWLEDGE_DIR.exists():
        for md_file in sorted(_KNOWLEDGE_DIR.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError as exc:  # noqa: BLE001
                logger.warning("Could not read %s: %s", md_file.name, exc)
                continue

            for index, section in enumerate(re.split(r"\n(?=#{1,3}\s)", text)):
                section = section.strip()
                if not section:
                    continue
                heading = section.splitlines()[0].lstrip("# ").strip()
                documents.append(
                    Document(
                        doc_id=f"md:{md_file.stem}:{index}",
                        source=md_file.stem,
                        language=_language_of_guide(md_file.stem),
                        title=heading,
                        text=section,
                        tokens=tuple(_tokenize(section)),
                    )
                )

    # Source 2: the structured 330-entry corpus
    try:
        from app.knowledge.corpus import build_corpus

        for entry in build_corpus():
            body = f"{entry['title']}\n{entry['content']}"
            documents.append(
                Document(
                    doc_id=f"kb:{entry['id']}",
                    source=entry["source"],
                    language=entry.get("language", "all"),
                    title=entry["title"],
                    text=body,
                    tokens=tuple(
                        _tokenize(body) + [t.lower() for t in entry.get("tags", [])]
                    ),
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Structured knowledge corpus unavailable: %s", exc)

    doc_frequency: Dict[str, int] = {}
    for document in documents:
        for token in set(document.tokens):
            doc_frequency[token] = doc_frequency.get(token, 0) + 1

    total_length = sum(d.length for d in documents)
    average_length = total_length / len(documents) if documents else 0.0

    logger.info(
        "Knowledge index built: %d documents (avg %.1f tokens).",
        len(documents),
        average_length,
    )
    return Index(
        documents=tuple(documents),
        doc_frequency=doc_frequency,
        average_length=average_length,
    )


def _language_of_guide(stem: str) -> str:
    for language, filename in _LANGUAGE_FILES.items():
        if Path(filename).stem == stem:
            return language
    if stem == "python_style_guide":
        return "python"
    return "all"


class RetrieverTool:
    """Retrieval-augmented knowledge provider over the curated corpus."""

    @staticmethod
    def get_context(language: str, query: str = "", top_k: int = 6) -> str:
        """Return the most relevant knowledge as a single formatted string."""
        from app.core.telemetry import start_span

        with start_span("rag.retrieve", layer=7, language=language, top_k=top_k):
            return RetrieverTool._get_context(language, query, top_k)

    @staticmethod
    def _get_context(language: str, query: str = "", top_k: int = 6) -> str:
        cache_extra = f"top_k={top_k}"
        cached = ResultCache.get_text("rag", query, language, extra=cache_extra)
        if cached is not None:
            return cached

        if settings.ENABLE_CHROMADB:
            chroma_context = _chroma_get_context(language, query, top_k)
            if chroma_context is not None:
                ResultCache.set_text(
                    "rag", query, language, chroma_context, extra=cache_extra
                )
                return chroma_context

        results = RetrieverTool.search(query, language, top_k)
        context = "\n\n".join(
            f"### {doc.title}\n{doc.text}" if not doc.text.startswith("#")
            else doc.text
            for doc, _score in results
        )
        ResultCache.set_text("rag", query, language, context, extra=cache_extra)
        return context

    @staticmethod
    def search(
        query: str,
        language: str = "",
        top_k: int = 6,
    ) -> List[Tuple[Document, float]]:
        """BM25 search with a language-affinity boost."""
        index = _build_index()
        if not index.documents:
            return []

        language = (language or "").lower()
        query_terms = _tokenize(query)
        if not query_terms:
            # No query: fall back to the language's own guidance so the agent is never left with an empty context.
            fallback = [
                doc
                for doc in index.documents
                if doc.language in (language, "all")
            ][:top_k]
            return [(doc, 0.0) for doc in fallback]

        term_counts: Dict[str, int] = {}
        for term in query_terms:
            term_counts[term] = term_counts.get(term, 0) + 1

        scored: List[Tuple[Document, float]] = []
        total_docs = index.size

        for document in index.documents:
            doc_counts: Dict[str, int] = {}
            for token in document.tokens:
                doc_counts[token] = doc_counts.get(token, 0) + 1

            score = 0.0
            for term in term_counts:
                frequency = doc_counts.get(term, 0)
                if not frequency:
                    continue
                df = index.doc_frequency.get(term, 0)
                idf = max(
                    0.0,
                    math.log(
                        (total_docs - df + 0.5) / (df + 0.5) + 1.0
                    ),
                )
                denominator = frequency + _BM25_K1 * (
                    1
                    - _BM25_B
                    + _BM25_B
                    * (document.length / (index.average_length or 1.0))
                )
                score += idf * (frequency * (_BM25_K1 + 1)) / denominator

            if score <= 0:
                continue

            if language and document.language == language:
                score *= 1.5
            elif document.language not in ("all", language) and language:
                score *= 0.4

            scored.append((document, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    @staticmethod
    def stats() -> dict:
        """Corpus composition - surfaced on /health."""
        index = _build_index()
        markdown = sum(1 for d in index.documents if d.doc_id.startswith("md:"))
        structured = sum(1 for d in index.documents if d.doc_id.startswith("kb:"))
        return {
            "total_documents": index.size,
            "markdown_sections": markdown,
            "structured_entries": structured,
            "average_tokens": round(index.average_length, 1),
            "ranking": "bm25",
            "chromadb_enabled": settings.ENABLE_CHROMADB,
            "vector_backend": (
                "chromadb" if settings.ENABLE_CHROMADB else "bm25 (in-process)"
            ),
        }


# Optional ChromaDB-backed semantic retrieval

_chroma_collection = None
_chroma_initialised = False


def _chroma_get_context(language: str, query: str, top_k: int) -> Optional[str]:
    """Return context via ChromaDB, or None to signal a fallback is needed."""
    global _chroma_collection, _chroma_initialised

    if not _chroma_initialised:
        _chroma_initialised = True
        try:
            import chromadb  # type: ignore

            client = chromadb.PersistentClient(path=settings.CHROMADB_PATH)
            collection = client.get_or_create_collection("arcas_knowledge")

            index = _build_index()
            # Seed from the same unified index the BM25 path uses.
            if collection.count() == 0 and index.documents:
                collection.add(
                    ids=[d.doc_id for d in index.documents],
                    documents=[d.text for d in index.documents],
                    metadatas=[
                        {
                            "source": d.source,
                            "language": d.language,
                            "title": d.title,
                        }
                        for d in index.documents
                    ],
                )
                logger.info(
                    "Seeded ChromaDB with %d documents.", len(index.documents)
                )
            _chroma_collection = collection
            logger.info("ChromaDB knowledge collection ready.")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ChromaDB unavailable (%s); using the BM25 retriever.", exc
            )
            _chroma_collection = None

    if _chroma_collection is None:
        return None

    try:
        result = _chroma_collection.query(
            query_texts=[query or language or "secure coding"],
            n_results=top_k,
        )
        docs = (result.get("documents") or [[]])[0]
        return "\n\n".join(docs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ChromaDB query failed: %s", exc)
        return None
