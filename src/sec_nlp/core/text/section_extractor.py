# src/sec_nlp/core/section_extractor.py
"""Extract complete sections from SEC documents with boundary detection."""

import re

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.chunking import SentenceSplitter
from sec_nlp.core.text.filters import SectionFilter, SectionType
from sec_nlp.types import JsonValue


class SectionBoundary:
    """Represents the boundaries of a section in a document."""

    def __init__(
        self,
        section_type: str,
        section_number: str,
        start_pos: int,
        end_pos: int | None = None,
        title: str | None = None,
    ):
        """Initialize section boundary.

        Args:
            section_type: Type of section (item, exhibit, part)
            section_number: Section number (e.g., "10", "1A", "10.1")
            start_pos: Character position where section starts
            end_pos: Character position where section ends (None if end not found)
            title: Section title if detected
        """
        self.section_type = section_type
        self.section_number = section_number
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.title = title

    def __repr__(self) -> str:
        end = f"{self.end_pos}" if self.end_pos else "EOF"
        return (
            f"<SectionBoundary {self.section_type} {self.section_number} "
            f"[{self.start_pos}:{end}]>"
        )


class ExtractedSection(Document):
    """A complete extracted section with metadata about boundaries."""

    def __init__(
        self,
        page_content: str,
        section_type: str,
        section_number: str,
        start_pos: int,
        end_pos: int | None = None,
        title: str | None = None,
        **metadata: JsonValue,
    ):
        """Initialize extracted section.

        Args:
            page_content: Full section text content
            section_type: Type of section (item, exhibit, part)
            section_number: Section number
            start_pos: Start position in original document
            end_pos: End position in original document
            title: Section title if detected
            **metadata: Additional metadata
        """
        # Add section metadata
        section_metadata: dict[str, JsonValue] = {
            "section_type": section_type,
            "section_number": section_number,
            "section_start_pos": start_pos,
            "section_end_pos": end_pos,
            "section_title": title,
            "is_complete_section": True,
            **metadata,
        }

        super().__init__(page_content=page_content, metadata=section_metadata)


class SectionExtractor:
    """Extract complete sections from documents with boundary detection."""

    # Patterns for detecting section boundaries
    SECTION_END_PATTERNS: dict[SectionType, list[str]] = {
        SectionType.ITEM: [
            r"^\s*item\s+\d+[a-z]?\b",  # Next item starts
            r"^\s*part\s+[ivxIVX]+\b",  # Next part starts
        ],
        SectionType.EXHIBIT: [
            r"^\s*exhibit\s+\d+",  # Next exhibit starts
            r"^\s*signature",  # Signature page
            r"^\s*item\s+\d+",  # Back to items section
        ],
        SectionType.PART: [
            r"^\s*part\s+[ivxIVX]+\b",  # Next part starts
        ],
    }

    def __init__(
        self,
        section_filter: SectionFilter,
        max_section_length: int = 500000,
        detect_boundaries: bool = True,
    ):
        """Initialize section extractor.

        Args:
            section_filter: Filter to identify sections
            max_section_length: Maximum length of extracted section
            detect_boundaries: Whether to detect section end boundaries
        """
        self.section_filter = section_filter
        self.max_section_length = max_section_length
        self.detect_boundaries = detect_boundaries

    def extract_sections(
        self,
        content: str,
        metadata: dict[str, JsonValue] | None = None,
    ) -> list[ExtractedSection]:
        """Extract complete sections from document content.

        Args:
            content: Full document text
            metadata: Metadata to attach to sections

        Returns:
            List of extracted sections with boundaries
        """
        sections: list[ExtractedSection] = []
        metadata = metadata or {}

        # Find all section starts
        boundaries = self._find_section_boundaries(content)

        if not boundaries:
            logger.debug("No sections found in document")
            return sections

        logger.debug("Found %d section(s) in document", len(boundaries))

        # Extract content for each section
        for boundary in boundaries:
            end_pos = (
                boundary.end_pos
                if boundary.end_pos is not None
                else len(content)
            )
            if end_pos < boundary.start_pos:
                end_pos = len(content)
            section_content = content[boundary.start_pos : end_pos]

            # Validate section length
            if len(section_content) > self.max_section_length:
                logger.warning(
                    "Section %s %s exceeds max length (%d > %d), truncating",
                    boundary.section_type,
                    boundary.section_number,
                    len(section_content),
                    self.max_section_length,
                )
                section_content = section_content[: self.max_section_length]

            # Create extracted section
            section = ExtractedSection(
                page_content=section_content,
                section_type=boundary.section_type,
                section_number=boundary.section_number,
                start_pos=boundary.start_pos,
                end_pos=boundary.end_pos,
                title=boundary.title,
                **metadata,
            )

            sections.append(section)

        return sections

    def extract_and_chunk(
        self,
        content: str,
        metadata: dict[str, JsonValue] | None = None,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
    ) -> list[Document]:
        """Extract sections and chunk them while preserving section context.

        Args:
            content: Full document text
            metadata: Metadata to attach
            chunk_size: Size of chunks
            chunk_overlap: Overlap between chunks

        Returns:
            List of chunked documents with section metadata
        """
        # Extract complete sections first
        sections = self.extract_sections(content, metadata)

        if not sections:
            return []

        splitter = SentenceSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        # Chunk each section separately
        all_chunks: list[Document] = []
        for section in sections:
            # Split the section into chunks
            section_chunks = splitter.split_documents([section])

            # Update metadata with chunk information
            for i, chunk in enumerate(section_chunks):
                chunk.metadata.update(
                    {
                        "chunk_index": i,
                        "total_chunks_in_section": len(section_chunks),
                        "section_length": len(section.page_content),
                    }
                )

            all_chunks.extend(section_chunks)

        logger.debug(
            "Extracted %d sections into %d chunks",
            len(sections),
            len(all_chunks),
        )

        return all_chunks

    def _find_section_boundaries(self, content: str) -> list[SectionBoundary]:
        """Find section boundaries in content.

        Args:
            content: Full document text

        Returns:
            List of section boundaries
        """
        boundaries: list[SectionBoundary] = []

        # Get all section start positions
        for (
            pattern_config,
            compiled_patterns,
        ) in self.section_filter._compiled_patterns:
            for pattern in compiled_patterns:
                for match in pattern.finditer(content):
                    # Extract section info
                    section_type = pattern_config.section_type.value
                    match_text = match.group(0)
                    start_pos = match.start()

                    # Try to extract section number
                    section_number = self._extract_section_number(
                        match_text, section_type
                    )

                    # Try to extract title (look at next 100 chars)
                    title = self._extract_title(
                        content[start_pos : start_pos + 100], section_type
                    )

                    # Create boundary (end will be determined later)
                    boundary = SectionBoundary(
                        section_type=section_type,
                        section_number=section_number or "unknown",
                        start_pos=start_pos,
                        title=title,
                    )

                    boundaries.append(boundary)

        # Sort boundaries by position
        boundaries.sort(key=lambda b: b.start_pos)

        # Remove duplicates (same section found by multiple patterns)
        boundaries = self._deduplicate_boundaries(boundaries)

        # Detect section ends if enabled
        if self.detect_boundaries:
            boundaries = self._detect_section_ends(content, boundaries)

        return boundaries

    def _extract_section_number(
        self, match_text: str, section_type: str
    ) -> str | None:
        """Extract section number from matched text.

        Args:
            match_text: Matched section header text
            section_type: Type of section

        Returns:
            Section number or None
        """
        if section_type == "exhibit":
            # Match: Exhibit 10, Exhibit 10.1, EX-10
            pattern = r"(?:exhibit|exh\.?|ex-?)\s*(\d+(?:\.\d+)?)"
            match = re.search(pattern, match_text, re.IGNORECASE)
            return match.group(1) if match else None

        elif section_type == "item":
            # Match: Item 1A, Item 7, Item 1.01
            pattern = r"item\s+(\d+[a-z]?(?:\.\d+)?)"
            match = re.search(pattern, match_text, re.IGNORECASE)
            return match.group(1) if match else None

        elif section_type == "part":
            # Match: Part I, Part II
            pattern = r"part\s+([ivxIVX]+)"
            match = re.search(pattern, match_text, re.IGNORECASE)
            return match.group(1) if match else None

        return None

    def _extract_title(self, text: str, section_type: str) -> str | None:
        """Extract section title from text following section header.

        Args:
            text: Text following section header
            section_type: Type of section

        Returns:
            Section title or None
        """
        # Look for text after the section marker up to newline or period
        lines = text.split("\n")
        if len(lines) > 1:
            # Title is usually on same line or next line
            potential_title = lines[0].strip()
            if len(potential_title) > 100:  # Too long, likely not a title
                return None
            # Clean up the title
            potential_title = re.sub(r"^[.\-:\s]+", "", potential_title)
            return potential_title if potential_title else None
        return None

    def _deduplicate_boundaries(
        self, boundaries: list[SectionBoundary]
    ) -> list[SectionBoundary]:
        """Remove duplicate boundaries (same section found by multiple patterns).

        Args:
            boundaries: List of boundaries

        Returns:
            Deduplicated list
        """
        seen: set[tuple[str, str, int]] = set()
        unique: list[SectionBoundary] = []

        for boundary in boundaries:
            key = (
                boundary.section_type,
                boundary.section_number,
                boundary.start_pos,
            )
            if key not in seen:
                seen.add(key)
                unique.append(boundary)

        if len(unique) < len(boundaries):
            logger.debug(
                "Removed %d duplicate boundaries", len(boundaries) - len(unique)
            )

        return unique

    def _detect_section_ends(
        self, content: str, boundaries: list[SectionBoundary]
    ) -> list[SectionBoundary]:
        """Detect end positions for sections.

        Args:
            content: Full document text
            boundaries: List of boundaries with only start positions

        Returns:
            Boundaries with end positions filled in
        """
        for i, boundary in enumerate(boundaries):
            # Check if there's a next boundary
            if i + 1 < len(boundaries):
                # Section ends where next section starts
                boundary.end_pos = boundaries[i + 1].start_pos
            else:
                # Last section goes to end of document
                boundary.end_pos = len(content)

            # Try to refine end position by looking for end markers
            section_content = content[boundary.start_pos : boundary.end_pos]
            refined_end = self._find_section_end_marker(
                section_content, boundary.section_type
            )

            if refined_end is not None:
                boundary.end_pos = boundary.start_pos + refined_end

        return boundaries

    def _find_section_end_marker(
        self, section_content: str, section_type: str
    ) -> int | None:
        """Find end marker within section content.

        Args:
            section_content: Content from section start
            section_type: Type of section

        Returns:
            Position of end marker relative to section start, or None
        """
        # Get end patterns for this section type
        end_patterns = self.SECTION_END_PATTERNS.get(
            SectionType(section_type), []
        )

        min_end_pos = None

        for pattern_str in end_patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE | re.MULTILINE)
            match = pattern.search(section_content)
            if match:
                # Found a potential end marker
                if match.start() == 0:
                    # Skip markers that point to the current section start
                    continue
                if min_end_pos is None or match.start() < min_end_pos:
                    min_end_pos = match.start()

        return min_end_pos


def create_section_extractor(
    section_filter: SectionFilter,
    max_section_length: int = 500000,
    detect_boundaries: bool = True,
) -> SectionExtractor:
    """Create a section extractor with the given filter.

    Args:
        section_filter: Filter to identify sections
        max_section_length: Maximum section length
        detect_boundaries: Whether to detect section ends

    Returns:
        Configured SectionExtractor
    """
    return SectionExtractor(
        section_filter=section_filter,
        max_section_length=max_section_length,
        detect_boundaries=detect_boundaries,
    )
