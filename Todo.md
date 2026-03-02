# Todo — DesignSync 개발 Task Board

**마지막 업데이트:** 2026-02-28
**현재 단계:** Phase 1 — MVP (핵심 기능 구현 완료, 정확도 검증 단계)

---

## ✅ 완료된 작업 (Phase 1 MVP)

### 프로젝트 초기 세팅
- [x] Next.js 14 프로젝트 생성 (TypeScript, App Router)
- [x] Tailwind CSS 세팅
- [x] FastAPI 백엔드 프로젝트 생성
- [x] 환경변수 관리 (.env)
- [x] Claude Code launch.json 설정

### 이미지 업로드 UI (Frontend)
- [x] 메인 랜딩 페이지 레이아웃
- [x] 이미지 업로드 컴포넌트 (D&D + 클릭, 미리보기)
- [x] 파일 포맷/사이즈 유효성 검사 (PNG/JPG/WebP, 20MB)
- [x] 디자인 + 개발 2업로드 슬롯 UI
- [x] 분석 시작 버튼 및 로딩 상태

### 이미지 전처리 (Backend)
- [x] FastAPI 이미지 수신 엔드포인트 (`POST /api/analyze`)
- [x] 이미지 정규화 (작은 쪽 기준 리사이즈)
- [x] 비동기 분석 (BackgroundTasks)
- [x] Rate Limiting (IP당 시간당 20회)

### AI 분석 엔진
- [x] OpenCV SSIM 기반 픽셀 비교
- [x] Pixel diff 영역 세분화 알고리즘 (프로젝션 분할, 타이트 bbox)
- [x] Gemini Vision API 연동 + 모델 폴백 체인
- [x] **CV+AI 하이브리드 파이프라인** (v2.3)
  - [x] element_analyzer v2 (히스토그램 매칭, DP 순서보존)
  - [x] 상태바 트리밍 (`_trim_status_bar`, 상단 7%)
  - [x] 듀얼 bbox 시스템 (dev + design 좌표)
  - [x] Gemini 밴드 라벨링 (의미론적 이름)
  - [x] 비례적 심각도 (절대 px + 상대 비율)
  - [x] 겹치는 차이 병합

### 결과 시각화 (Frontend)
- [x] 결과 페이지 레이아웃
- [x] Side-by-side 이미지 뷰어 (SVG viewBox 기반)
- [x] 듀얼 bbox 렌더링 (design_bbox + fallback)
- [x] Single Focus Mode (선택 항목만 하이라이트)
- [x] 자동 #1 선택 (첫 진입 시)
- [x] 차이점 목록 사이드패널 (DiffList)
- [x] 기준값(파란) → 실제값(빨간) 칩 표시
- [x] 심각도 뱃지 (Critical/Major/Minor)
- [x] 유사도 점수 표시

### 리포트 & 공유
- [x] SQLite DB 저장 (Analysis, Difference, ShareLink)
- [x] 공유 링크 생성 (short_id 기반)
- [x] 공유 링크 조회 (만료일 설정)

### Approve/Ignore 워크플로우
- [x] 차이점 상태 변경 API (`PATCH /api/analyze/{id}/differences/{diff_id}`)
- [x] UI에서 상태 변경 반영

---

## 🔴 즉시 필요 (Priority 0) — 검증

- [ ] **새 분석 실행 후 듀얼 bbox 검증**
  - 디자인 패널에서 초록 박스가 올바른 크기/위치로 표시되는지
  - 개발 패널과 디자인 패널 모두 정확한 하이라이트 확인
- [ ] **상태바 트리밍 검증**
  - 상태바 포함 이미지에서 상태바 관련 오탐이 제거되는지
  - 상태바 경계를 걸치는 밴드가 올바르게 트리밍되는지
- [ ] **CV+AI 하이브리드 정확도 평가**
  - 최소 10쌍 테스트셋으로 Precision/Recall 측정
  - CV 간격 측정값과 실제 값 비교

---

## 🟠 단기 개선 (Priority 1) — UX & 품질

- [ ] 키보드 내비게이션 (↑↓ 화살표로 차이점 이동)
- [ ] AI 교차 검증 (CV 측정 결과를 AI가 2차 확인하여 오탐 제거)
- [ ] 로딩 화면 단계 세분화 (CV 측정 → AI 라벨링 → 시각 분석 → 완료)
- [ ] Gemini API 안정성 확보 (유료 플랜 또는 안정적 키)
- [ ] 이미지 크기 크게 다른 경우 (Retina 2x vs 1x) 전처리 보정

---

## 🟡 중기 기능 (Priority 2) — 확장

- [ ] Google OAuth 인증 (NextAuth.js)
- [ ] 분석 히스토리 페이지
- [ ] 마킹 이미지 다운로드/내보내기
- [ ] 결과 페이지 반응형 (모바일 대응)
- [ ] 결과 PDF 내보내기

---

## Phase 2: Growth (목표 기간: 3~4개월)

### 사용자 인증 & 히스토리
- [ ] NextAuth.js + Google OAuth
- [ ] 사용자 프로필 페이지
- [ ] 분석 히스토리 목록 (프로젝트별)
- [ ] 버전별 비교 뷰 (이전 vs 현재 분석 diff)
- [ ] QA 트렌드 대시보드

### 팀 협업
- [ ] 팀 워크스페이스 + 멤버 초대
- [ ] 권한 관리 (Admin / Editor / Viewer)
- [ ] 차이점 항목 코멘트 + @멘션

### 외부 도구 연동
- [ ] Figma API 연동 (프레임 직접 가져오기)
- [ ] Jira/Linear 연동 (차이점 → 이슈 자동 생성)
- [ ] Slack 알림 웹훅

---

## Phase 3: Scale (목표 기간: 5~6개월)

### CI/CD 연동
- [ ] REST API 공개 (`/api/v1/analyze`)
- [ ] GitHub Actions 공식 Action
- [ ] 배포 시 자동 스크린샷 + QA 실행

### AI 고도화
- [ ] Approve 패턴 학습 → 자동 화이트리스트
- [ ] 다국어 UI 텍스트 비교
- [ ] 반응형 다중 해상도 비교

### Enterprise
- [ ] SSO (SAML 2.0)
- [ ] 온프레미스 배포 (Docker Compose)
- [ ] 감사 로그 + SLA 보장

---

## 작업 우선순위 매트릭스

| Task | Impact | Effort | Priority |
|------|--------|--------|----------|
| 듀얼 bbox + 상태바 검증 | High | Low | 🔴 P0 |
| CV+AI 정확도 평가 | High | Medium | 🔴 P0 |
| 키보드 내비게이션 | Medium | Low | 🟠 P1 |
| AI 교차 검증 | High | Medium | 🟠 P1 |
| 로딩 단계 세분화 | Medium | Low | 🟠 P1 |
| Google OAuth 인증 | Medium | Medium | 🟡 P2 |
| 분석 히스토리 | Medium | Medium | 🟡 P2 |
| Figma 연동 | High | High | 🟡 P2 |
| CI/CD 연동 | High | High | ⚪ P3 |

---

## 정의 of Done (DoD)

각 기능은 아래 조건을 모두 충족해야 완료로 간주:

- [ ] 기능 구현 완료
- [ ] 단위 테스트 작성 (커버리지 70% 이상)
- [ ] E2E 테스트 시나리오 통과
- [ ] 코드 리뷰 완료 (PR approved)
- [ ] Staging 환경 배포 및 검증
- [ ] 문서 업데이트 (API 문서, README)
