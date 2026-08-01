"""LLM 연동 지점.

실제 LLM(Anthropic/OpenAI 등) 연동 전까지는 더미 응답/키워드 기반 분류만 수행한다.
나중에 실 API를 붙일 때는 이 파일 내부만 교체하면 된다.
"""

CATEGORY_OTHER = "기타"

CATEGORIES = ["휴가/근태", "급여/보험", "복지제도", "채용/인사", CATEGORY_OTHER]

_CATEGORY_KEYWORDS = {
    "휴가/근태": ["휴가", "연차", "출근", "퇴근", "근태", "지각", "반차", "야근"],
    "급여/보험": ["급여", "월급", "연봉", "보험", "4대보험", "세금", "정산", "명세서"],
    "복지제도": ["복지", "포인트", "동호회", "교육비", "지원금", "건강검진", "식대"],
    "채용/인사": ["채용", "면접", "인사", "발령", "승진", "전배", "입사"],
}


def generate_reply(message: str) -> str:
    return f"'{message}'에 대한 답변입니다. (더미 응답 - 실제 LLM 연동 전)"


def classify_topic(message: str) -> str:
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in message for keyword in keywords):
            return category
    return CATEGORY_OTHER
