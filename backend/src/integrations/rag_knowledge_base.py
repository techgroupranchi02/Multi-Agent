"""
Aikyam Multi-Agent Pipeline — RAG Knowledge Base
Vector-indexed PRD storage using ChromaDB for downstream agent consumption.

Design:
- Only the latest active PRD version is indexed
- Old versions are deleted when a new version replaces them
- PRD is chunked by section headers for semantic retrieval
- Downstream agents (Architect, Developer, QA, Docs) query this instead of state.prd
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RAGKnowledgeBase:
    """
    ChromaDB-backed vector store for PRD sections.
    Each project has its own namespace; only the active PRD version is stored.
    """

    def __init__(self):
        self._client = None
        self._collection = None
        self._initialized: bool = False
        self._persist_dir: str = ""
        self._collection_name: str = "aikyam_prd"

    def initialize(self) -> bool:
        """Initialize ChromaDB with persistent storage."""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            from src.config import get_settings
            settings = get_settings()

            self._persist_dir = str(
                Path(settings.rag_persist_dir).resolve()
                if hasattr(settings, "rag_persist_dir") and settings.rag_persist_dir
                else Path(__file__).resolve().parent.parent.parent / "rag_data"
            )
            self._collection_name = getattr(settings, "rag_collection_name", "aikyam_prd")

            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )

            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            self._initialized = True
            logger.info(
                "✓ RAG Knowledge Base initialized (ChromaDB at %s, collection: %s)",
                self._persist_dir, self._collection_name,
            )
            return True

        except ImportError:
            logger.warning(
                "chromadb not installed — run: pip install chromadb"
            )
            return False
        except Exception as e:
            logger.error("Failed to initialize RAG Knowledge Base: %s", e)
            return False

    def index_prd(
        self,
        project_id: str,
        content: str,
        version: int,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Chunk the PRD into sections, embed, and store in ChromaDB.
        Each section gets a unique ID based on project + version + section.
        """
        if not self._initialized or not self._collection:
            logger.warning("RAG not initialized — skipping indexing")
            return False

        try:
            chunks = self._chunk_prd(content)
            if not chunks:
                logger.warning("No chunks extracted from PRD — nothing to index")
                return False

            ids = []
            documents = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                chunk_id = self._make_chunk_id(project_id, version, chunk["section_name"], i)
                ids.append(chunk_id)
                documents.append(chunk["content"])

                chunk_meta = {
                    "project_id": project_id,
                    "version": version,
                    "section_name": chunk["section_name"],
                    "section_type": chunk["section_type"],
                    "chunk_index": i,
                }
                if metadata:
                    chunk_meta.update(metadata)
                metadatas.append(chunk_meta)

            self._collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )

            logger.info(
                "Indexed PRD v%d for project %s (%d chunks)",
                version, project_id[:8], len(chunks),
            )
            return True

        except Exception as e:
            logger.error("Failed to index PRD: %s", e)
            return False

    def replace_index(
        self,
        project_id: str,
        content: str,
        new_version: int,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Delete all chunks for this project, then index the new version."""
        if not self._initialized or not self._collection:
            return False

        try:
            # Delete all existing chunks for this project
            self.delete_project(project_id)

            # Index the new version
            return self.index_prd(project_id, content, new_version, metadata)

        except Exception as e:
            logger.error("Failed to replace RAG index: %s", e)
            return False

    def query(
        self,
        project_id: str,
        query_text: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Query the RAG for relevant PRD sections.
        Returns list of {content, section_name, section_type, score}.
        """
        if not self._initialized or not self._collection:
            return []

        try:
            results = self._collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where={"project_id": project_id},
            )

            output = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    output.append({
                        "content": doc,
                        "section_name": meta.get("section_name", ""),
                        "section_type": meta.get("section_type", ""),
                        "version": meta.get("version", 0),
                        "relevance_score": 1.0 - distance,  # Cosine distance → similarity
                    })

            return output

        except Exception as e:
            logger.error("RAG query failed: %s", e)
            return []

    def get_full_prd(self, project_id: str) -> Optional[str]:
        """Retrieve the complete current PRD by fetching all chunks and reassembling."""
        if not self._initialized or not self._collection:
            return None

        try:
            results = self._collection.get(
                where={"project_id": project_id},
            )

            if not results or not results["documents"]:
                return None

            # Sort by chunk_index to reassemble in order
            chunks = []
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                chunks.append({
                    "content": doc,
                    "index": meta.get("chunk_index", i),
                    "section_name": meta.get("section_name", ""),
                })

            chunks.sort(key=lambda x: x["index"])
            return "\n\n".join(c["content"] for c in chunks)

        except Exception as e:
            logger.error("Failed to retrieve full PRD: %s", e)
            return None

    def delete_project(self, project_id: str) -> bool:
        """Delete all vectors for a project."""
        if not self._initialized or not self._collection:
            return False

        try:
            # Get all IDs for this project
            results = self._collection.get(
                where={"project_id": project_id},
            )

            if results and results["ids"]:
                self._collection.delete(ids=results["ids"])
                logger.info(
                    "Deleted %d chunks for project %s from RAG",
                    len(results["ids"]), project_id[:8],
                )

            return True

        except Exception as e:
            logger.error("Failed to delete project from RAG: %s", e)
            return False

    def get_section_names(self, project_id: str) -> list[str]:
        """Get all unique section names for a project."""
        if not self._initialized or not self._collection:
            return []

        try:
            results = self._collection.get(
                where={"project_id": project_id},
            )

            if not results or not results["metadatas"]:
                return []

            sections = set()
            for meta in results["metadatas"]:
                name = meta.get("section_name", "")
                if name:
                    sections.add(name)

            return sorted(sections)

        except Exception as e:
            logger.error("Failed to get section names: %s", e)
            return []

    # ── Private Helpers ──

    @staticmethod
    def _chunk_prd(content: str) -> list[dict[str, str]]:
        """
        Split PRD markdown into semantic chunks based on section headers.
        Each chunk contains the section header + its content.
        """
        chunks = []
        lines = content.split("\n")
        current_section = "Introduction"
        current_type = "general"
        current_lines: list[str] = []

        # Map section keywords to types
        section_type_map = {
            "executive summary": "summary",
            "user persona": "personas",
            "functional requirement": "requirements",
            "non-functional": "nfr",
            "user stor": "user_stories",
            "out of scope": "scope",
            "success metric": "metrics",
            "assumption": "assumptions",
            "constraint": "constraints",
        }

        for line in lines:
            stripped = line.strip()
            # Detect section headers (# or ## or ### or bold numbered)
            is_header = (
                stripped.startswith("#")
                or re.match(r"^\*?\*?\d+\.\s", stripped)
            )

            if is_header and current_lines:
                # Save the previous section
                chunk_content = "\n".join(current_lines).strip()
                if chunk_content and len(chunk_content) > 20:
                    chunks.append({
                        "section_name": current_section,
                        "section_type": current_type,
                        "content": chunk_content,
                    })
                current_lines = []

                # Parse new section name
                clean = stripped.lstrip("#").strip().lstrip("0123456789.").strip()
                clean = clean.strip("*").strip()
                if clean:
                    current_section = clean
                    # Determine section type
                    lower_clean = clean.lower()
                    current_type = "general"
                    for keyword, stype in section_type_map.items():
                        if keyword in lower_clean:
                            current_type = stype
                            break

            current_lines.append(line)

        # Don't forget the last section
        if current_lines:
            chunk_content = "\n".join(current_lines).strip()
            if chunk_content and len(chunk_content) > 20:
                chunks.append({
                    "section_name": current_section,
                    "section_type": current_type,
                    "content": chunk_content,
                })

        return chunks

    @staticmethod
    def _make_chunk_id(project_id: str, version: int, section_name: str, index: int) -> str:
        """Generate a deterministic chunk ID."""
        raw = f"{project_id}|v{version}|{section_name}|{index}"
        return hashlib.md5(raw.encode()).hexdigest()


# ── Singleton ──
_rag_kb: Optional[RAGKnowledgeBase] = None


def get_rag_knowledge_base() -> RAGKnowledgeBase:
    """Get or create the singleton RAG Knowledge Base."""
    global _rag_kb
    if _rag_kb is None:
        _rag_kb = RAGKnowledgeBase()
    return _rag_kb
