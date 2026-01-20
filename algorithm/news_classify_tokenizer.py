import re

FACTUAL_VERBS = {
    '말하다','밝히다','전하다','설명하다','주장하다','전해지다'
}

FACT_PATTERNS = {
    "에 따르면","전해졌다","밝혔다","확인됐다","발생했다","조사 결과","경찰은","검찰은","소방은","당국은","관계자는"
}

INSIGHT_KEYWORDS = {
    "의미","맥락","관점","해석","배경","평가",
    "논란","쟁점","문제","시사점","함의",
    "우려","비판","반박","옹호","핵심","본질","원인","영향","파장"
}

def tokenizer_fi(text: str):
    tokens = re.findall(r"[가-힣]{2,}", text)
    result = []

    text_has_fact_pattern = any(p in text for p in FACT_PATTERNS)
    for t in tokens:
        # Insight 키워드는 유지
        if t in INSIGHT_KEYWORDS:
            result.append(t)
        # Fact 패턴이 있는 기사라면
        # FACTUAL_VERBS도 제거하지 않고 유지
        elif text_has_fact_pattern:
            result.append(t)
        # Fact 패턴 없고, 서술 동사면 제거
        elif t in FACTUAL_VERBS:
            continue
        else:
            result.append(t)

    return result