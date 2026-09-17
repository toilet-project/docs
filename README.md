# 📚 급똥 · 설계와 운영 문서

**공공데이터를 수집하는 지도에서, 사용자 참여와 관리자 검토로 품질을 개선하는 서비스로.**

[서비스 열기](https://geupddong.com) · [프로젝트 소개](https://github.com/toilet-project) · [WBS](https://github.com/orgs/toilet-project/projects/2/views/2) · [변경 이력](changelog/CHANGELOG.md)

## 처음 오셨다면

| 알고 싶은 것 | 먼저 읽을 문서 |
| --- | --- |
| 지금 무엇을 운영하고 있나요? | [현재 기능·운영 상태](operations/current-state-2026-09-17.md) |
| 시스템은 어떻게 연결되나요? | [운영 아키텍처 v5](architecture/architecture-v5.md) |
| 어떤 문제를 어떻게 해결했나요? | [프로젝트 포트폴리오](https://github.com/toilet-project) · [중복 시설·변경 검토](database/duplicate-facility-management.md) |
| 데이터와 API의 기준은 무엇인가요? | [현재 스키마 안내](database/current-schema.md) · [리뷰 API·정책](api/location-reviews.md) · [기본 API](api/toilet-api.md) |
| 어떻게 배포하고 점검하나요? | [배포·운영 가이드](operations/deployment.md) · [장애 대응](operations/reliability-runbook.md) |

## 현재 운영 · 2026-09-17

| 영역 | 반영된 기능 | 자세히 보기 |
| --- | --- | --- |
| 사용자 웹 | Next.js·Workers, 지도 탐색, Google·Kakao 로그인, 제보·알림, 현장 리뷰와 내 리뷰 관리 | [현재 상태](operations/current-state-2026-09-17.md) |
| 데이터 품질 | 행정구역 검토, 공공데이터 변경 비교, 중복 이름·좌표 비교, 대표 지정·선택 숨김 | [시설 관리 정책](database/duplicate-facility-management.md) |
| 서비스 분석 | GA 제거, 자체 이벤트 수집·기간별 방문자 추정·KST 집계 | [수집 범위와 한계](planning/service-analytics.md) |
| 상세 캐시 | 배포 독립 공유 데이터, 변경 이벤트 갱신, 28일 순환 갱신·보호 조건부 퇴역 캐시 정리 | [캐시 운영](architecture/toilet-detail-cache-platform.md) |
| 계정 보호 | 탈퇴·선택 보관·복구·후속 파기, 국내 LOCAL 보호 기록 | [계정 수명주기](operations/account-lifecycle-current-2026-09-10.md) |

구현 완료와 자연 운영 관측은 구분합니다. 실제 공공데이터 변경 수신·확정 값 보존 관측은 [10월 초 점검](https://github.com/toilet-project/docs/issues/95), 사본 만료 관측은 [후속 인수](https://github.com/toilet-project/docs/issues/94)에서 추적합니다. 전체 서비스 자동 복구는 현재 제공 기능이 아닙니다.

## 시스템 한눈에 보기

![급똥 운영 아키텍처 v5](architecture/assets/architecture-v5.svg)

## 주제별 문서

| 주제 | 문서 |
| --- | --- |
| 아키텍처·성능 | [현재 아키텍처](architecture/architecture-v5.md) · [상세 캐시·갱신·정리](architecture/toilet-detail-cache-platform.md) |
| API·리뷰 | [기본 API 계약](api/toilet-api.md) · [리뷰 작성·조회·관리](api/location-reviews.md) |
| DB·데이터 품질 | [스키마 변경 지도](database/current-schema.md) · [중복 시설·변경 검토](database/duplicate-facility-management.md) · [좌표 품질 관리](database/duplicate-coordinate-quality.md) |
| 지역·주소 | [행정구역 정규화](database/administrative-region-normalization-v1.8.md) · [확정 주소 분리](database/coordinate-address-fields-v1.9.md) · [재판정 이력](database/region-assessment-history-v1.10.md) |
| 인증·회원 | [인증·권한 설계](planning/authentication-authorization-design.md) · [회원 모델 V11](database/account-withdrawal-retention-v1.11.md) · [현재 계정 운영](operations/account-lifecycle-current-2026-09-10.md) |
| 분석·정책 | [자체 서비스 이용 분석](planning/service-analytics.md) · [리뷰 보존·작성자 연결 해제](api/location-reviews.md#작성자-연결-해제와-보존) |
| 배포·복구 | [배포 가이드](operations/deployment.md) · [Tunnel 접속](operations/tunnel-access-runbook.md) · [안정화 Runbook](operations/reliability-runbook.md) · [키·인수 절차](operations/account-acceptance-and-key-lifecycle-2026-09-10.md) |

<details>
<summary><b>과거 설계·검증 기록 찾기</b></summary>

아래 문서는 해당 날짜의 설계와 시험 결과를 보존합니다. 당시의 “계획·미배포·OFF”를 현재 운영 상태로 해석하지 않습니다.

- 아키텍처: [v2](architecture/architecture-v2.md) · [v3 / Pages 시점](architecture/architecture-v3.md) · [v4 / Tunnel 전환](architecture/architecture-v4.md).
- 초기 모델: [DB v1.7](database/database-schema-v1.7.md) · [Toilet 테이블](database/toilet-table.md) · [제보·좌표 승인](database/user-report-coordinate-model.md).
- 기획: [요구사항](planning/requirements.md) · [공공데이터 변경 검토 초기안](planning/public-data-change-review.md) · [폐기된 GA 설계](planning/google-analytics-admin-dashboard.md) · [초기 동의 정책](planning/privacy-policy-consent-v1.md).
- 전환·점검: [Next.js 전환](operations/nextjs-workers-production-2026-09-06.md) · [Tunnel 후속](operations/tunnel-followup-2026-09-07.md) · [9/10 WBS 감사](operations/wbs-audit-2026-09-10.md) · [Workers 감시](operations/worker-error-monitoring.md).
- 데이터 검증: [운영 반영](operations/region-production-result-2026-09-05.md) · [전체 분석](operations/region-full-final-review-2026-09-05.md) · [관리자 인수](operations/region-admin-review-release-2026-09-05.md).
- 추가 표본·SQL·복원 시험 기록은 [operations 디렉터리](operations/)에서 날짜별로 찾을 수 있습니다.

</details>

## 문서 작성 기준

- **결론 → 사용자에게 달라진 점 → 확인 결과 → 남은 일** 순서로 씁니다. 긴 커밋·실행 번호 나열 대신 설명 있는 근거 링크를 사용합니다.
- 운영 반영, 시험 통과, 계획, 자연 관측 대기를 구분하고 기준일을 표시합니다. 과거 결과를 소급해 고치지 않습니다.
- 아키텍처는 `architecture/`, 데이터 모델은 `database/`, API는 `api/`, 운영은 `operations/`, 의사결정은 `planning/`에 둡니다.
- 실행 가능한 DDL·API 계약은 제품 저장소 소스를 기준으로 확인합니다. 문서의 예시를 운영에 바로 실행하지 않습니다.
- 공개 문서에는 비밀값·내부 접속 정보·회원정보·시설별 비공개 원문을 싣지 않습니다.
- 확정 변경은 [변경 이력](changelog/CHANGELOG.md)에 최신순으로 추가합니다. 새 WBS는 실제 개발 주차와 날짜를 확인합니다.
