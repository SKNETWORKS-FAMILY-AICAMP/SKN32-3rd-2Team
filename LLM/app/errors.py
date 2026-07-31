"""서비스 전역 예외.

`message` 는 프론트가 그대로 출력할 수 있는 한국어여야 한다 (docs/API.md 6절).
"""

from __future__ import annotations


class LLMServiceError(Exception):
    error_code = "INTERNAL_ERROR"
    status_code = 500
    message = "일시적인 오류입니다. 잠시 후 다시 시도해주세요."

    def __init__(self, message: str | None = None) -> None:
        if message:
            self.message = message
        super().__init__(self.message)


class ProviderTimeout(LLMServiceError):
    """스토리보드 13p: '5초 -> 일시적인 오류입니다 잠시후 다시 시도해주세요.'"""

    error_code = "LLM_TIMEOUT"
    status_code = 504
    message = "일시적인 오류입니다. 잠시 후 다시 시도해주세요."


class ProviderUnavailable(LLMServiceError):
    error_code = "LLM_UNAVAILABLE"
    status_code = 503
    message = "AI 응답 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."


class ProviderNotConfigured(LLMServiceError):
    error_code = "PROVIDER_NOT_CONFIGURED"
    status_code = 503
    message = "AI 응답 서비스가 아직 설정되지 않았습니다. 관리자에게 문의해주세요."
