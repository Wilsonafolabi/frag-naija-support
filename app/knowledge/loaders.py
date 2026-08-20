"""Document loaders.

Loader registry pattern: each loader declares which extensions it can handle
and knows how to extract plain text. The pipeline selects a loader by path.
Extending to DOCX/Markdown later = register a new loader, no other changes.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List


class DocumentLoadError(Exception):
    """Raised when a document cannot be loaded or contains no text."""


class BaseLoader(ABC):
    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        ...

    @abstractmethod
    def extract_text(self, path: Path) -> str:
        ...


class PdfLoader(BaseLoader):
    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def extract_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover
            raise DocumentLoadError("pypdf is required to load PDFs") from e

        try:
            reader = PdfReader(str(path))
        except Exception as e:
            raise DocumentLoadError(f"Failed to read PDF {path.name}: {e}") from e

        pages: List[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)

        if not pages:
            raise DocumentLoadError(
                f"PDF contained no extractable text: {path.name}"
            )
        return "\n\n".join(pages)


class MarkdownLoader(BaseLoader):
    """Handles .md, .markdown, and .txt files."""
    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in {".md", ".markdown", ".txt"}

    def extract_text(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            raise DocumentLoadError(f"Failed to read text file {path.name}: {e}") from e
            
        if not text.strip():
            raise DocumentLoadError(f"Document contained no text: {path.name}")
        return text


class LoaderRegistry:
    """Selects a loader by file extension. New loaders can be registered at runtime."""

    def __init__(self) -> None:
        # Both PdfLoader and MarkdownLoader are registered here
        self._loaders: List[BaseLoader] = [PdfLoader(), MarkdownLoader()]

    def register(self, loader: BaseLoader) -> None:
        # Prepend so newer loaders take precedence over built-ins
        self._loaders.insert(0, loader)

    def get_loader(self, path: Path) -> BaseLoader:
        for loader in self._loaders:
            if loader.can_handle(path):
                return loader
        raise DocumentLoadError(
            f"No loader registered for extension '{path.suffix}'"
        )

    def load(self, path: Path) -> str:
        return self.get_loader(path).extract_text(path)


default_registry = LoaderRegistry()