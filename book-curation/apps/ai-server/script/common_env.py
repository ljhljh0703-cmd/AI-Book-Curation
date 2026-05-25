from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


def find_ai_server_root(start: Path | None = None) -> Path:
    """Find apps/ai-server so CLI scripts load the same local env files as the FastAPI app."""
    current = (start or Path(__file__)).resolve()
    candidates: Iterable[Path] = [current, *current.parents]
    for candidate in candidates:
        if candidate.name == "ai-server" and (candidate / "app").exists():
            return candidate
        nested = candidate / "apps" / "ai-server"
        if nested.exists() and (nested / "app").exists():
            return nested
    return Path.cwd().resolve()


def load_ai_server_env(start: Path | None = None) -> Path:
    """Load .env first and .env.local second without printing secret values.

    수정 포인트:
    - 운영 app.core.config.Settings와 동일하게 .env → .env.local 순서로 읽습니다.
    - override=True를 사용해 로컬 테스트용 .env.local 값이 기본 .env 값을 덮어쓰게 합니다.
    - 파일이 없어도 실패하지 않도록 두어 Docker/NAS 배포와 충돌하지 않습니다.
    """
    root = find_ai_server_root(start)
    load_dotenv(root / ".env", override=True)
    load_dotenv(root / ".env.local", override=True)
    return root
