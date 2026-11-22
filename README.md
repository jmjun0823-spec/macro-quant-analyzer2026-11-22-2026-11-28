# 11월 4주차 매크로 및 계절성 정량 검증 (`week4-nov-macro-quant`)

글에서 제시한 핵심 시나리오—① 한·미 통화정책 및 금리·환율 민감도, ② 추수감사절 주간 거래량 급감 및 변동성 아노말리, ③ 연말 북클로징·배당 차익거래와 대형/고배당 vs 코스닥/중소형 수급 로테이션, ④ 원/달러 환율 국면별 코스피·반도체 민감도—를 최장기 시계열 데이터로 입증하는 종합 파이프라인입니다[cite: 1].

## 빠른 실행

```bash
pip install -r requirements.txt
pytest -v tests/
python -m src.main
