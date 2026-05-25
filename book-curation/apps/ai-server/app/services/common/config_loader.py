from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _candidate_resource_roots() -> tuple[Path, ...]:
    current = Path(__file__).resolve()
    roots: list[Path] = []

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved not in roots:
            roots.append(resolved)

    for parent in current.parents:
        if parent.name == "app" and (parent / "prompts").is_dir():
            add(parent)
        app_child = parent / "app"
        if (app_child / "prompts").is_dir():
            add(app_child)

    cwd = Path.cwd().resolve()
    for candidate in (cwd, cwd / "app"):
        if (candidate / "prompts").is_dir():
            add(candidate)

    return tuple(roots)


@lru_cache(maxsize=64)
def load_text_resource(relative_path: str) -> str:
    normalized_path = str(relative_path or "").strip().lstrip("/\\")
    if not normalized_path:
        return ""

    for root in _candidate_resource_roots():
        resource_path = root / normalized_path
        if resource_path.is_file():
            return resource_path.read_text(encoding="utf-8")

    return ""
