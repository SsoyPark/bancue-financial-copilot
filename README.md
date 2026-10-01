# BANCUE 🏦

> 공식 금융 근거와 Gemini를 결합해 상담 답변 초안을 제공하는 은행 상담사 Copilot

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![React](https://img.shields.io/badge/React-TypeScript-61dafb)
![Gemini](https://img.shields.io/badge/Gemini-3.6_Flash-orange)
![Version](https://img.shields.io/badge/version-v0.3.0-315d93)

---

## 프로젝트 소개

금융 상담에서 빠른 답변보다 정확한 근거와 검토 가능한 과정이 중요하다고 보고 만든 상담 지원 프로토타입이다.

AI Hub 금융 상담 데이터를 처리해 상담 업무를 구성하고, 개인정보 마스킹과 위험도 분류를 거친 뒤 검증된 공식 자료를 검색한다. 검색 근거가 충분할 때만 Gemini가 답변 초안을 생성하며 최종 승인·반려·이관은 상담사가 결정한다.

---

## 주요 기능

- **대용량 데이터 처리** — ZIP 내부 JSON 155,262개 스트리밍 스캔, 은행 QA 45,000건 적재
- **분석 저장소** — DuckDB·Parquet 기반 배치 적재 및 데이터 품질 프로파일링
- **개인정보 보호** — 전화번호·이메일·주민등록번호·계좌번호 마스킹 후 LLM 호출
- **Gemini 상담 구조화** — 문의를 요약·의도·위험도·필수 확인 항목으로 변환하고 분석 신뢰도 표시
- **근거 검색** — 질의 확장, 최소 신뢰도 기준, 검색 중단 및 후보 점수 추적
- **공식 자료 관리** — 출처·게시일·시행일·적용 범위·검토 상태 관리
- **Gemini RAG** — 검증된 최상위 근거만 전달하고 출처가 포함된 답변 초안 생성
- **답변 품질 가드레일** — 근거 추적·PII·수치 근거·검토 안내·고위험 처리·완결성 자동 점검
- **Human-in-the-loop** — 상담사 승인·반려·이관과 1~5점 품질 피드백 저장

---

## 처리 흐름

```text
AI Hub ZIP/JSON
      ↓
스트리밍 ETL → DuckDB · Parquet
      ↓
개인정보 마스킹 · Gemini 구조화 분석 · 규칙 안전장치
      ↓
질의 확장 · 공식 근거 검색 · 신뢰도 게이트
      ↓
Gemini 근거 기반 답변 생성
      ↓
답변 품질 가드레일 · 프롬프트 버전 추적
      ↓
상담사 검토 · 승인 · 반려 · 이관 · 품질 피드백
```

근거가 없거나 검토 대기 문서만 검색된 경우에는 LLM을 호출하지 않는다. API 키 누락, 호출 실패 또는 불완전한 응답이 발생하면 검증 근거 기반 템플릿으로 복구한다.

---

## 데이터 처리 결과

| 항목 | 결과 |
|---|---:|
| 스캔한 JSON | 155,262개 |
| 적재한 은행 QA | 45,000건 |
| 고유 상담 원천 | 30,156건 |
| 질문·답변 누락 | 0건 |
| 개인정보 마스킹 | 112건 |
| 자동화 테스트 | 82개 통과 |

원본 AI Hub 데이터와 생성된 DuckDB·Parquet 파일은 저장소에 포함하지 않는다.

---

## 검색 품질 평가

질의 확장과 최소 신뢰도 기준을 적용하기 전후를 같은 정답셋으로 비교했다.

| 지표 | 기존 검색 | 개선 검색 |
|---|---:|---:|
| Recall@1 | 90% | 100% |
| MRR | 90% | 100% |
| 무응답 정확도 | 0% | 100% |
| 전체 정확도 | 60% | 100% |
| 오검색 | 5건 | 0건 |

위 수치는 정답 문서가 있는 질문 10개와 검색하면 안 되는 질문 5개로 구성한 **15개 파일럿 정답셋 기준**이다. 금융 상담 전체 성능이나 LLM 답변 정확도를 의미하지 않는다.

---

## 기술 스택

| 구분 | 기술 |
|---|---|
| Frontend | React · TypeScript · Vite |
| Backend | FastAPI · Python · Pydantic · httpx |
| AI/RAG | Gemini REST API · 구조화 상담 분석 · 근거 제한 프롬프트 · 품질 가드레일 |
| Data | DuckDB · Parquet · SQLite · AI Hub 금융 상담 JSON |
| Test | pytest · FastAPI TestClient · LLM 모킹 |

---

## 실행 방법

### API

```bash
cd apps/api
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
copy .env.example .env
# .env에 GEMINI_API_KEY 입력

python -m uvicorn app.main:app --reload --port 8000
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

- Web: `http://localhost:5173`
- API 문서: `http://localhost:8000/docs`

`.env`, 원본 데이터, DuckDB·Parquet 및 로컬 SQLite 파일은 GitHub에 업로드하지 않는다.

---

## 테스트

```bash
cd apps/api
python -m pytest -q
```

현재 테스트는 데이터 적재, 개인정보 마스킹, 위험도 분류, Gemini 구조화 분석, 근거 검색, 무응답 판단, 답변 품질 가드레일, Gemini 요청 형식, 오류 복구, 상담 처리와 품질 피드백 흐름을 포함한다.

---

## 개발자

**박소영** · AI/ML Engineer

- GitHub: [@SsoyPark](https://github.com/SsoyPark)
