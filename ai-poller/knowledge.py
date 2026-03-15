"""ChromaDB-backed knowledge base for agent work history.

Stores agent work artifacts (proposals, code reviews, decisions, etc.)
and retrieves relevant context via semantic search.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import chromadb

from config import VectorDBConfig

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Wrapper around a ChromaDB collection for agent knowledge."""

    def __init__(self, config: VectorDBConfig) -> None:
        self._client = chromadb.HttpClient(host=config.host, port=config.port)
        self._collection = self._client.get_or_create_collection(
            name=config.collection,
            metadata={"hnsw:space": "cosine"},
        )

    def document_work(
        self,
        task_id: str,
        agent_id: str,
        work_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a piece of agent work in the knowledge base.

        Args:
            task_id: The task this work relates to.
            agent_id: The agent that produced this work.
            work_type: Category of work (e.g. "proposal", "code_review", "decision", "research").
            content: The actual text content to store and make searchable.
            metadata: Optional extra metadata.

        Returns:
            The document ID.
        """
        doc_id = f"{task_id}:{agent_id}:{work_type}:{int(time.time() * 1000)}"
        doc_metadata: dict[str, Any] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "work_type": work_type,
            "timestamp": int(time.time() * 1000),
        }
        if metadata:
            doc_metadata.update(metadata)

        self._collection.add(
            ids=[doc_id],
            documents=[content],
            metadatas=[doc_metadata],
        )
        logger.debug("Stored document %s (%d chars)", doc_id, len(content))
        return doc_id

    def query_knowledge(
        self,
        query: str,
        where: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search over stored knowledge.

        Args:
            query: Natural language query.
            where: Optional ChromaDB where filter (e.g. {"task_id": "abc"}).
            limit: Max results to return.

        Returns:
            List of dicts with keys: id, document, metadata, distance.
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": limit,
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        docs: list[dict[str, Any]] = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })
        return docs

    def get_task_history(self, task_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get all knowledge entries for a specific task."""
        return self.query_knowledge(
            query=f"work on task {task_id}",
            where={"task_id": task_id},
            limit=limit,
        )

    def get_agent_history(self, agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get all knowledge entries produced by a specific agent."""
        return self.query_knowledge(
            query=f"work by agent {agent_id}",
            where={"agent_id": agent_id},
            limit=limit,
        )
