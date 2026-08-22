# BANCUE 🏦

> 공식 근거를 바탕으로 은행 상담의 위험도와 답변 초안을 제공하는 상담사 Copilot

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![React](https://img.shields.io/badge/React-TypeScript-61dafb)
![SQLite](https://img.shields.io/badge/SQLite-3-003b57)
![Version](https://img.shields.io/badge/version-v0.1.0-orange)

---

## 프로젝트 소개

금융 상담에서 답변 속도보다 **정확한 근거와 검토 가능한 과정**이 중요하다고 보고 만든 로컬 MVP이다.

상담 데이터를 불러오면 개인정보를 마스킹하고, 위험도를 분류한 뒤 공식 공개자료에서 관련 근거를 검색한다. 검증된 근거가 있을 때만 답변 초안을 생성하며 최종 승인·반려·이관은 상담사가 결정하도록 설계했다.

현재 버전은 검색 과정과 판단 이유를 직접 확인할 수 있는 **설명 가능한 규칙 기반 MVP**이며 외부 LLM은 사용하지 않는다.

---

## 주요 기능

- **상담 관리** — 상담 목록 조회, 상세 확인, 처리 상태 저장
- **개인정보 보호** — 전화번호·이메일·주민등록번호·계좌번호 마스킹
- **위험도 분류** — 규칙 ID와 판정 이유를 함께 제공
- **근거 문서 검색** — 검증된 공식 공개자료만 검색하고 출처 표시
- **답변 초안 생성** — 근거가 있을 때만 초안 생성, 고위험 상담은 승인 차단
- **품질 피드백** — 의도 파악·초안 정확도를 1~5점으로 평가하고 개선 사유 집계

---

## 처리 흐름

```text
상담 데이터 입력
      ↓
개인정보 마스킹 · 위험도 분류
      ↓
질의 확장 · 근거 문서 검색
      ↓
근거 기반 답변 초안 생성
      ↓
상담사 승인 · 반려 · 관리자 이관
      ↓
품질 피드백 저장
```

검색에 사용된 확장 용어, 일치 키워드, 후보별 점수와 검색 중단 이유를 화면에서 확인할 수 있다.

---

## 검색 품질 개선

단순 키워드 검색에서 발생한 오검색을 줄이기 위해 금융 용어 질의 확장과 최소 점수 기준을 추가했다.

| 지표 | 기존 | 개선 |
|---|---:|---:|
| Recall@1 | 90% | 100% |
| 무응답 정확도 | 0% | 100% |
| 전체 정확도 | 60% | 100% |

위 결과는 공식 공개자료 요약 5개와 정답셋 15개에 한정된 로컬 평가 결과이다. 실제 금융 상담 전체의 성능을 의미하지 않는다.

---

## 기술 스택

| 구분 | 기술 |
|---|---|
| Frontend | React · TypeScript · Vite |
| Backend | FastAPI · Python · Pydantic |
| Database | SQLite |
| Test | pytest |
| Data | AI Hub 금융 상담 JSON · 공식 공개자료 요약 |

---

## 실행 방법

### API

```bash
cd apps/api
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
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

기본 실행에서는 `apps/api/data/sample`의 합성 데이터를 사용한다. 실제 AI Hub JSON 폴더를 연결하려면 API 실행 전에 환경변수를 지정한다.

```bat
set BANCUE_DATA_DIR=C:\데이터\은행_JSON_폴더
set BANCUE_DATA_LIMIT=200
```

원본 데이터와 SQLite DB는 GitHub에 업로드되지 않는다.

---

## 테스트

```bash
cd apps/api
python -m pytest -q
```

상담 조회부터 근거 검색, 답변 검토, 피드백 저장까지의 통합 흐름을 포함한다. 면접용 시연 순서는 [`docs/DEMO.md`](docs/DEMO.md)에 정리했다.

---

## 개발자

**박소영** · AI/ML Engineer

- GitHub: [@SsoyPark](https://github.com/SsoyPark)
