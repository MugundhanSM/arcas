"""Populate the ChromaDB knowledge base with 300+ structured entries."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script (python scripts/populate_knowledge_base.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.logging import get_logger  # noqa: E402
from app.knowledge.corpus import _build_entries  # noqa: E402

logger = get_logger("arcas.scripts.kb")


def populate() -> int:
    entries = _build_entries()
    logger.info("Composed %d knowledge entries.", len(entries))

    if not settings.ENABLE_CHROMADB:
        logger.warning(
            "ENABLE_CHROMADB is false - entries composed but not embedded. "
            "Set ENABLE_CHROMADB=true to persist them to the vector store."
        )
        print(f"Composed {len(entries)} entries (ChromaDB disabled).")
        return len(entries)

    try:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=settings.CHROMADB_PATH)
        collection = client.get_or_create_collection("arcas_knowledge")

        # Optional semantic embeddings via sentence-transformers.
        embeddings = None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode(
                [e["content"] for e in entries]
            ).tolist()
            logger.info("Embedded entries with sentence-transformers.")
        except Exception:  # noqa: BLE001
            logger.info(
                "sentence-transformers unavailable - using ChromaDB default "
                "embedding."
            )

        collection.upsert(
            ids=[e["id"] for e in entries],
            documents=[e["content"] for e in entries],
            metadatas=[
                {
                    "category": e["category"],
                    "language": e["language"],
                    "source": e["source"],
                    "title": e["title"],
                    "tags": ",".join(e["tags"]),
                }
                for e in entries
            ],
            embeddings=embeddings,
        )
        total = collection.count()
        logger.info("ChromaDB collection now holds %d documents.", total)
        print(f"Populated ChromaDB with {len(entries)} entries (total {total}).")
        return len(entries)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to populate ChromaDB: %s", exc)
        print(f"ERROR: {exc}")
        return 0


if __name__ == "__main__":
    count = populate()
    print(f"Done. {count} entries processed.")
