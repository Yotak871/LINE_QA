# PRD: DesignSync — AI-Powered Design QA Automation

**Version:** 2.2
**Date:** 2026-02-27
**Author:** Product Team
**Status:** MVP Development In Progress

> v2.2 변경: 구현 현황 문서화, 프로젝트 구조/실행 가이드/트러블슈팅 추가, Pixel Diff 세분화 알고리즘 스펙 추가
> v2.1 변경: bbox 좌표 시스템 명세 추가, Gemini Vision API 연동 확정, SVG viewBox 매핑 스펙 추가
> v2.0 변경: 블로커 5개 해소 (기술 스택 확정 / Auth MVP 포함 / 과금 모델 수정 / Approve 워크플로우 추가 / 정확도 정의 추가)
> + 심각도 기준 정의 / 에러 케이스 스펙 / 경쟁사 분석 / FRE 추가

---

## 1. Executive Summary

DesignSync는 Product Designer와 개발자 간의 UI 싱크 검증 프로세스를 AI로 자동화하는 서비스다.
디자이너가 디자인 원본 이미지와 개발 배포 스크린샷을 업로드하면, AI가 차이점을 자동으로 감지·마킹하고
구체적인 피드백 리포트를 생성한다. 디자이너는 차이점을 승인(Approve) 또는 무시(Ignore) 처리하여
의도적 변경과 실수를 구분할 수 있다.

---

## 2. Problem Statement

### 현재 Pain Point

| 문제 | 영향 |
|------|------|
| 배포마다 수동으로 디자인-개발 화면 비교 | 디자이너 1인당 배포 1회당 평균 30~60분 소요 |
| 육안 비교로 인한 누락 발생 | 색상값, 폰트 굵기 등 미세 차이 놓침 |
| 비동기 커뮤니케이션 비용 | 슬랙/지라 이슈 등록, 재배포 요청 사이클 반복 |
| 기준 문서 부재 | 의도적 변경인지 실수인지 히스토리 없음 |

### Opportunity Size
- 대상: Product Designer, FE Developer, QA Engineer
- 디자이너 1인 월 평균 QA 시간: ~20시간
- 자동화 시 예상 절감: 80% 이상

---

## 3. Goals & Success Metrics

**Objective:** Design QA 프로세스를 자동화하여 팀 생산성을 높인다.

| Key Result | 측정 방법 | Target (6개월) |
|-----------|----------|---------------|
| QA 소요 시간 감소 | 사용 전후 설문 | 60분 → 5분 이하 |
| 차이점 감지 정확도 | 내부 테스트셋 기준 Precision/Recall | Precision 90%+ / Recall 95%+ |
| False Positive율 | 테스트셋 측정 | 10% 이하 |
| NPS | 월 1회 인앱 설문 | 50 이상 |
| MAU | 분석 실행 기준 | 1,000 |
| D30 Retention | 코호트 분석 | 40% 이상 |

### 정확도 정의 (B-2 해소)

```
True Positive  (TP): 실제 차이가 있고, AI가 차이로 감지한 경우
False Positive (FP): 실제 차이가 없는데, AI가 차이로 감지한 경우 ← 노이즈
False Negative (FN): 실제 차이가 있는데, AI가 놓친 경우          ← 치명적 누락

Precision = TP / (TP + FP)  → 감지한 것 중 진짜 차이 비율
Recall    = TP / (TP + FN)  → 실제 차이 중 잡아낸 비율

목표: Precision 90%+, Recall 95%+
      (놓치는 것이 FP보다 훨씬 심각하므로 Recall에 더 높은 기준)

테스트셋: 사내 디자이너가 수동 라벨링한 50쌍 기준 이미지 세트로 측정
```

---

## 4. Competitive Analysis

| 경쟁사 | 주요 강점 | 주요 약점 | DesignSync 차별점 |
|--------|---------|---------|-----------------|
| Percy | CI/CD 통합 성숙, Storybook 지원 | 디자이너 UX 전무, 개발자 전용 | 디자이너 중심 워크플로우, 이미지 업로드만으로 시작 |
| Chromatic | Storybook 컴포넌트 단위 비교 | 컴포넌트 기반 프로젝트만 가능 | 프레임워크 무관, 스크린샷 기반 |
| Applitools | AI 비주얼 테스트 정확도 높음 | 가격 높음($500+/월), 설정 복잡 | 저렴하고 즉시 사용 가능 |
| Figma (내장 비교) | 디자이너 친화적 | 개발 화면 비교 불가, Figma 안에서만 | 개발 결과물과 직접 비교 가능 |

**포지셔닝:** "설정 없이 이미지 2장으로 즉시 시작하는 디자이너 전용 QA 도구"

---

## 5. User Journey (Core Flow)

### 5.1 신규 사용자 FRE (First Run Experience)

```
[랜딩 페이지]
  ├── Hero: "디자인과 개발, 한눈에 비교하세요"
  ├── [샘플로 체험해보기] 버튼 → 샘플 이미지 2장 자동 로드 후 분석 실행
  └── [직접 시작하기] 버튼 → 업로드 화면으로
         │
         ▼ (첫 업로드 화면)
  - 좌: "디자인 원본" 업로드 영역 + 툴팁 ("Figma Export나 캡처본을 올려주세요")
  - 우: "개발 화면" 업로드 영역 + 툴팁 ("배포된 화면의 스크린샷을 올려주세요")
  - 하단: 단계 가이드 (1. 업로드 → 2. 분석 → 3. 결과 확인)
```

### 5.2 핵심 사용 플로우 (MVP)

```
[로그인 / 회원가입]  ← MVP 포함 (Google OAuth)
        │
        ▼
[홈 대시보드]
  ├── 최근 분석 목록
  └── [새 분석 시작] 버튼
        │
        ▼
[이미지 업로드]
  ├── 디자인 이미지 + 개발 스크린샷 업로드
  ├── 이미지 크기 불일치 감지 시 → 정렬 옵션 선택 UI
  └── [분석 시작] 버튼
        │
        ▼
[분석 중 화면]
  ├── 진행 상태 바 (전처리 → 픽셀 분석 → AI 분석 → 완료)
  └── 예상 소요 시간 표시
        │
        ▼
[결과 리포트]
  ├── Side-by-side 이미지 뷰 + 마킹
  ├── 차이점 목록 (카테고리 / 심각도별)
  ├── 각 항목: [승인 Approve] / [무시 Ignore] / [코멘트] 액션
  └── [공유 링크 생성] / [내보내기]
        │
        ▼
[피드백 루프]
  └── 공유 링크로 개발자 전달
```

### 5.3 에러 / 엣지 케이스 플로우 (M-2 해소)

| 상황 | 감지 시점 | 사용자에게 보여주는 것 |
|------|---------|-------------------|
| 이미지 포맷 오류 | 업로드 즉시 | "지원하지 않는 형식입니다. PNG, JPG, WebP만 가능합니다" |
| 이미지 20MB 초과 | 업로드 즉시 | "파일이 너무 큽니다. 20MB 이하로 올려주세요" |
| 완전히 다른 화면 업로드 | 분석 후 | "두 이미지가 동일한 화면으로 보이지 않습니다. 올바른 이미지인지 확인해주세요" + [계속 진행] |
| Claude API 타임아웃 | 분석 60초 초과 | "분석이 지연되고 있습니다. 잠시 후 자동으로 재시도합니다" + 재시도 1회 자동 실행 |
| Claude API 다운 | 분석 실패 | "현재 AI 분석 서비스가 일시적으로 불가합니다. 픽셀 비교 결과만 제공합니다" (Fallback) |
| 이미지 파일 손상 | 전처리 단계 | "이미지 파일이 손상되었습니다. 다시 업로드해주세요" |
| 분석 도중 연결 끊김 | WebSocket 감지 | 재접속 시 진행 중이던 분석 상태 자동 복원 |

---

## 6. Feature Requirements

### 6.1 MVP (Phase 1) — Must Have

#### F-01: 사용자 인증 (B-4 해소 — MVP 포함)
- Google OAuth (NextAuth.js)
- 로그인 없이 "샘플 체험" 가능 (분석 결과 저장 안 됨)
- 로그인 시 분석 히스토리 자동 저장

#### F-02: 이미지 업로드
- 드래그 앤 드롭 + 클릭 업로드
- 지원 포맷: PNG, JPG, WebP
- 최대 파일 크기: 20MB per image
- 업로드 후 즉시 미리보기
- **이미지 크기 불일치 처리 (M-1 해소):**
  - 두 이미지 해상도 자동 감지
  - 옵션 A: 작은 쪽 기준으로 리사이즈 (기본값)
  - 옵션 B: 사용자가 기준 이미지 직접 선택
  - 2x/1x (Retina) 스케일 차이 자동 감지 및 보정
  - 스크롤 페이지 (세로 길이 2000px 이상): 분할 비교 안내

#### F-03: AI 차이점 분석
- **Layer 1 — 픽셀 비교:** OpenCV SSIM
- **Layer 2 — 시맨틱 분석:** Claude Vision API (`claude-opus-4-6`)
- **Layer 3 — 속성 수치화:** 색상(HEX), 크기(px), 간격(px) 차이 명시
- **Fallback:** Claude API 장애 시 Layer 1 결과만 제공
- 분석 완료 시간: 30초 이내 (P95)

#### F-04: 심각도 분류 기준 (B-2 + M-3 해소)

| 심각도 | 기준 | 예시 |
|--------|------|------|
| 🔴 Critical | UI 요소 누락, 클릭 불가 영역 오류, 텍스트 완전 오표시 | 버튼 자체가 없음, CTA 텍스트가 다른 문구 |
| 🟠 Major | 색상 차이 ΔE > 10, 폰트 크기 ±2px 이상, 레이아웃 위치 ±8px 이상 | 브랜드 컬러 오적용, 헤딩 14px→12px |
| 🟡 Minor | 색상 차이 ΔE ≤ 10, 간격 ±1~4px, 폰트 굵기 한 단계 차이 | 여백 1px 차이, 그림자 강도 미세 차이 |

> ΔE (Delta-E): 색상 차이 국제 표준 단위. ΔE > 10이면 육안으로도 명확히 다름

#### F-05: 결과 시각화
- **Side-by-side 뷰:** 두 이미지 나란히 + 차이 마킹
  - 마킹 색상: 빨간색 (기본) / 주황색 (Major) / 노란색 (Minor)
  - 색맹 대응: 패턴 오버레이 옵션 제공 (색상 외 테두리 패턴으로 구분)
- **Overlay 슬라이더 뷰:** 마우스 드래그로 두 이미지 전환
- **줌 기능:** 마우스 휠 또는 핀치 줌으로 최대 400% 확대
- **마킹 클릭:** 해당 차이 항목 상세 팝업 (카테고리, 심각도, 수치)

#### F-06: Approve / Ignore 워크플로우 (B-5 해소)
각 차이점 항목에 대해:
- **[Approve]:** "의도적 변경 — 정상" 처리. 마킹이 초록색으로 변하고 목록에서 분리
- **[Ignore]:** "이 항목 무시" 처리. 마킹이 회색으로 변하고 이후 분석에서 제외 옵션
- **[Issue]:** 해결 필요 (기본 상태, 빨간 마킹 유지)
- 상태 변경 이력 저장 (누가, 언제 Approve 했는지)
- 다음 분석 시 이전 Approve 목록과 자동 대조

#### F-07: 리포트 생성
- 차이점 목록: Typography / Color / Spacing / Layout / Missing Elements
- 요약 카드: Critical N개 / Major N개 / Minor N개 / Approved N개
- 유사도 점수: SSIM 기반 0~100%
- 차이점 수치 명시 (예: `버튼 height 40px → 36px (-4px)`)

#### F-08: 공유 기능
- 고유 링크 생성 (`/r/[shortId]`)
- 링크 유효 기간: 7일 / 30일 / 영구
- 링크 접근자: 로그인 불필요 (뷰 전용)
- 결과 PNG 내보내기
- 결과 PDF 내보내기

### 6.2 Phase 2 — Should Have

#### F-09: 프로젝트 관리
- 프로젝트별 분석 히스토리
- 버전별 비교 (이전 분석과 현재 분석 diff)
- QA 트렌드 대시보드

#### F-10: 팀 협업
- 팀 워크스페이스 및 멤버 초대
- 권한: Admin / Editor / Viewer
- 차이점 항목 코멘트 + @멘션

#### F-11: 외부 도구 연동
- Figma API: 프레임 직접 불러오기
- Jira / Linear: 차이점 → 이슈 자동 생성
- Slack: 분석 완료 알림

### 6.3 Phase 3 — Could Have

#### F-12: CI/CD 파이프라인 연동
- REST API 공개
- GitHub Actions 공식 Action
- 배포 시 자동 스크린샷 + QA 실행

#### F-13: AI 고도화
- Approve 패턴 학습 → 자동 화이트리스트
- 다국어 UI 텍스트 비교
- 반응형 다중 해상도 비교

---

## 7. Technical Architecture

### 7.1 전체 구조

```
┌─────────────────────────────────────────────────────────┐
│                 Frontend (Next.js 14)                    │
│  - 이미지 업로드 / 결과 시각화 / 리포트 뷰어            │
│  - Canvas: Konva.js (마킹 인터랙션)                     │
└────────────────────────┬────────────────────────────────┘
                         │ REST API + WebSocket (상태 폴링)
┌────────────────────────▼────────────────────────────────┐
│               Backend (FastAPI + Python)                  │
│  - 이미지 수신 및 전처리                                 │
│  - 분석 Job 생성 및 결과 반환                            │
│  - 공유 링크 / 리포트 관리                               │
└──────────────┬─────────────────────┬────────────────────┘
               │                     │
┌──────────────▼──────┐   ┌──────────▼──────────────────┐
│  AI 분석 엔진       │   │  Storage Layer               │
│  (Celery Worker)    │   │                              │
│  - OpenCV SSIM      │   │  - AWS S3 (이미지)           │
│  - Claude Vision    │   │  - PostgreSQL (리포트/유저)  │
│    API 호출         │   │  - Redis (Job 큐 / 캐시)     │
└─────────────────────┘   └──────────────────────────────┘
```

> **[B-1 해소]** 백엔드 Python 단일 스택으로 확정.
> Bull(Node.js) 제거 → **Celery + Redis** 로 통일.

### 7.2 AI 분석 파이프라인

```
Input: [Design Image] + [Dev Screenshot]
        │
        ▼
[Step 1] 전처리 (Python / Pillow)
  - 해상도 정규화 (기준: 작은 이미지 크기)
  - Retina 스케일 보정 (2x → 1x 다운샘플)
  - PNG 통일 변환
        │
        ▼
[Step 2] 픽셀 비교 (OpenCV)
  - SSIM 계산 → 유사도 점수
  - 차이 마스크 생성 → 바운딩 박스 추출
        │
        ▼
[Step 3] Vision LLM 분석 (Claude Vision API)
  - 입력: 원본 이미지 + 개발 이미지 + 차이 마스크 이미지
  - 출력: 각 차이 영역별 { 카테고리, 심각도, 설명, 수치 }
  - 타임아웃: 45초 → 초과 시 Step 2 결과만으로 Fallback
        │
        ▼
[Step 4] 결과 구조화
  - JSON 리포트 생성
  - 마킹 이미지 생성 (심각도별 색상 적용)
  - PostgreSQL 저장
```

### 7.3 데이터 모델

```sql
-- 사용자
users (id, email, name, avatar_url, plan, created_at)

-- 분석
analyses (
  id, user_id, title,
  design_image_url, dev_image_url, marked_image_url,
  similarity_score, status,  -- pending/processing/done/failed
  created_at
)

-- 차이점 항목
differences (
  id, analysis_id,
  category,    -- typography/color/spacing/layout/missing
  severity,    -- critical/major/minor
  description, design_value, dev_value,
  bbox_x, bbox_y, bbox_w, bbox_h,
  status,      -- issue/approved/ignored
  status_by, status_at,
  created_at
)

-- 공유 링크
share_links (
  id, analysis_id, short_id,
  expires_at, created_at
)
```

### 7.4 Annotation 좌표 시스템 (v2.1 추가)

```
┌── 핵심 원칙 ──────────────────────────────────────────────────┐
│ 모든 bbox 좌표는 DEV(개발) 이미지의 원본 픽셀 기준이다.       │
│ Design 이미지에 표시할 때는 비율 스케일링으로 매핑한다.        │
└───────────────────────────────────────────────────────────────┘

[문제 정의]
  - Design 이미지 (390×844) ≠ Dev 이미지 (375×812) → 크기가 다를 수 있음
  - AI(Gemini)가 반환하는 bbox는 DEV 이미지의 원본 pixel 좌표
  - 프론트엔드에서 이미지가 축소 표시되면 좌표가 안 맞음

[해결: 3단계 좌표 파이프라인]

  ① Backend — 정규화 좌표 → 원본 좌표 변환
     pixel_diff는 정규화(리사이즈) 이미지에서 실행
     → scale_regions_to_original()로 원본 dev 이미지 좌표로 변환
     → Gemini에 원본 이미지 + 원본 크기 정보 전달

  ② Backend API — 응답에 이미지 크기 포함
     GET /api/analyze/{id}/result 응답에 추가:
     {
       "dev_image_size":    { "width": 375, "height": 812 },
       "design_image_size": { "width": 390, "height": 844 },
       ...
       "differences": [{ "bbox_x": 40, "bbox_y": 300, ... }]
     }
     → bbox 좌표는 dev_image_size 기준

  ③ Frontend — SVG viewBox 기반 자동 스케일링
     <img src={devUrl} />
     <svg viewBox="0 0 {dev_width} {dev_height}" class="absolute inset-0 w-full h-full">
       <rect x={bbox_x} y={bbox_y} ... />    ← 원본 픽셀 좌표 그대로 사용
     </svg>
     → viewBox가 이미지 축소/확대와 무관하게 좌표 매핑
     → Design 이미지에는 비율 변환:
        design_bbox_x = bbox_x × (design_width / dev_width)
        design_bbox_y = bbox_y × (design_height / dev_height)
```

**이미지 크기 불일치 매핑 규칙:**

| 상황 | 처리 방법 |
|------|---------|
| 두 이미지 크기 동일 | bbox 좌표 그대로 사용 |
| 크기 다름 (같은 비율) | 비율 스케일링 (dev→design 비율 곱하기) |
| 크기 다름 (다른 비율) | 비율 스케일링 + 넘침 시 클램핑 |
| Retina 2x vs 1x | 전처리에서 2x 감지 후 0.5x 다운샘플 |

### 7.5 Tech Stack (확정)

| Layer | Technology | 비고 |
|-------|-----------|------|
| Frontend | Next.js 14 + TypeScript | App Router |
| Styling | Tailwind CSS | |
| Canvas / 마킹 | Konva.js | react-konva |
| Backend | FastAPI (Python 3.11) | |
| 이미지 처리 | Pillow + OpenCV | |
| AI / Vision | Google Gemini 2.0 Flash | 무료 티어, 추후 Claude 교체 가능 |
| Job Queue | FastAPI BackgroundTasks | 로컬 MVP용, 추후 Celery 전환 |
| Storage | 로컬 파일시스템 | 로컬 MVP용, 추후 S3 전환 |
| DB | SQLite + SQLAlchemy | 로컬 MVP용, 추후 PostgreSQL 전환 |
| Auth | NextAuth.js (Google OAuth) | |
| 모니터링 | Sentry (에러) + Datadog (APM) | |
| Hosting | Vercel (FE) + Railway (BE) | |

---

## 8. Non-Functional Requirements

| 요구사항 | 목표 | 측정 방법 |
|---------|------|---------|
| 분석 완료 시간 | 30초 이내 (P95) | Datadog APM |
| 이미지 업로드 | 20MB 5초 이내 | S3 Transfer 측정 |
| 서비스 가용성 | 99.5% Uptime | Railway 헬스체크 |
| 동시 분석 | 최대 50 Job (MVP) | Celery Worker 수 |
| 데이터 보안 | S3 서버 사이드 암호화 (SSE-S3) | |
| 데이터 보존 | 이미지: 90일 후 자동 삭제 / 분석 메타데이터: 영구 보존 | |
| 접근성 | WCAG 2.1 AA, 색맹 대응 마킹 옵션 | |
| 개인정보 | GDPR 준수: 삭제 요청 처리 API 제공 | |
| 보안 | 업로드 파일 MIME 타입 검증, 크기 제한 서버 검증 | |

---

## 9. Monetization Strategy (B-3 해소 — 비용 역산 반영)

### API 비용 역산

```
Claude Vision API 비용 추정 (이미지 1쌍 기준):
  - Input:  ~2,000 tokens (이미지 2장) ≒ $0.006
  - Output: ~500 tokens              ≒ $0.002
  - 합계: 분석 1회당 약 $0.008 ~ $0.015

Pro 사용자 월 100회 분석 시:
  - API 비용: $1.5 (여유 있음)
  - Storage:  ~$0.1
  - 총 원가:  ~$2/월 → $19 플랜 충분한 마진
```

| 플랜 | 가격 | 분석 횟수 | 기능 |
|------|------|---------|------|
| Free | $0/월 | 월 10회 | 기본 분석, 공유 링크 7일 |
| Pro | $19/월 | 월 200회 | 히스토리, Approve 워크플로우, 공유 링크 무제한, Figma 연동 |
| Team | $49/월 (팀 5인) | 월 500회 | Pro + 팀 협업, Jira 연동, 우선 처리 큐 |
| Enterprise | 문의 | 무제한 | CI/CD, SSO, 온프레미스, SLA |

> "무제한" 표현 제거. 플랜별 횟수 상한 명시.
> 초과 시: 건당 $0.05 추가 과금 (Pay-as-you-go)

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| AI 분석 정확도 미달 | High | 내부 테스트셋 50쌍 구축, Precision/Recall 목표 명시, 지속 개선 |
| Claude API 장애 | High | Fallback: 픽셀 비교 결과만 제공 (서비스 중단 없음) |
| 이미지 해상도 불일치 | Medium | Retina 자동 감지, 수동 기준 선택 UI |
| 이미지 내 PII 노출 | High | 90일 자동 삭제, 분석 시 PII 감지 경고 옵션 |
| API 비용 급증 | Medium | 플랜별 횟수 상한, 이상 사용 알림 |
| 경쟁사 Percy/Chromatic | Medium | 디자이너 온보딩 UX 차별화, 설정 없이 즉시 시작 |

---

## 11. Roadmap

```
Phase 1 — MVP (0~8주)
  ✦ Google OAuth + 이미지 업로드 + AI 분석 + 결과 시각화
  ✦ Approve/Ignore 워크플로우 + 공유 링크

Phase 2 — Growth (9~16주)
  ✦ 프로젝트 히스토리 + 팀 협업 + Figma 연동 + Slack 알림

Phase 3 — Scale (17~24주)
  ✦ CI/CD 연동 + REST API 공개 + Enterprise 기능
```

---

## 12. Out of Scope (현재 버전)

- 비디오 / 애니메이션 QA
- 코드 레벨 자동 수정
- 모바일 앱 (네이티브) 자동 실행 테스트
- 접근성 자동 검사
- 멀티 스크린 비교 (Phase 2 검토)

---

## 13. 구현 현황 (Implementation Status)

### 13.1 프로젝트 구조

```
LINE_QA/
├── .claude/
│   └── launch.json              # 개발 서버 실행 설정
├── PRD.md                       # 이 문서
├── backend/                     # FastAPI Python 백엔드
│   ├── main.py                  # FastAPI 앱 엔트리포인트 (CORS, 라우터, 정적 파일)
│   ├── requirements.txt         # Python 의존성
│   ├── .env                     # 환경변수 (GEMINI_API_KEY 등)
│   ├── designsync.db            # SQLite DB (auto-created)
│   ├── uploads/                 # 업로드 이미지 저장 디렉토리
│   └── app/
│       ├── core/
│       │   └── config.py        # Settings (pydantic-settings, .env 로드)
│       ├── models/
│       │   └── database.py      # SQLAlchemy 모델 (Analysis, Difference, ShareLink)
│       ├── api/
│       │   ├── analyze.py       # 분석 API (업로드, 상태조회, 결과, 차이점 상태변경)
│       │   └── share.py         # 공유 링크 API (생성, 조회)
│       └── services/
│           ├── image_processor.py  # 이미지 정규화, 크기 조회, 좌표 스케일링
│           ├── pixel_diff.py       # SSIM 기반 픽셀 비교 + 영역 세분화
│           └── gemini_analyzer.py  # Gemini Vision API 분석 + 모델 폴백 체인
└── frontend/                    # Next.js 14 프론트엔드
    ├── next.config.mjs          # Next.js 설정 (API 리라이트 프록시)
    ├── tailwind.config.ts       # Tailwind 설정 (brand 색상 확장)
    └── src/
        ├── app/
        │   ├── layout.tsx       # 공통 레이아웃 (헤더)
        │   ├── page.tsx         # 홈 페이지 (이미지 업로드)
        │   ├── globals.css      # 글로벌 CSS
        │   ├── demo/page.tsx    # 데모 페이지 (목업 데이터)
        │   └── result/[id]/page.tsx  # 결과 페이지 (폴링 → 분석 결과 표시)
        ├── components/
        │   ├── ImageViewer.tsx   # 이미지 뷰어 (Side-by-side + Overlay, SVG 마킹)
        │   ├── DiffList.tsx     # 차이점 목록 패널 (필터, 상태 변경)
        │   ├── SeverityBadge.tsx # 심각도 뱃지 컴포넌트
        │   └── UploadZone.tsx   # 이미지 업로드 영역 컴포넌트
        └── lib/
            ├── api.ts           # API 호출 함수 (fetch wrapper)
            └── types.ts         # TypeScript 타입 정의
```

### 13.2 MVP 기능 구현 체크리스트

| 기능 | 상태 | 비고 |
|------|------|------|
| F-02 이미지 업로드 | ✅ 완료 | D&D + 클릭, PNG/JPG/WebP, 20MB 제한 |
| F-03 AI 차이점 분석 | ✅ 완료 | Gemini Vision + Pixel diff 폴백 |
| F-04 심각도 분류 | ✅ 완료 | Critical/Major/Minor 자동 분류 |
| F-05 결과 시각화 | ✅ 완료 | Side-by-side, Overlay 슬라이더, 줌 |
| F-06 Approve/Ignore | ✅ 완료 | 상태 변경 API + UI 반영 |
| F-07 리포트 생성 | ✅ 완료 | 요약 카드, 유사도 점수, 수치 표시 |
| F-08 공유 링크 | ✅ 완료 | short_id 기반, 만료일 설정 |
| F-01 사용자 인증 | ❌ 미구현 | Google OAuth (NextAuth.js) |
| 데모 페이지 | ✅ 완료 | 목업 데이터로 즉시 체험 |

### 13.3 개발 환경 설정 & 실행 방법

**사전 요구사항:**
- Python 3.9+ (backend)
- Node.js 18+ (frontend)
- Gemini API Key ([Google AI Studio](https://aistudio.google.com/)에서 발급)

**Backend 설정:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env 파일 생성
cat > .env << EOF
GEMINI_API_KEY=your_actual_gemini_api_key
DATABASE_URL=sqlite+aiosqlite:///./designsync.db
UPLOAD_DIR=./uploads
FRONTEND_URL=http://localhost:3000
EOF

# 실행
uvicorn main:app --reload --port 8000
```

**Frontend 설정:**
```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

**Claude Code에서 실행 (launch.json 사용):**
- `.claude/launch.json`에 설정이 미리 되어 있음
- `preview_start("backend")` → `preview_start("frontend")` 순서로 실행

### 13.4 API 엔드포인트 명세

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/analyze` | 이미지 2장 업로드 후 분석 시작 |
| `GET` | `/api/analyze/{id}/status` | 분석 진행 상태 조회 |
| `GET` | `/api/analyze/{id}/result` | 분석 결과 전체 반환 |
| `PATCH` | `/api/analyze/{id}/differences/{diff_id}` | 차이점 상태 변경 |
| `POST` | `/api/share/{analysis_id}` | 공유 링크 생성 |
| `GET` | `/api/share/{short_id}` | 공유 링크로 결과 조회 |
| `GET` | `/api/files/{filename}` | 업로드된 이미지 서빙 (StaticFiles) |
| `GET` | `/health` | 헬스체크 |

**결과 API 응답 구조 (`GET /api/analyze/{id}/result`):**
```json
{
  "analysis_id": "uuid",
  "status": "done",
  "similarity_score": 85.3,
  "design_image": "/api/files/{id}_design.png",
  "dev_image": "/api/files/{id}_dev.png",
  "marked_image": "/api/files/{id}_marked.png",
  "design_image_size": { "width": 390, "height": 844 },
  "dev_image_size": { "width": 375, "height": 812 },
  "summary": { "critical": 2, "major": 3, "minor": 1, "approved": 0, "ignored": 0 },
  "differences": [
    {
      "id": "uuid",
      "category": "typography",
      "severity": "major",
      "description": "CTA 버튼 폰트 크기가 16px이어야 하는데 14px입니다",
      "design_value": "16px",
      "dev_value": "14px",
      "bbox_x": 40, "bbox_y": 700, "bbox_w": 295, "bbox_h": 48,
      "status": "issue"
    }
  ]
}
```

---

## 14. 핵심 기술 아키텍처 상세

### 14.1 AI 분석 파이프라인 (실제 구현)

```
Input: [Design Image] + [Dev Screenshot]
        │
        ▼
[Step 1] 원본 이미지 크기 조회
  get_image_dimensions(dev_path) → (dev_w, dev_h)
        │
        ▼
[Step 2] 이미지 정규화 + 픽셀 비교
  load_and_normalize(design_path, dev_path) → (img_a, img_b, orig_a_size, orig_b_size)
  ※ 작은 쪽 기준 리사이즈 (비율 유지 아닌 강제 리사이즈)
  compute_diff(img_a, img_b) → (similarity_score, regions)
  ※ SSIM + 영역 세분화 알고리즘 적용
        │
        ▼
[Step 3] 좌표 스케일링 (정규화 → 원본)
  scale_regions_to_original(regions, norm_w, norm_h, dev_w, dev_h)
  ※ norm 좌표 × (orig / norm) 비율로 변환
        │
        ▼
[Step 4] Gemini Vision AI 분석 (모델 폴백 체인)
  analyze_with_gemini(design_path, dev_path, scaled_regions, dev_w, dev_h)
  ├── 시도 1: gemini-2.0-flash-lite
  ├── 시도 2: gemini-2.0-flash
  ├── 시도 3: gemini-1.5-flash-latest
  ├── 시도 4: gemini-1.5-pro-latest
  └── 모두 실패 시: _fallback_from_regions() (Pixel diff 폴백)
        │
        ▼
[Step 5] 마킹 이미지 생성
  save_marked_image(dev_path, diff_data, marked_path)
  ※ 원본 dev 이미지 위에 심각도별 색상 bbox 오버레이
        │
        ▼
[Step 6] DB 저장 → 상태 "done" 업데이트
```

### 14.2 Pixel Diff 세분화 알고리즘

큰 차이 영역이 하나의 거대 박스로 잡히는 문제를 해결하기 위해 4단계 세분화 적용:

```
[1단계] 노이즈 제거
  - threshold: 25 (기존 30보다 민감)
  - MORPH_OPEN (kernel 3×3): 1-2px 짜리 노이즈 제거
  - MORPH_CLOSE (kernel 7×5): 같은 요소 내 인접 픽셀 연결

[2단계] Contour 추출
  - findContours(RETR_EXTERNAL): 외곽 윤곽만 추출
  - area < 80px 미만: 노이즈로 판단, 제외

[3단계] 큰 영역 세분화 (화면의 15% 이상)
  - 수평 프로젝션: 각 행의 흰 픽셀 수 계산
  - 빈 행 (행의 3% 미만) 이 5행 이상 연속되면 → 분할 포인트
  - 수평 분할이 실패하면 → 수직 분할 시도 (동일 로직)
  - _tight_bbox()로 각 세그먼트의 실제 차이 영역만 감싸는 타이트한 bbox 생성

[4단계] 겹치는 영역 병합
  - IoU (Intersection over Union) > 0.3이면 병합
  - 최종 최대 15개로 제한
```

**효과:**
- 이전: 화면 전체를 덮는 1개 거대 영역
- 이후: 헤더/콘텐츠/푸터 등 UI 영역별로 3~10개 세분화된 영역

### 14.3 Annotation 좌표 시스템 (Frontend)

```
┌── 핵심 원칙 ──────────────────────────────────────────────────┐
│ 모든 bbox 좌표는 DEV(개발) 이미지의 원본 픽셀 기준이다.       │
│ Design 이미지에 표시할 때는 비율 스케일링으로 매핑한다.        │
└───────────────────────────────────────────────────────────────┘

[ImageViewer.tsx 핵심 구조]

  <div style={{ transform: `scale(${zoom})` }}>
    <img ref={imgRef} src={url} />    ← 이미지 원본 크기로 렌더링
    <svg
      viewBox={`0 0 ${vw} ${vh}`}     ← viewBox = 이미지 원본 크기
      class="absolute inset-0 w-full h-full"
    >
      <rect x={bbox_x} y={bbox_y} ... />    ← 원본 픽셀 좌표 그대로
      <circle cx={badgeX} cy={badgeY} />     ← 번호 배지
    </svg>
  </div>

[Design 이미지 좌표 변환]
  scaleX = design_width / dev_width
  scaleY = design_height / dev_height
  design_bbox_x = bbox_x × scaleX
  design_bbox_y = bbox_y × scaleY

[Badge 크기 자동 스케일링]
  BADGE_R = max(12, min(18, vw × 0.032))
  ※ viewBox 기준 비율로 계산하여 줌에 무관하게 일정 크기
```

### 14.4 프론트엔드 API 프록시

프론트엔드에서 백엔드 API에 접근하기 위해 Next.js 리라이트를 사용:

```js
// next.config.mjs
async rewrites() {
  return [
    { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }
  ];
}

// api.ts
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";  // 빈 문자열 → 같은 호스트
```

**장점:** CORS 문제 없음, 프론트엔드와 백엔드가 같은 origin으로 동작

---

## 15. Gemini API 설정 & 트러블슈팅

### 15.1 API 키 설정

1. [Google AI Studio](https://aistudio.google.com/apikey) 접속
2. "Create API Key" 클릭
3. `backend/.env`에 설정:
   ```
   GEMINI_API_KEY=AIzaSy...실제키
   ```

### 15.2 모델 폴백 체인

할당량 초과(429) 시 자동으로 다음 모델로 전환:

```
gemini-2.0-flash-lite → gemini-2.0-flash → gemini-1.5-flash-latest → gemini-1.5-pro-latest
```

모든 모델이 실패하면 → Pixel diff 폴백 결과 사용

### 15.3 자주 발생하는 문제

| 문제 | 원인 | 해결 |
|------|------|------|
| `429 quota exceeded, limit: 0` | 무료 할당량 소진 (일일 리셋) | 다음 날 자동 리셋 대기 또는 새 API 키 생성 |
| `404 model not found` | 모델명 변경/폐지 | `GEMINI_MODELS` 배열 업데이트 |
| `400 API key not valid` | 잘못된 API 키 | `.env` 확인, AI Studio에서 재발급 |
| 결과가 1개뿐 (거대 영역) | Gemini 실패 + 이전 pixel diff | pixel_diff.py 세분화 알고리즘 확인 |
| 배지가 잘못된 위치 | viewBox 미설정 | ImageViewer.tsx의 SVG viewBox 확인 |
| "Failed to fetch" | CORS 또는 프록시 문제 | next.config.mjs 리라이트 설정 확인 |

### 15.4 DB 초기화 (개발 시)

분석 결과가 꼬였을 때 DB를 초기화:
```bash
cd backend
rm -f designsync.db   # DB 삭제 (서버 재시작 시 자동 재생성)
```

---

## 16. 향후 작업 (Next Steps)

### 즉시 필요 (Priority 1)
- [ ] Gemini API 유료 플랜 전환 또는 안정적인 API 키 확보
- [ ] Gemini 정상 동작 시 E2E 테스트 (구체적 차이점 설명, 정확한 bbox)
- [ ] 이미지 크기가 크게 다른 경우 (Retina 2x vs 1x) 전처리 보정
- [ ] 로딩 화면에서 폴링 상태 표시 개선 (processing 단계 세분화)

### 단기 개선 (Priority 2)
- [ ] Google OAuth 인증 (NextAuth.js)
- [ ] 분석 히스토리 페이지
- [ ] Pixel diff 폴백 품질 개선 (색상 차이 감지, 텍스트 영역 구분)
- [ ] 마킹 이미지 다운로드/내보내기 기능
- [ ] 결과 페이지 반응형 (모바일 대응)

### 중기 기능 (Priority 3)
- [ ] Figma API 연동 (프레임 직접 가져오기)
- [ ] 팀 워크스페이스 + 멤버 초대
- [ ] Jira/Linear 이슈 자동 생성 연동
- [ ] PDF 리포트 내보내기
- [ ] CI/CD 연동 REST API

---

## 17. 기술 결정 기록 (ADR: Architecture Decision Records)

### ADR-001: Gemini Vision 선택 (2026-02-27)
- **결정:** Claude Vision 대신 Google Gemini 2.0 Flash 사용
- **이유:** 무료 티어 제공, 이미지 분석 성능 우수, 빠른 프로토타이핑
- **트레이드오프:** 무료 할당량 제한 있음, 모델 안정성 변동 가능
- **전환 계획:** 추후 필요 시 Claude Vision으로 교체 가능 (인터페이스 동일)

### ADR-002: SVG viewBox 기반 좌표 매핑 (2026-02-27)
- **결정:** Canvas(Konva.js) 대신 SVG viewBox 사용
- **이유:** viewBox가 이미지 크기와 좌표를 자동 매핑, 줌/리사이즈에 무관하게 일관된 좌표
- **효과:** bbox 원본 픽셀 좌표를 변환 없이 그대로 SVG에 사용 가능

### ADR-003: Next.js 리라이트 프록시 (2026-02-27)
- **결정:** 프론트엔드에서 직접 `localhost:8000` 접근 대신 Next.js rewrites 사용
- **이유:** CORS 문제 완전 해결, 프리뷰 환경/배포 환경 모두 동작
- **설정:** `next.config.mjs`에 `/api/:path*` → `http://127.0.0.1:8000/api/:path*`

### ADR-004: Pixel Diff 세분화 알고리즘 (2026-02-27)
- **결정:** 큰 차이 영역을 수평/수직 프로젝션으로 자동 세분화
- **이유:** SSIM contour가 하나의 거대 blob을 생성하는 문제 해결
- **방법:** 화면의 15% 이상 영역 → 수평 프로젝션 → 빈 행 기반 분할 → 타이트 bbox
- **효과:** 1개 거대 영역 → 3~10개 UI 요소별 영역으로 세분화
