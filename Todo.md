# Todo — DesignSync 개발 Task Board

**마지막 업데이트:** 2026-02-26
**현재 단계:** Phase 1 — MVP

---

## Phase 1: MVP (목표 기간: 0~2개월)

### 1-1. 프로젝트 초기 세팅

- [ ] Next.js 14 프로젝트 생성 (TypeScript, App Router)
- [ ] Tailwind CSS 세팅
- [ ] FastAPI 백엔드 프로젝트 생성
- [ ] 모노레포 구조 세팅 (apps/web, apps/api)
- [ ] ESLint / Prettier / Husky 설정
- [ ] GitHub 레포지토리 생성 및 브랜치 전략 수립
- [ ] 환경변수 관리 (.env.example 작성)
- [ ] Vercel / Railway 배포 파이프라인 초기 연결

---

### 1-2. 이미지 업로드 UI (Frontend)

- [ ] 메인 랜딩 페이지 레이아웃 작성
- [ ] 이미지 업로드 컴포넌트 제작
  - [ ] 드래그 앤 드롭 (react-dropzone)
  - [ ] 클릭하여 파일 선택
  - [ ] 업로드 전 미리보기 (썸네일)
  - [ ] 파일 포맷 / 사이즈 유효성 검사 (PNG/JPG/WebP, 20MB 이하)
- [ ] 디자인 이미지 + 개발 이미지 2업로드 슬롯 UI
- [ ] 분석 시작 버튼 및 로딩 상태 표시
- [ ] 업로드 진행률 바

---

### 1-3. 이미지 전처리 (Backend)

- [ ] FastAPI 이미지 수신 엔드포인트 (`POST /api/analyze`)
- [ ] AWS S3 이미지 업로드 연동
- [ ] 이미지 전처리 모듈
  - [ ] 이미지 해상도 정규화 (같은 크기로 맞추기)
  - [ ] 이미지 정렬 보정 (기준점 맞추기)
  - [ ] 포맷 통일 (PNG 변환)
- [ ] 비동기 분석 Job 큐 구성 (Redis + Bull / Celery)

---

### 1-4. AI 분석 엔진 (핵심)

- [ ] **Layer 1: 픽셀 차이 분석**
  - [ ] OpenCV SSIM 기반 픽셀 비교 구현
  - [ ] 차이 영역 바운딩 박스 추출
  - [ ] 차이 마스크 이미지 생성

- [ ] **Layer 2: Vision LLM 시맨틱 분석**
  - [ ] Claude Vision API 연동 (`claude-opus-4-6`)
  - [ ] 프롬프트 엔지니어링
    - [ ] UI 요소 분류 (버튼, 텍스트, 이미지, 아이콘 등)
    - [ ] 차이 속성 추출 (색상, 폰트, 크기, 간격)
    - [ ] 심각도 판단 로직 (Critical / Major / Minor)
  - [ ] 응답 JSON 파싱 및 구조화

- [ ] **결과 데이터 모델 설계**
  ```json
  {
    "analysisId": "uuid",
    "differences": [
      {
        "id": 1,
        "category": "Typography",
        "severity": "Major",
        "description": "버튼 폰트 크기 차이",
        "designValue": "16px",
        "devValue": "14px",
        "boundingBox": { "x": 100, "y": 200, "w": 120, "h": 40 }
      }
    ],
    "summary": { "critical": 1, "major": 3, "minor": 5 },
    "similarityScore": 87.5
  }
  ```

---

### 1-5. 결과 시각화 (Frontend)

- [ ] 결과 페이지 레이아웃
- [ ] Side-by-side 이미지 뷰어
  - [ ] 두 이미지 나란히 표시
  - [ ] 차이점 오버레이 마킹 (빨간 테두리 박스)
  - [ ] 마킹 클릭 시 상세 팝업
- [ ] 슬라이더 오버레이 모드 (마우스로 두 이미지 전환)
- [ ] 차이점 목록 사이드패널
  - [ ] 카테고리별 그룹핑 (Typography / Color / Spacing / Layout)
  - [ ] 심각도 뱃지 (Critical: 빨강 / Major: 주황 / Minor: 노랑)
  - [ ] 목록 아이템 클릭 시 해당 마킹으로 스크롤/하이라이트
- [ ] 유사도 점수 시각화 (%)

---

### 1-6. 리포트 & 공유

- [ ] 분석 결과 PostgreSQL 저장
- [ ] 고유 공유 링크 생성 (`/report/[uuid]`)
- [ ] 공유 링크 유효 기간 설정 (7일 / 30일 / 영구)
- [ ] 결과 PNG 내보내기 (html2canvas)
- [ ] 결과 PDF 내보내기

---

### 1-7. 기본 인프라

- [ ] PostgreSQL 스키마 설계 및 마이그레이션 (Prisma)
  - [ ] analyses 테이블
  - [ ] differences 테이블
  - [ ] share_links 테이블
- [ ] Redis 캐싱 레이어 구성
- [ ] API Rate Limiting (무료 사용자 월 10회 제한)
- [ ] 에러 핸들링 및 로깅 (Sentry)
- [ ] 헬스체크 엔드포인트

---

## Phase 2: Growth (목표 기간: 3~4개월)

### 2-1. 사용자 인증

- [ ] NextAuth.js 설정
- [ ] Google OAuth 연동
- [ ] GitHub OAuth 연동
- [ ] 사용자 프로필 페이지
- [ ] 무료/Pro 플랜 사용량 추적

---

### 2-2. 프로젝트 & 히스토리

- [ ] 프로젝트 생성/관리 CRUD
- [ ] 분석 히스토리 목록 (프로젝트별)
- [ ] 버전별 비교 뷰 (이전 분석과 현재 분석 diff)
- [ ] 대시보드 (QA 현황, 트렌드 차트)

---

### 2-3. 팀 협업

- [ ] 팀 워크스페이스 생성
- [ ] 팀원 초대 (이메일)
- [ ] 권한 관리 (Admin / Editor / Viewer)
- [ ] 차이점 항목에 코멘트 기능
- [ ] @멘션 알림 (이메일 / 슬랙)

---

### 2-4. Figma 연동

- [ ] Figma OAuth 연동
- [ ] Figma API로 프레임 직접 불러오기
- [ ] Figma 프레임 → 분석 자동 연결

---

### 2-5. 이슈 트래커 연동

- [ ] Jira 연동 (차이점 → 이슈 자동 생성)
- [ ] Linear 연동
- [ ] Slack 알림 웹훅

---

## Phase 3: Scale (목표 기간: 5~6개월)

### 3-1. CI/CD 연동

- [ ] REST API 공개 (`/api/v1/analyze`)
- [ ] GitHub Actions 공식 Action 제공
- [ ] Jenkins / GitLab CI 가이드 및 플러그인
- [ ] 배포 시 자동 스크린샷 캡처 (Playwright 연동)
- [ ] QA 실패 시 PR 블로킹 옵션

---

### 3-2. AI 고도화

- [ ] 분석 정확도 피드백 루프 (사용자 정오답 입력)
- [ ] 화이트리스트 학습 (의도적 변경 패턴 기억)
- [ ] 다국어 UI 텍스트 비교 지원
- [ ] 반응형 화면 비교 (모바일/태블릿/데스크탑)

---

### 3-3. Enterprise

- [ ] SSO (SAML 2.0)
- [ ] 온프레미스 배포 옵션 (Docker Compose)
- [ ] 감사 로그 (Audit Log)
- [ ] SLA 보장 및 전용 지원

---

## 작업 우선순위 매트릭스

| Task | Impact | Effort | Priority |
|------|--------|--------|----------|
| AI 분석 엔진 | High | High | 🔴 P0 |
| 이미지 업로드 UI | High | Low | 🔴 P0 |
| 결과 시각화 | High | Medium | 🔴 P0 |
| 공유 링크 | Medium | Low | 🟠 P1 |
| 사용자 인증 | Medium | Medium | 🟠 P1 |
| Figma 연동 | High | High | 🟡 P2 |
| CI/CD 연동 | High | High | 🟡 P2 |
| 팀 협업 | Medium | High | 🟡 P2 |

---

## 정의 of Done (DoD)

각 기능은 아래 조건을 모두 충족해야 완료로 간주:

- [ ] 기능 구현 완료
- [ ] 단위 테스트 작성 (커버리지 70% 이상)
- [ ] E2E 테스트 시나리오 통과
- [ ] 코드 리뷰 완료 (PR approved)
- [ ] Staging 환경 배포 및 검증
- [ ] 문서 업데이트 (API 문서, README)
