# src/sec_nlp/core/text/deduplication.py
# src/sec_nlp/core/deduplication.py
"""Efficient document deduplication using SimHash with indexed lookups."""

import re
from dataclasses import dataclass, field

from simhash import Simhash, SimhashIndex

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger


@dataclass(frozen=True)
class SimHashConfig:
    """Configuration for SimHash deduplication."""

    num_bits: int = 64
    max_distance: int = 3


@dataclass
class SimHashDeduplicator:
    """Efficient near-duplicate detection using SimHash with indexed lookups.

    Uses SimhashIndex for O(1) average-case lookups instead of O(n) comparisons.
    """

    config: SimHashConfig = field(default_factory=SimHashConfig)
    _index: SimhashIndex | None = field(default=None, init=False, repr=False)
    _hashes: dict[int, Simhash] = field(
        default_factory=dict, init=False, repr=False
    )
    _doc_count: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the SimHash index."""
        self._index = SimhashIndex(
            [],
            k=self.config.max_distance,
            f=self.config.num_bits,
        )

    def _compute_hash(self, text: str) -> Simhash:
        """Compute SimHash for normalized text."""
        normalized = self._normalize_text(text)
        tokens = normalized.split()
        if not tokens:
            # Return a zero hash for empty content
            return Simhash(value=0, f=self.config.num_bits)
        return Simhash(tokens, f=self.config.num_bits)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Lowercase and collapse whitespace for stable fingerprinting."""
        return re.sub(r"\s+", " ", text).strip().lower()

    def is_duplicate(self, text: str) -> bool:
        """Check if text is a near-duplicate of previously seen content.

        Args:
            text: Text content to check

        Returns:
            True if text is a near-duplicate, False otherwise
        """
        if not text or not text.strip():
            return True  # Empty content is considered duplicate

        doc_hash = self._compute_hash(text)

        hash_value = doc_hash.value
        if not isinstance(hash_value, int):
            return False

        # Check for exact hash match first (fast path)
        if hash_value in self._hashes:
            return True

        # Check for near-duplicates using the index
        if self._index is not None:
            near_dups = self._index.get_near_dups(doc_hash)
            if near_dups:
                return True

        return False

    def add(self, text: str) -> int | None:
        """Add text to the deduplication index.

        Args:
            text: Text content to add

        Returns:
            Hash value if added, None if duplicate or empty
        """
        if not text or not text.strip():
            return None

        doc_hash = self._compute_hash(text)

        hash_value = doc_hash.value
        if not isinstance(hash_value, int):
            return None

        # Skip if already seen
        if hash_value in self._hashes:
            return None

        # Check for near-duplicates
        if self._index is not None:
            near_dups = self._index.get_near_dups(doc_hash)
            if near_dups:
                return None

            # Add to index with unique key
            self._index.add(str(self._doc_count), doc_hash)

        self._hashes[hash_value] = doc_hash
        self._doc_count += 1
        return hash_value

    def add_if_unique(self, text: str) -> tuple[bool, int | None]:
        """Check and add in one operation.

        Args:
            text: Text content to check and potentially add

        Returns:
            Tuple of (is_unique, hash_value)
        """
        if not text or not text.strip():
            return False, None

        doc_hash = self._compute_hash(text)

        hash_value = doc_hash.value
        if not isinstance(hash_value, int):
            return False, None

        if hash_value in self._hashes:
            return False, hash_value

        # Check near-duplicates
        if self._index is not None:
            near_dups = self._index.get_near_dups(doc_hash)
            if near_dups:
                return False, hash_value

            # Add to index
            self._index.add(str(self._doc_count), doc_hash)

        self._hashes[hash_value] = doc_hash
        self._doc_count += 1
        return True, hash_value

    def deduplicate_documents(self, docs: list[Document]) -> list[Document]:
        """Remove near-duplicate documents from a list.

        Args:
            docs: List of documents to deduplicate

        Returns:
            List of unique documents (preserves order)
        """
        unique_docs: list[Document] = []
        initial_count = len(docs)

        for doc in docs:
            content = (doc.page_content or "").strip()
            if not content:
                continue

            is_unique, hash_value = self.add_if_unique(content)
            if is_unique:
                # Store hash in metadata for downstream use
                doc.metadata.update(
                    {
                        **(doc.metadata or {}),
                        "simhash": hash_value,
                    }
                )
                unique_docs.append(doc)

        if len(unique_docs) < initial_count:
            logger.info(
                "SimHash deduplicated %d -> %d documents (max_distance=%d, bits=%d)",
                initial_count,
                len(unique_docs),
                self.config.max_distance,
                self.config.num_bits,
            )

        return unique_docs

    def reset(self) -> None:
        """Clear the deduplication index."""
        self._index = SimhashIndex(
            [],
            k=self.config.max_distance,
            f=self.config.num_bits,
        )
        self._hashes.clear()
        self._doc_count = 0

    @property
    def count(self) -> int:
        """Number of unique documents seen."""
        return len(self._hashes)
