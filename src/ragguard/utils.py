from __future__ import annotations

from pathlib import Path


def collect_markdown_files(input_path: Path) -> list[Path]:
    """Collect Markdown files without mutating the input path."""
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".md" else []
    if input_path.is_dir():
        return sorted(path for path in input_path.rglob("*.md") if path.is_file())
    raise FileNotFoundError(f"Input path does not exist: {input_path}")


def display_path(path: Path, base: Path | None = None) -> str:
    try:
        if base is not None:
            return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        pass
    return str(path)
