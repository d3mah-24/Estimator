"""Page text from the tender PDF, with 1-based PDF page numbers (the `source_page`)."""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

# The tender uses a PDFTron font collection pdfminer does not know; text still extracts fine.
logging.getLogger("pdfminer").setLevel(logging.ERROR)


@dataclass(frozen=True)
class Page:
	number: int
	text: str


def file_sha256(path) -> str:
	h = hashlib.sha256()
	with open(path, "rb") as fh:
		for chunk in iter(lambda: fh.read(1 << 20), b""):
			h.update(chunk)
	return h.hexdigest()


def read_pages(path, pages: list[int] | None = None) -> list[Page]:
	"""Text of every page (or only `pages`, 1-based)."""
	out = []
	with pdfplumber.open(Path(path)) as pdf:
		numbers = pages or range(1, len(pdf.pages) + 1)
		for n in numbers:
			out.append(Page(number=n, text=pdf.pages[n - 1].extract_text() or ""))
	return out
