# 배포·운영 가이드

2026-09-17 현재 기준. **CI 통과, main 병합, 실제 운영 전환을 구분합니다.**

## 서비스 경계

| 영역 | 주소·구성 |
| --- | --- |
| 사용자 웹 | https://geupddong.com · Next.js/OpenNext · Cloudflare Workers |
| 공개 API | https://api.geupddong.com · Cloudflare → Tunnel → Nginx → Spring Boot |
| 관리자 | https://admin.geupddong.com · Access 통과 + 애플리케이션 ADMIN 권한 |
| 원본 서버 | Mini PC Ubuntu · Docker의 API·Admin·Batch·MySQL·Redis |
| 웹 캐시 | R2·D1·Durable Object. 원본 DB·국내 LOCAL 보호 기록과 분리 |

MySQL·Redis는 공개 인터넷에 노출하지 않습니다. 개인 운영 접속과 CI 배포 접속은 다른 Access/Tunnel 정책을 사용합니다. [접속 안내](tunnel-access-runbook.md)

## 제품별 반영 방식

| 제품 | 검증·산출물 | 운영 전환 |
| --- | --- | --- |
| Web | Workers validation, 테스트·lint·타입·빌드·CodeQL, preview/production candidate | 검증 산출물을 승인 후 Wrangler Versions로 전환. CI 성공만으로 운영 배포 완료 아님 |
| API·Batch | Java 테스트·DB 통합·보안 검사·정확한 소스의 이미지 | 보호 롤아웃의 승인된 소스·게이트·기존 서비스 보존 조건 확인. 모든 main 변경을 무조건 자동 배포하지 않음 |
| Admin | 테스트·정적 UI 검사·CodeQL·이미지 | 저장소 배포 workflow의 트리거·보호 조건 확인 후 Tunnel 경유 전환 |
| Docs·조직 프로필 | 링크·표시·사실관계·공개 범위 | 문서 PR만 반영. 업무 서비스 배포 없음 |

브랜치 경로는 작업별 PR 정책을 따릅니다. 오래된 “feature → develop → main이면 항상 자동 배포” 설명을 공통 계약으로 사용하지 않습니다. 실제 실행 기준은 각 저장소의 현재 workflow입니다.

[Web workflow](https://github.com/toilet-project/toilet-web/tree/main/.github/workflows) · [API workflow](https://github.com/toilet-project/toilet-api/tree/main/.github/workflows) · [Admin workflow](https://github.com/toilet-project/toilet-admin-api/tree/main/.github/workflows) · [Batch workflow](https://github.com/toilet-project/toilet-batch/tree/main/.github/workflows)

## 배포 전후 체크리스트

1. 원격 최신 main·열린 PR·운영 버전을 비교해 다른 작업의 변경을 보존합니다.
2. 업무 스키마와 별도 캐시 DDL, 환경 변수·비밀정보·기능 게이트의 호환성을 확인합니다.
3. 변경 범위에 맞는 자동 검사와 CI를 통과하고 백업·복귀 경계를 정합니다.
4. 승인된 산출물만 반영합니다. 기능 변경이 없는 문서·테스트 PR 때문에 운영을 재배포하지 않습니다.
5. API health, 로그인·핵심 화면, 최근 배치와 관련 캐시·분석 상태를 구분해 확인합니다.
6. 일회성 게이트와 임시 시험 자원을 정리하고 완료·남은 관측을 WBS에 기록합니다.

## 주기 작업

- 공공데이터: 매일 02:00 KST, 최근 3일 갱신분의 수신·신규·수정·실패 이력을 확인합니다.
- 자체 분석: 매일 02:30 KST, 최근 14개 완료일을 재계산합니다.
- 공유 캐시: 28개 파티션 순환 갱신. 퇴역 페이지 캐시는 보호 조건을 통과한 대상만 정리합니다.
- 백업·복원 검증·계정 보호: [Runbook](reliability-runbook.md), [계정 기준](account-lifecycle-current-2026-09-10.md)과 후속 관측 WBS를 따릅니다.

## 비밀정보·장애 대응

비밀값은 환경별 비밀 저장소에 보관하고 코드·문서·공개 로그에 기록하지 않습니다. 장애 진단을 위해 DB·Redis 포트를 외부에 열지 않습니다. 재시작 정책·상태·로그를 확인하되 전체 서비스 자동 복구가 구현됐다고 가정하지 않습니다.

페이지 복귀, 앱 이미지 복귀, DB 복원, 파기 기록 재적용은 서로 다른 작업입니다. 원본 데이터·outbox·복구 자료를 임의 삭제하지 않습니다. [현재 구조](../architecture/architecture-v5.md) · [현재 운영 상태](current-state-2026-09-17.md)

<details>
<summary>이전 판본</summary>

- 2026-08-31 v2: 관리자 Access·Redis·정기 점검 기준.
- 2026-09-07 v2.1: Tunnel 경유 배포·개인 SSH/Workbench 전환.
- 2026-09-17: Workers와 제품별 보호 롤아웃, 자체 분석·캐시 수명주기를 반영.

</details>
