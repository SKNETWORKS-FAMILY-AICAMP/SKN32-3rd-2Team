"""벤치 결과 집계 → `docs/PERFORMANCE_REPORT.md`.

    python bench/report.py

`bench/results/*.jsonl` 을 전부 읽어 조건별로 묶고, 표를 만들어 보고서를 쓴다.
토큰 수는 벤치 JSONL 에 없으므로 `logs/metrics.jsonl` 을 `chatroom_id` 로 조인해
가져온다(운영 계측을 그대로 재활용한다 — 벤치용 계측을 따로 두면 두 숫자가
어긋날 수 있다).

원본 JSONL 은 `.gitignore` 대상이고, 여기서 나온 보고서만 커밋한다.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
LLM_DIR = BENCH_DIR.parent
RESULTS_DIR = BENCH_DIR / "results"
METRICS_PATH = LLM_DIR / "logs" / "metrics.jsonl"
DEFAULT_OUT = LLM_DIR / "docs" / "PERFORMANCE_REPORT.md"

# 1M 토큰당 USD. **직접 확인한 값만 넣는다.** 모르면 None 으로 두고 보고서에
# "요금 미확인" 으로 표시한다 — 추정치를 표에 넣으면 그게 사실처럼 인용된다.
PRICING: dict[str, tuple[float, float] | None] = {
    "gpt-4o-mini": (0.15, 0.60),
    "qwen2.5:7b": (0.0, 0.0),  # 로컬 실행. 전기요금은 따지지 않는다
}
USD_KRW = 1380  # 환산 기준. 보고서에 함께 표기한다

# `/v1/chat` 한 번은 프로바이더를 **두 번** 부른다(답변 생성 + 주제 분류).
# 그런데 `logs/metrics.jsonl` 에는 답변 호출의 토큰만 남는다 — `classify()` 는
# 토큰을 돌려주지 않기 때문이다(프로바이더 인터페이스가 문자열만 반환).
#
# 인터페이스를 바꾸는 대신 주제 호출을 따로 실측했다. 아래는 gpt-4o-mini 로
# 벤치 문항 5개를 같은 프롬프트·같은 스키마로 호출해 얻은 평균이다.
# 주제 프롬프트는 질문 길이에 거의 무관하므로(시스템 프롬프트가 대부분)
# 문항이 달라도 크게 흔들리지 않는다.
#
# 재측정이 필요하면: 프롬프트(`TOPIC_SYSTEM`)를 크게 고쳤을 때.
TOPIC_CALL_TOKENS = (838, 9)  # (입력, 출력) — gpt-4o-mini 실측 평균

_HAN = re.compile(r"[一-鿿]")
_HANGUL = re.compile(r"[가-힣]")

# 근거가 없을 때 나와야 하는 문구. 프롬프트가 이 표현을 쓰도록 지시하고 있다.
_REFUSAL = "찾을 수 없습니다"


def _is_foreign(answer: str | None) -> bool:
    """한자가 한글의 10% 를 넘으면 한국어 이탈로 본다.

    법령명 병기("근로기준법(勤勞基準法)") 정도는 정상이므로 0 이 아니라
    비율로 판단한다. Qwen2.5 가 한국어 질문에 중국어로 답하는 것을 잡으려는
    지표다 — 실제로 걸린 답변들은 한자 수백 자에 한글이 한 자릿수였다.
    """
    if not answer:
        return False
    han = len(_HAN.findall(answer))
    return bool(han) and han > len(_HANGUL.findall(answer)) * 0.1


@dataclass
class Run:
    """한 조건의 실행 결과 하나."""

    tag: str
    provider: str
    model: str
    variant: str
    run_id: str
    rows: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}/{self.tag}"

    @property
    def done(self) -> list[dict]:
        """에러 없이 끝난 문항. 지연·길이 통계는 이것만으로 낸다."""
        return [r for r in self.rows if not r["error_code"]]

    @property
    def errors(self) -> int:
        return len(self.rows) - len(self.done)

    @property
    def topic_correct(self) -> int:
        return sum(1 for r in self.rows if r["topic_correct"])

    @property
    def foreign(self) -> int:
        return sum(1 for r in self.done if _is_foreign(r["answer"]))

    def latency(self, pct: float) -> float:
        lat = sorted(r["latency_ms"] for r in self.done)
        if not lat:
            return 0.0
        return lat[min(int(len(lat) * pct), len(lat) - 1)] / 1000

    @property
    def over_5s(self) -> int:
        return sum(1 for r in self.done if r["latency_ms"] > 5000)

    @property
    def answer_chars(self) -> float:
        return st.median([r["answer_chars"] for r in self.done]) if self.done else 0

    @property
    def group_consistency(self) -> tuple[int, int]:
        """패러프레이즈 묶음이 하나의 주제로 수렴하는 비율.

        정답 여부와 별개다. 틀리더라도 **일관되게** 틀리면 도넛 차트는
        조각나지 않는다. 대시보드 신뢰도의 직접적인 근거다.
        """
        groups: dict[str, set[str]] = defaultdict(set)
        for r in self.rows:
            if r.get("group") and r["got_topic"]:
                groups[r["group"]].add(r["got_topic"])
        if not groups:
            return 0, 0
        return sum(1 for v in groups.values() if len(v) == 1), len(groups)

    @property
    def oos_refused(self) -> tuple[int, int]:
        """범위 밖 질문에서 '모른다' 고 말한 비율.

        근거 없이 지어내면 안 된다. 다만 `oos-personal-balance`("제 연차가
        며칠 남았나요") 처럼 **일반 기준은 답해야 하는** 문항이 섞여 있어
        100% 가 정답은 아니다. 해석은 보고서 본문에서 한다.
        """
        oos = [r for r in self.done if r["out_of_scope"]]
        return sum(1 for r in oos if _REFUSAL in (r["answer"] or "")), len(oos)


def load_runs(expected: int) -> tuple[list[Run], list[str]]:
    """결과 파일을 읽어 Run 으로 만든다. 불완전한 실행은 걸러낸다."""
    runs: list[Run] = []
    skipped: list[str] = []

    for path in sorted(RESULTS_DIR.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if not rows:
            skipped.append(f"{path.name}: 비어 있음")
            continue
        # 중간에 끊긴 실행을 그대로 집계하면 '문항 수가 적어서' 정확도가
        # 높아 보이는 착시가 생긴다. 조용히 섞이지 않게 막는다.
        if len(rows) < expected:
            skipped.append(f"{path.name}: {len(rows)}/{expected}문항 (중단됨)")
            continue
        # 전부 실패한 실행은 아무것도 측정하지 못한 것이다. 표에 넣으면
        # 정확도 0% 로 찍혀 '성능이 나쁘다' 로 오독된다 — 성능이 아니라
        # 호출 자체가 안 된 것이다. 제외 목록에 이유를 남긴다.
        if all(r["error_code"] for r in rows):
            code = rows[0]["error_code"]
            skipped.append(f"{path.name}: {expected}문항 전부 실패 ({code})")
            continue
        head = rows[0]
        runs.append(
            Run(
                tag=head["tag"],
                provider=head["provider"],
                model=head["model"],
                variant=head.get("variant", head["tag"]),
                run_id=head["run_id"],
                rows=rows,
            )
        )
    return runs, skipped


def load_tokens() -> dict[tuple[str, str], tuple[int, int]]:
    """`metrics.jsonl` 에서 (chatroom_id, ts) → (prompt, completion) 토큰.

    벤치는 `chatroom_id` 를 `bench-{문항id}` 로 넣으므로 같은 문항을 여러 조건에서
    돌리면 키가 겹친다. 그래서 시각까지 함께 키로 쓴다.
    """
    if not METRICS_PATH.exists():
        return {}
    out: dict[tuple[str, str], tuple[int, int]] = {}
    for line in METRICS_PATH.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        m = json.loads(line)
        if m.get("event") != "chat":
            continue
        p, c = m.get("prompt_tokens"), m.get("completion_tokens")
        if p is None or c is None:
            continue
        out[(m["chatroom_id"], m["ts"][:19])] = (p, c)
    return out


def run_tokens(run: Run, table: dict[tuple[str, str], tuple[int, int]]) -> tuple[float, float]:
    """조건별 문항당 평균 토큰. 계측이 비면 (0, 0)."""
    found = []
    for r in run.done:
        cid = f"bench-{r['question_id']}"
        # 벤치 행의 ts 는 호출 완료 직후라, 계측 행과 같은 초이거나 1초 이내다.
        stamp = datetime.fromisoformat(r["ts"])
        for delta in (0, -1, 1):
            key = (cid, (stamp.replace(microsecond=0)).isoformat()[:19])
            if delta:
                shifted = stamp.timestamp() + delta
                key = (cid, datetime.fromtimestamp(shifted, stamp.tzinfo).isoformat()[:19])
            if key in table:
                found.append(table[key])
                break
    if not found:
        return 0.0, 0.0
    return st.mean(p for p, _ in found), st.mean(c for _, c in found)


def cost_per_10k(model: str, prompt: float, completion: float) -> str:
    rate = PRICING.get(model)
    if rate is None:
        return "요금 미확인"
    if rate == (0.0, 0.0):
        return "0원 (로컬)"
    usd = (prompt * rate[0] + completion * rate[1]) / 1_000_000 * 10_000
    return f"{usd * USD_KRW:,.0f}원"


def md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def build(runs: list[Run], skipped: list[str], expected: int) -> str:
    tokens = load_tokens()
    by_tag = defaultdict(list)
    for r in runs:
        by_tag[r.tag].append(r)

    # --- 프로바이더 비교 (tag=final) ---
    finals = sorted(by_tag.get("final", []), key=lambda r: r.provider)
    provider_rows = []
    for run in finals:
        p, c = run_tokens(run, tokens)
        gc, gt = run.group_consistency
        provider_rows.append(
            [
                f"`{run.provider}`",
                f"`{run.model}`",
                f"{run.topic_correct}/{len(run.rows)} ({run.topic_correct / len(run.rows) * 100:.0f}%)",
                f"{gc}/{gt}",
                f"{run.latency(0.5):.1f}s",
                f"{run.latency(0.95):.1f}s",
                f"{run.answer_chars:.0f}자",
                f"{run.errors}건",
                f"{run.foreign}건",
                cost_per_10k(run.model, p, c),
            ]
        )

    # --- 프롬프트 개선 이력 (OpenAI 단일 프로바이더 안에서의 변화) ---
    order = ["baseline", "baseline-r2", "catdef", "fewshot", "catdef2", "promoted", "final"]
    history = [r for t in order for r in by_tag.get(t, []) if r.provider == "openai"]
    history_rows = []
    for run in history:
        wrong = [r["question_id"] for r in run.rows if not r["topic_correct"]]
        history_rows.append(
            [
                f"`{run.tag}`",
                f"{run.topic_correct}/{len(run.rows)} ({run.topic_correct / len(run.rows) * 100:.0f}%)",
                f"{run.latency(0.5):.1f}s",
                f"{run.answer_chars:.0f}자",
                ", ".join(f"`{w}`" for w in wrong) or "—",
            ]
        )

    # --- Qwen 언어 이탈 ---
    qwen = [r for r in runs if r.provider == "qwen"]
    qwen_rows = []
    for run in sorted(qwen, key=lambda r: r.run_id):
        qwen_rows.append(
            [
                f"`{run.tag}`",
                f"{run.topic_correct}/{len(run.rows)}",
                f"{run.foreign}/{len(run.done)}",
                f"{run.latency(0.5):.1f}s",
                f"{run.latency(1.0):.1f}s",
                f"{run.answer_chars:.0f}자",
            ]
        )

    gen = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    parts: list[str] = []
    parts.append(f"""# 성능 보고서 — LLM 서비스

> 자동 생성: `python bench/report.py` · {gen}
> 원본 측정값은 `bench/results/*.jsonl` (git 미포함), 질문 세트는 `bench/questions.yaml`.

## 1. 측정 방법과 그 한계

`bench/questions.yaml` 의 **{expected}문항**을 실제 서비스 경로(`generate_answer`)로
돌려 문항별 결과를 JSONL 로 남기고 집계했다. 문항은 실제 코퍼스(PDF 28개)에서
뽑았고, 같은 의도를 다르게 물은 **패러프레이즈 묶음 7개**와 **범위 밖 질문 3개**를
섞었다.

**중요 — 이 수치는 end-to-end 성능이 아니다.**
검색은 실제 RAG 서비스가 아니라 `bench/corpus.py` 를 쓴다. 문항마다 정답 문서가
이미 라벨링되어 있으므로 **그 문서 안에서만** 관련 구간을 찾는다. 즉 검색이
완벽하다고 가정한 상태에서 LLM 성능만 잰 것이고, 여기 나온 숫자는 **LLM 쪽
상한선**이다. 실제 RAG 를 붙여 같은 문항을 돌린 점수와의 차이가 검색이 깎아먹은
몫이 된다.

이렇게 나눈 이유는 두 가지다. 첫째, 둘을 섞으면 점수가 나빠졌을 때 검색을 고쳐야
할지 프롬프트를 고쳐야 할지 알 수 없다. 둘째, 실제 RAG 는 현재 검색 한 번에 30초가
걸려 {expected}문항 한 조건에 17분이 든다 — 프롬프트를 고쳐가며 비교하는 루프를
돌릴 수 없다.

측정 지표는 다음과 같다.

- **주제 정확도**: `chat.topic` 에 저장될 값이 정답 카테고리와 일치한 비율
- **묶음 일관성**: 패러프레이즈 묶음이 **하나의** 주제로 수렴한 비율.
  정답 여부와 별개다 — 틀리더라도 일관되게 틀리면 대시보드 도넛 차트는
  조각나지 않는다. 차트 신뢰도의 직접적 근거다.
- **지연**: p50 / p95. 스토리보드(13p) 의 5초 기준과 비교한다
- **한국어 이탈**: 답변의 한자가 한글의 10% 를 넘는 건수. 아래 3절 참조
- **비용**: `logs/metrics.jsonl` 의 실측 토큰 수로 환산 (1 USD = {USD_KRW:,}원)
""")

    if provider_rows:
        parts.append(f"""
## 2. 프로바이더 비교

{md_table(
    ["프로바이더", "모델", "주제 정확도", "묶음 일관성", "p50", "p95", "답변 길이", "에러", "한국어 이탈", "10k건 비용"],
    provider_rows,
)}
""")

    # --- 비용 분해 ---
    openai_final = next((r for r in finals if r.provider == "openai"), None)
    if openai_final:
        ap_, ac_ = run_tokens(openai_final, tokens)
        tp_, tc_ = TOPIC_CALL_TOKENS
        answer_cost = cost_per_10k("gpt-4o-mini", ap_, ac_)
        topic_cost = cost_per_10k("gpt-4o-mini", tp_, tc_)
        rate = PRICING["gpt-4o-mini"]
        assert rate
        total = (
            ((ap_ + tp_) * rate[0] + (ac_ + tc_) * rate[1]) / 1_000_000 * 10_000 * USD_KRW
        )
        parts.append(f"""
### 2.1 비용 분해 — `/v1/chat` 한 번은 API 를 두 번 부른다

{md_table(
    ["호출", "입력 토큰", "출력 토큰", "10,000건 비용"],
    [
        ["답변 생성", f"{ap_:,.0f}", f"{ac_:,.0f}", answer_cost],
        ["주제 분류", f"{tp_:,}", f"{tc_:,}", topic_cost],
        ["**합계**", f"**{ap_ + tp_:,.0f}**", f"**{ac_ + tc_:,.0f}**", f"**{total:,.0f}원**"],
    ],
)}

입력 토큰이 큰 이유는 참고 문서 5건을 프롬프트에 넣기 때문이다(문항당 약 4,000자).
출력은 200 토큰 안팎이라 비용의 대부분이 입력 쪽이다 — **답변을 짧게 만드는 것보다
검색 청크 수를 줄이는 쪽이 비용에 훨씬 크게 작용한다.**

주제 분류는 답변과 달리 참고 문서 본문을 넣지 않으므로(문서 *이름*만 힌트로 준다)
입력이 838 토큰으로 작다. 그래도 전체의 {(tp_ * rate[0] + tc_ * rate[1]) / ((ap_ + tp_) * rate[0] + (ac_ + tc_) * rate[1]) * 100:.0f}% 를 차지한다.

→ **주제 분류를 Qwen(로컬, 0원)으로 넘기면 이 몫이 통째로 사라진다.**
   4절에서 보듯 주제 분류는 Qwen 으로도 정확도가 비슷하고, enum 제약 디코딩
   덕분에 Qwen 의 언어 이탈 문제와도 무관하다.

> 계측 주석: `logs/metrics.jsonl` 은 답변 호출의 토큰만 남긴다(`classify()` 가
> 토큰을 반환하지 않는 인터페이스라서). 주제 분류 행은 같은 프롬프트로 별도
> 실측한 값이며, 근거는 `bench/report.py` 의 `TOPIC_CALL_TOKENS` 주석 참조.
> 2절 표의 "10k건 비용" 은 **답변 호출만** 반영한 값이다.
""")

    if history_rows:
        parts.append(f"""
## 3. 프롬프트 개선 이력 (OpenAI 기준)

{md_table(["조건", "주제 정확도", "p50", "답변 길이", "틀린 문항"], history_rows)}

### 3.1 카테고리는 이름만 주면 안 된다 — 88% → 97%

처음에는 카테고리 8종을 **이름만** 나열했다. 그러면 모델이 뜻을 몰라 글자 겹침으로
추측한다. 오답 4건 중 3건이 같은 원인이었다 — 질문에 "복무" 가 들어가면 무조건
`복무/징계` 로 갔다.

`복무/징계` 는 '비위·징계' 를 뜻하려고 지은 이름이지만, 한국어에서 "복무" 는
그냥 '근무한다' 는 뜻으로도 널리 쓰인다. 이름만으로는 구분이 안 되므로 각
카테고리의 경계를 문장으로 적었다(`app/prompts.py` 의 `_CATEGORY_GUIDE`).

중간 후보(`catdef`)는 없던 오답을 하나 만들었다. 채용/임용 정의에 "**인사관리**"
라고 썼다가 "직원 **인사** 규정" 문의를 빼앗긴 것으로, 이름만 주던 처음의 실수를
정의 안에서 반복한 셈이었다. `catdef2` 는 두 카테고리를 겹치지 않는 말로 갈랐다
— 채용/임용은 *들어오는 시점*, 인사/승진은 *들어온 뒤의 이동과 제도*.

예시를 덧붙인 `fewshot` 은 이득이 없었다(94% 로 동일). 프롬프트만 길어졌다.

### 3.2 개선폭이 실행 간 변동이 아님을 확인했다

`baseline` 을 한 번 더 돌린 것이 `baseline-r2` 다. **틀린 문항 ID 까지 똑같이**
재현됐다. enum 제약 디코딩과 `temperature=0` 덕분에 분류가 사실상 결정적이라는
뜻이고, 따라서 위 개선폭은 우연이 아니다.

### 3.3 남은 오답 1건은 라벨 자체가 경계 사례다

`hire-special-position`("별정직 직원은 어떻게 인사관리 하나요?") 은 정답을
`채용/임용` 으로 뒀지만 모델은 `인사/승진` 을 골랐다. 질문이 "인사관리" 를 묻고
있어 어느 쪽도 틀렸다고 하기 어렵다. **점수를 올리려고 라벨을 고치지는 않았다.**

### 3.4 출력 토큰 상한 (`ANSWER_MAX_TOKENS=500`)

프롬프트가 "3~6문장 이내" 를 요구하지만 이는 지시일 뿐이라 모델이 안 지킬 수 있다.
Qwen2.5:7b 는 한 문항에 2,415자를 **57초**에 걸쳐 뱉었다. 디코더 단에서 막으니
같은 조건에서 최대 지연이 57초 → 13.9초로 내려갔고 주제 정확도는 그대로였다.
OpenAI 도 {expected}문항 총 소요가 110초 → 65초로 줄었다.
""")

    if qwen_rows:
        parts.append(f"""
## 4. Qwen2.5:7b — 주제 분류는 되지만 답변 생성은 안 된다

{md_table(["조건", "주제 정확도", "한국어 이탈", "p50", "최대", "답변 길이"], qwen_rows)}

로컬 오픈소스 모델(Ollama, API 비용 0원)을 상용 API 와 같은 문항으로 비교했다.

**주제 분류는 쓸 만하다.** 정확도가 상용 모델과 1~2문항 차이고, Ollama 의 문법
제약 디코딩(`format` 에 JSON Schema)을 쓰므로 허용 목록 밖 값이 구조적으로
나올 수 없다. 출력이 8개 한국어 문자열 중 하나로 고정되므로 **아래의 언어 이탈
문제와도 무관하다.**

**답변 생성은 쓸 수 없다.** 한국어 질문에 중국어로 답한다. 한 건은 한자 1,601자 대
한글 132자로 사실상 전문이 중국어였다. 같은 프롬프트로 OpenAI 는 0건이었으므로
프롬프트 문제가 아니라 모델 고유의 성향이다.

프롬프트 맨 앞에 출력 언어 지시를 단독 문단으로 올려 완화를 시도했다(원래는
"답변 규칙" 4번에 묻혀 있었다). 이탈이 5건 → 3건으로 줄었지만 **없어지지는
않았다.** 사내 직원이 보는 화면에 9% 확률로 중국어가 나오는 것은 허용할 수 없다.

→ **결론: 답변 생성은 상용 API, 주제 분류는 Qwen** 이 합리적인 조합이다.
   주제 분류 호출이 전체 API 호출의 절반이므로 비용이 그만큼 줄어든다.
""")

    parts.append("""
## 5. Gemini 무료 티어로는 전체 측정이 불가능하다

`gemini-3.5-flash` 의 무료 티어 한도는 **하루 20회**
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, 값 20)다. 분당 한도가 아니라
일일 한도라 호출 간격을 늘려도 우회할 수 없다. 한 조건이 34문항 × 2호출 = 68회이므로
구조적으로 완주가 불가능하다 — 실제로 34문항 전부 429 로 실패했다.

한도는 모델별로 따로 잡히므로, 여유가 있는 `gemini-3.5-flash-lite` 로 바꿔 측정했다.
위 2절의 Gemini 수치는 이 모델 기준이다.

**이것은 테스트 환경 제약이지 서비스 결함이 아니다.** 유료 티어에서는 발생하지 않는다.
다만 서비스는 429 를 삼키지 않고 `LLM_RATE_LIMITED` + 한국어 안내 메시지로 변환해
반환하며, 그 처리 경로도 이번 측정에서 함께 검증됐다.

## 6. 한계

- 위 숫자는 **검색이 완벽할 때의 LLM 상한선**이다. 실제 RAG 연동 후 같은 문항을
  다시 돌려 비교해야 end-to-end 성능이 나온다 (1절 참조).
- 답변의 **사실 정확성은 자동 채점하지 않았다.** 주제 정확도와 근거 문서 포함
  여부만 기계적으로 재고, 답변 내용은 표본 수동 검수로 확인했다.
- 문항이 34개라 1문항이 약 3%p 다. 조건 간 3%p 이내 차이는 유의하다고 보기 어렵다.
- 스트리밍(`/v1/chat/stream`) 의 TTFT 는 이번 집계에 포함하지 않았다.
  비스트리밍 `/v1/chat` 이 기본 경로이기 때문이다.
""")

    if skipped:
        parts.append(
            "\n## 부록: 집계에서 제외한 파일\n\n"
            + "\n".join(f"- `{s}`" for s in skipped)
            + "\n\n중단된 실행을 그대로 섞으면 문항 수가 적어 정확도가 높아 보이는 착시가 생긴다.\n"
        )

    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--expected", type=int, default=34, help="완전한 실행의 문항 수")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    runs, skipped = load_runs(args.expected)
    if not runs:
        print("집계할 결과가 없습니다. 먼저 bench/run_bench.py 를 돌리세요.")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(runs, skipped, args.expected), encoding="utf-8")

    print(f"실행 {len(runs)}건 집계 → {out}")
    for run in runs:
        print(f"  {run.key:46s} 주제 {run.topic_correct}/{len(run.rows)}  에러 {run.errors}")
    for s in skipped:
        print(f"  (제외) {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
