# DesignSync — AI Design QA

디자인 원본과 개발 화면을 AI로 자동 비교하는 서비스.

---

## 빠른 시작

### 1. Gemini API 키 발급

1. [Google AI Studio](https://aistudio.google.com) 접속
2. "Get API Key" → 무료 API 키 생성
3. 아래 .env 파일에 입력

---

### 2. 백엔드 실행

```bash
cd backend

# 환경변수 설정
cp .env.example .env
# .env 파일 열어서 GEMINI_API_KEY 값 입력

# 가상환경 활성화 (최초 1회)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --reload --port 8000
```

서버 실행 후 → http://localhost:8000/health 접속해서 `{"status":"ok"}` 확인

---

### 3. 프론트엔드 실행

```bash
cd frontend

# 환경변수 설정
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# 패키지 설치
npm install

# 개발 서버 실행
npm run dev
```

브라우저에서 → http://localhost:3000 접속

---

## 사용 방법

1. 좌측에 **디자인 원본** 이미지 업로드 (Figma 익스포트 등)
2. 우측에 **개발 화면** 스크린샷 업로드
3. **AI 분석 시작** 클릭 (약 15~30초 소요)
4. 결과 화면에서 차이점 확인:
   - 마킹된 영역 클릭 → 상세 정보
   - **Approve**: 의도적 변경이면 승인
   - **Ignore**: 무시할 항목
5. **공유 링크 복사** → 개발자에게 전달

---

## 프로젝트 구조

```
LINE_QA/
├── PRD.md              # 제품 요구사항 문서
├── Todo.md             # 개발 태스크 보드
├── README.md           # 이 파일
├── frontend/           # Next.js 14 앱
│   └── src/
│       ├── app/        # 페이지 (App Router)
│       ├── components/ # 재사용 컴포넌트
│       └── lib/        # API 클라이언트, 타입
└── backend/            # FastAPI 앱
    ├── main.py         # 앱 진입점
    └── app/
        ├── api/        # 엔드포인트
        ├── services/   # AI 분석 로직
        ├── models/     # DB 모델
        └── core/       # 설정
```

---

## API 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| POST | `/api/analyze` | 이미지 업로드 + 분석 시작 |
| GET | `/api/analyze/{id}/status` | 분석 진행 상태 조회 |
| GET | `/api/analyze/{id}/result` | 분석 결과 조회 |
| PATCH | `/api/analyze/{id}/differences/{diffId}` | 차이점 상태 변경 |
| POST | `/api/share/{analysisId}` | 공유 링크 생성 |
| GET | `/api/share/{shortId}` | 공유 링크로 결과 조회 |

---

## Gemini API 키 없이 테스트

`.env` 에서 `GEMINI_API_KEY` 를 비워두면 Mock 분석 결과로 동작합니다.
UI 구조와 흐름을 먼저 확인할 수 있습니다.
