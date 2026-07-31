"""요청별 계측 기록 (JSONL).

성능 보고서(bench/report.py)의 입력이자, 실사용 중 지연 추적용.
기록 실패가 서비스에 영향을 주면 안 되므로 모든 예외를 삼킨다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def record(event: str, **fields: Any) -> None:
    settings = get_settings()
    if not settings.metrics_enabled:
        return
    try:
        path = settings.metrics_file
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - 계측 실패는 무시
        logger.debug("계측 기록 실패: %s", exc)
