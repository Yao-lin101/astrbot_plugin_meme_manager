from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import TYPE_CHECKING

from ...config import PLUGIN_DATA_DIR
from ...utils import get_config_value
from ..db.database import clear_legacy_tag_embeddings

if TYPE_CHECKING:
    from lancedb import AsyncConnection, AsyncTable

logger = logging.getLogger(__name__)

CACHE_PATH = PLUGIN_DATA_DIR / "lancedb"
TABLE_NAME = "tag_embeddings"
SOURCE_KEY = b"embedding_source"
REBUILD_COMMAND = "/表情管理 重构向量缓存"
WRITE_BATCH_SIZE = 32


def _tag_filter(tags) -> str:
    """Build a LanceDB predicate from literal tag values.

    Args:
        tags: Nonempty iterable of tag names to match exactly.

    Returns:
        An SQL predicate with quoted tag values.
    """
    literals = ["'" + tag.replace("'", "''") + "'" for tag in tags]
    return f"tag IN ({', '.join(literals)})"


def _validate_vector(vector: list[float], dimension: int | None) -> int:
    """Check that a vector is usable in the active cosine search.

    Args:
        vector: Embedding returned by the provider or read from the cache.
        dimension: Required length, if the cache has a known dimension.

    Returns:
        Actual length of the vector.

    Raises:
        ValueError: If the length or contents are invalid.
    """
    length = len(vector) if vector is not None else 0
    if dimension is not None and length != dimension:
        raise ValueError(
            f"Expected a {dimension}-dimensional embedding, got {length}. "
            f"Run {REBUILD_COMMAND} after changing models."
        )
    if not length or not all(map(math.isfinite, vector)) or not any(vector):
        raise ValueError("The embedding is empty, non-finite, or zero.")
    return length


class TagEmbeddingStore:
    """Manage the plugin's active LanceDB table and its background writer."""

    def __init__(self, sender):
        self._sender = sender
        self._db: AsyncConnection | None = None
        self._table: AsyncTable | None = None
        self._lock = asyncio.Lock()
        self._sync_task: asyncio.Task | None = None
        self._sync_pending = False
        self._rebuilding = False
        self._closed = False

    def _provider(self):
        """Resolve the embedding provider and its persisted configuration identity.

        Returns:
            A provider and identity, or None if embeddings are unconfigured.

        Raises:
            ValueError: If the configured provider is unavailable.
        """
        context = self._sender.context
        provider_id = get_config_value(self._sender.config, "embedding_provider_id", "")
        if provider_id:
            provider = context.get_provider_by_id(provider_id)
            if not callable(getattr(provider, "get_embedding", None)):
                raise ValueError(f"Embedding provider {provider_id!r} is unavailable.")
        else:
            provider = next(iter(context.get_all_embedding_providers()), None)
            if provider is None:
                return None

        config = getattr(provider, "provider_config", {})
        model = getattr(provider, "model", None) or config.get("embedding_model")
        if not model and callable(getattr(provider, "get_model", None)):
            model = provider.get_model()
        source = json.dumps(
            [
                config.get("type") or type(provider).__name__,
                config.get("id") or getattr(provider, "id", None) or provider_id,
                model,
                config.get("embedding_dimensions"),
                config.get("embedding_dimensions_mode"),
            ],
            ensure_ascii=False,
        ).encode()
        return provider, source

    async def _connect(self) -> AsyncConnection:
        """Open the local LanceDB connection on demand with the lock held."""
        if self._db is None:
            import lancedb

            self._db = await lancedb.connect_async(CACHE_PATH)
        return self._db

    async def _open_table(self) -> AsyncTable | None:
        """Get the persisted table if present, with the lock held."""
        if self._table is None:
            db = await self._connect()
            if TABLE_NAME in (await db.list_tables()).tables:
                self._table = await db.open_table(TABLE_NAME)
        return self._table

    async def _model_table(self, source: bytes) -> tuple[AsyncTable | None, int | None]:
        """Check the table's model and dimension with the lock held.

        Args:
            source: Identity of the resolved embedding provider and model.

        Returns:
            The active table and its stored dimension, if the table exists.

        Raises:
            ValueError: If the table was built using a different configuration.
        """
        table = await self._open_table()
        if table is None:
            return None, None
        schema = await table.schema()
        if (schema.metadata or {}).get(SOURCE_KEY) != source:
            raise ValueError(
                f"Embedding model differs from the cache. Run {REBUILD_COMMAND}."
            )
        return table, schema.field("vector").type.list_size

    async def _read_table(self):
        """Get the provider and table for a query, or None with embeddings disabled."""
        resolved = self._provider()
        if resolved is None:
            return None
        provider, source = resolved
        async with self._lock:
            if self._rebuilding or self._closed:
                raise RuntimeError("The embedding cache is rebuilding or closed.")
            table, dimension = await self._model_table(source)
            if table is None:
                raise RuntimeError("The LanceDB embedding table is not ready.")
        return provider, table, dimension

    async def search(
        self, query: str, tags: set[str], threshold: float, limit: int
    ) -> list[tuple[str, float]]:
        """Find the highest-scoring eligible tags using LanceDB cosine search.

        Args:
            query: Tag to use as the search query.
            tags: Eligible tags, with any exact match already excluded.
            threshold: Minimum cosine similarity.
            limit: Maximum number of matching tags.

        Returns:
            Matching tags and their similarity scores, in descending score order.
        """
        if not tags:
            return []
        try:
            minimum = float(threshold)
            if not math.isfinite(minimum):
                raise ValueError("The cosine similarity threshold must be finite.")
            cache = await self._read_table()
            if cache is None:
                return []
            provider, table, dimension = cache
            lookup = (
                table.query().where(_tag_filter((query,))).select(["vector"]).limit(1)
            )
            cached = (await lookup.to_arrow()).to_pylist()
            vector = (
                cached[0]["vector"] if cached else await provider.get_embedding(query)
            )
            _validate_vector(vector, dimension)
            if table is not self._table:
                raise RuntimeError("The embedding table changed during the query.")

            neighbors = (
                table.query()
                .nearest_to(vector)
                .distance_type("cosine")
                .where(_tag_filter(tags))
                .select(["tag", "_distance"])
                .limit(limit)
            )
            results = (await neighbors.to_arrow()).to_pylist()
            if table is not self._table:
                raise RuntimeError("The embedding table changed during the query.")

            matches = []
            for row in results:
                distance = row["_distance"]
                if distance is None or not math.isfinite(distance):
                    logger.warning(
                        "Skipping invalid cosine distance for tag %r.", row["tag"]
                    )
                elif 1 - distance >= minimum:
                    matches.append((row["tag"], 1 - distance))
            return matches
        except Exception as exc:
            logger.warning("Skipping vector search for tag %r: %s", query, exc)
            return []

    async def get_vectors(self, tags: set[str]) -> dict[str, list[float]]:
        """Read the vectors needed for the administrative all-pairs scan.

        Args:
            tags: Tags currently referenced by memes.

        Returns:
            Cached vectors for the selected tags.
        """
        if not tags:
            return {}
        try:
            cache = await self._read_table()
            if cache is None:
                return {}
            _, table, _ = cache
            rows = await table.query().where(_tag_filter(tags)).to_arrow()
            if table is not self._table:
                raise RuntimeError("The embedding table changed during the scan.")
            return {row["tag"]: row["vector"] for row in rows.to_pylist()}
        except Exception as exc:
            logger.warning("Skipping cached vectors for the tag merge scan: %s", exc)
            return {}

    async def delete(self, tags: set[str]) -> None:
        """Remove merged source tags from the cache.

        Args:
            tags: Source tags that were removed from the library.
        """
        if not tags:
            return
        try:
            async with self._lock:
                if self._closed:
                    return
                if self._sync_task and not self._sync_task.done():
                    self._sync_pending = True
                table = await self._open_table()
                if table is not None:
                    await table.delete(_tag_filter(tags))
        except Exception as exc:
            logger.warning("Skipping deletion of merged tag vectors: %s", exc)

    def start_sync(self) -> None:
        """Schedule an incremental sync, coalescing requests during a run."""
        if self._closed:
            return
        if self._sync_task and not self._sync_task.done():
            self._sync_pending = True
        else:
            self._sync_task = asyncio.create_task(self._sync())

    async def _sync(self) -> None:
        """Backfill missing tags and batch LanceDB writes."""
        task = asyncio.current_task()
        saved = 0
        try:
            resolved = self._provider()
            if resolved is None:
                return
            provider, source = resolved
            while task is self._sync_task:
                self._sync_pending = False
                tags = self._sender.category_manager.get_local_categories()
                if not tags:
                    break
                async with self._lock:
                    if task is not self._sync_task:
                        return
                    table, dimension = await self._model_table(source)
                    cached = set()
                    if table is not None:
                        cached = set(
                            (await table.query().select(["tag"]).to_arrow())[
                                "tag"
                            ].to_pylist()
                        )

                missing = sorted(tags - cached)
                for start in range(0, len(missing), WRITE_BATCH_SIZE):
                    rows = []
                    for tag in missing[start : start + WRITE_BATCH_SIZE]:
                        if task is not self._sync_task:
                            return
                        try:
                            vector = await provider.get_embedding(tag)
                            dimension = _validate_vector(vector, dimension)
                            rows.append({"tag": tag, "vector": vector})
                        except Exception as exc:
                            logger.warning(
                                "Skipping embedding for tag %r: %s", tag, exc
                            )
                    if not rows:
                        continue
                    async with self._lock:
                        if task is not self._sync_task:
                            return
                        if self._sync_pending:
                            active = (
                                self._sender.category_manager.get_local_categories()
                            )
                            rows = [row for row in rows if row["tag"] in active]
                            if not rows:
                                continue

                        if table is None:
                            import pyarrow as pa

                            schema = pa.schema(
                                [
                                    ("tag", pa.string()),
                                    ("vector", pa.list_(pa.float32(), dimension)),
                                ],
                                metadata={SOURCE_KEY: source},
                            )
                            db = await self._connect()
                            table = await db.create_table(
                                TABLE_NAME, rows, schema=schema
                            )
                            self._table = table
                        else:
                            await table.add(rows)
                        saved += len(rows)

                if not self._sync_pending:
                    break
            if saved or self._rebuilding:
                logger.info(
                    "Tag embedding synchronization finished. Saved %d vectors.", saved
                )
        except Exception as exc:
            logger.warning("Skipping tag embedding synchronization: %s", exc)
        finally:
            if task is self._sync_task:
                self._rebuilding = False

    async def reset(self, *, rebuild: bool = False) -> bool:
        """Drop the vector table and optionally start a fresh backfill.

        Args:
            rebuild: Whether to populate the new table in the background.

        Returns:
            Whether the cache was successfully cleared.
        """
        async with self._lock:
            try:
                if self._closed or (rebuild and self._provider() is None):
                    raise RuntimeError(
                        "An active embedding provider is required to rebuild."
                    )
                db = self._db
                if rebuild or CACHE_PATH.exists():
                    db = await self._connect()
                # Writers acquire the same lock and are bound to the current task.
                if self._sync_task is not None:
                    self._sync_task.cancel()
                    self._sync_task = None
                self._sync_pending = False
                self._rebuilding = rebuild
                if self._table is not None:
                    self._table.close()
                    self._table = None
                if db is not None:
                    await db.drop_table(TABLE_NAME, ignore_missing=True)
                clear_legacy_tag_embeddings()
                if rebuild:
                    self.start_sync()
                return True
            except Exception as exc:
                logger.warning("Skipping reset of the tag embedding cache: %s", exc)
                return False
            finally:
                if self._sync_task is None:
                    self._rebuilding = False

    async def close(self) -> None:
        """Stop background writes before an AstrBot plugin reload or shutdown."""
        async with self._lock:
            self._closed = True
            if self._sync_task is not None:
                self._sync_task.cancel()
                self._sync_task = None
            if self._table is not None:
                self._table.close()
                self._table = None
            if self._db is not None:
                self._db.close()
                self._db = None
