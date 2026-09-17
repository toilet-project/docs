# 화장실 상세 캐시 · 갱신과 정리

2026-09-17 현재 운영 기준 · [최초 전환](https://github.com/toilet-project/docs/issues/101) · [후속 순환 갱신·자동 정리](https://github.com/toilet-project/toilet-web/issues/265)

## 지금의 운영 방식

**공유 공개 데이터는 배포 간 재사용하고, 페이지는 배포별로 분리합니다.** 전체 페이지를 배포마다 다시 만들지 않습니다. 데이터만 28일 주기로 순환 갱신하고 대표 URL 검증과 실제 사용자 요청으로 페이지를 생성합니다.

| 계층 | 저장·조회 방식 | 경계 |
| --- | --- | --- |
| 공개 기본 상세 데이터 | R2 고정 키 `public-toilets/v1/toilets/{id}.json` | 배포와 독립. 공개 필드만 저장 |
| HTML·RSC·OpenNext 결과 | R2 incremental cache의 배포별 namespace | 코드·렌더링 결과 혼용 금지 |
| 태그·재검증 | D1 tag cache · Durable Object queue | 상세 경로·태그 무효화 |
| 지도 | 브라우저 → 공개 API | OpenNext 페이지 캐시가 아님 |
| 리뷰·평점·프로필·개인화 | 별도 API/사진 경로 | 공유 시설 데이터 객체에 고정하지 않음 |

R2 namespace는 **NEXT_DEPLOYMENT_ID / appVersion**으로 식별합니다. OpenNext build ID는 별도 검증 정보이며 두 값을 같은 것으로 취급하지 않습니다.

## 읽기와 변경 전파

```text
상세 요청 → 배포별 페이지 캐시
  MISS → 공유 공개 데이터
    fresh HIT → 렌더링
    MISS / 만료 → 원본 API → 조건부 저장 → 렌더링

DB 변경 커밋 → revision outbox → 서명된 v2 이벤트
  → 공유 데이터 · 상세 태그 · 상세 경로 갱신
  → 신규 / 삭제 / 공개 범위 변경이면 사이트맵도 갱신
```

원본 공개 데이터 요청에 방문자의 Cookie·Authorization을 전달하지 않습니다. 응답 필드를 명시적으로 선택해 내부 필드가 공유 객체로 유입되지 않도록 합니다.

## 일관성과 장애 정책

| 상황 | 처리 |
| --- | --- |
| 정상 데이터 | 저장 후 30일 fresh |
| 원본 장애 | fresh가 지난 기존 정상 데이터만 저장 후 37일까지 fallback; 없으면 오류 |
| 없는 ID | 404 negative cache 5분 |
| 삭제·비공개 | tombstone으로 오래된 공개 데이터의 재등장 차단 |
| 동시 조회·변경 | revision과 R2 ETag 조건부 쓰기로 오래된 응답의 덮어쓰기 방지 |
| 중복·역순 이벤트 | 시설별 단조 증가 revision으로 멱등 처리 |
| R2 장애 | 공개 API 조회로 우회. 원본 실패까지 숨기지 않음 |
| 분석 수집 장애 | 공개 상세 조회와 분리 |

30일은 이벤트 갱신을 대신하는 대기 시간이 아닙니다. 수정·숨김 이벤트가 먼저 무효화하고, TTL과 순환 갱신은 보조 수단입니다.

## 변경 이벤트와 공개 범위

```json
{
  "contractVersion": 2,
  "events": [
    { "toiletId": 1, "revision": 17, "action": "UPSERT", "catalogChanged": false }
  ]
}
```

- action은 UPSERT, DELETE, PRIVATE입니다. 정확한 ID·revision ACK 이후 전달 완료로 기록합니다.
- outbox의 전달 완료 행은 revision 기준으로 보존합니다. 원문 응답·회원정보를 넣지 않습니다.
- DB 트리거가 API뿐 아니라 배치의 변경도 포착합니다. 캐시용 DDL 번호는 Flyway 업무 스키마 번호와 별개입니다.
- 제보 접수·반려·검토 보류는 공개 시설 값이 바뀌지 않으면 시설 캐시를 무효화하지 않습니다.
- 제보 승인·좌표 보정·지역 판정·공공데이터 반영은 관련 상세를 갱신합니다.
- **시설 숨김/해제**는 공개 목록·상세·사이트맵에 영향을 줍니다. 기존 트리거를 보존한 추가 visibility 트리거로 연결합니다.
- 관리자별 **작업 목록 숨김**은 공개 시설 값이 바뀌지 않습니다.
- 리뷰 변경은 리뷰 조회·집계 경로에서 처리하고 공유 기본 시설 객체와 구분합니다.

[시설 관리 정책](../database/duplicate-facility-management.md) · [API 캐시 구현](https://github.com/toilet-project/toilet-api/issues/131)

## 데이터 순환 갱신

전체 공개 ID를 안정적인 28개 파티션으로 나눠 하루 하나를 갱신합니다. 기본 5 req/s로 원본을 읽어 같은 R2 키에 조건부 저장합니다. 상세 페이지 URL을 요청하지 않으므로 HTML/RSC를 모두 다시 생성하지 않습니다.

배포와 실행 그룹을 분리하고 체크포인트·재시도·실패 목록으로 중단 후 이어갑니다. 배포 후에는 대표 상세 URL의 캐시 증거만 확인합니다. 수동 전체 사전 생성 도구는 남아 있지만 정기 배포의 필수 단계가 아닙니다.

## 퇴역 페이지 캐시 자동 정리

정리 대상은 릴리스 기록으로 식별한 **퇴역 incremental cache namespace**뿐입니다.

- 현재 트래픽의 모든 활성 버전, rollback 및 새 배포 후보를 보호합니다.
- 식별 가능한 모든 퇴역 namespace를 각각의 퇴역 시각부터 최소 3일 보호합니다.
- 공유 데이터, D1, Durable Object, 정적 자산, 업로드 사진과 다른 버킷은 제외합니다.
- 활성 판정 실패·배포 진행·unknown 객체·삭제 직전 지문 불일치이면 삭제를 거부합니다.
- 기본 상한 10만 개·4 GiB를 초과하면 거부합니다. 생성일만으로 삭제하거나 버킷 전체를 비우지 않습니다.
- 매 실행마다 새 계획 → 활성 상태 재확인 → 동일 지문 삭제 → 결과 보고를 수행합니다.
- 정리 실패는 별도 운영 실패로 보고하며 정상 배포를 자동 롤백하지 않습니다.

## 설정·중단 경계

| 설정 | 역할 |
| --- | --- |
| SHARED_TOILET_CACHE_ENABLED | 공유 데이터 사용 여부 |
| WEB_CACHE_CONTRACT_VERSION | 운영 이벤트 계약 v2 |
| CACHE_DATA_REFRESH_ENABLED | 정기 데이터 순환 갱신 게이트 |
| CACHE_CLEANUP_AUTOMATIC_ENABLED | 보호 조건부 자동 정리 게이트 |
| CACHE_PREWARM_ENABLED | 별도 수동 사전 생성 게이트 |

후속 운영 인수에서 정기 갱신·자동 정리 게이트를 활성화했습니다. 일회성 수동 삭제 게이트와 혼동하지 않습니다. 유지보수 서명은 변경 이벤트 서명과 분리하며 삭제 자격증명은 대상 버킷 최소 권한으로 제한합니다. 실제 비밀값은 문서·로그·artifact에 남기지 않습니다.

중단 시 해당 유지보수 게이트를 먼저 끕니다. 페이지 문제는 검증된 이전 Worker 버전으로 복귀하되 R2를 지우지 않습니다. 캐시·트리거·계약 버전 변경은 현재 호환성을 확인한 승인 절차로 수행하며, 문서만 보고 과거 rollback SQL을 바로 실행하지 않습니다.

## 확인 결과와 한계

| 확인한 것 | 결과·근거 |
| --- | --- |
| 최초 전체 URL 생성 | [53,590개 처리](https://github.com/toilet-project/toilet-web/actions/runs/35091327638). 당시 STALE도 성공으로 인정하여 전체 fresh 증거로는 부족 |
| fresh 판정 보강 | HIT/REVALIDATED만 완료 인정. [표본 11개 성공](https://github.com/toilet-project/toilet-web/actions/runs/35118300307) |
| 전체 fresh 실행 후 실패 재검증 | [전체 실행 실패 기록](https://github.com/toilet-project/toilet-web/actions/runs/35118665768)을 보존. [실패 260개 재검증 성공·추가 표본 20개 HIT](https://github.com/toilet-project/toilet-web/actions/runs/35152708839) |
| 승인된 일회성 구버전 삭제 | [120,493개 정리](https://github.com/toilet-project/toilet-web/actions/runs/35145618452), [사후 후보 0·unknown 0](https://github.com/toilet-project/toilet-web/actions/runs/35149397464) |
| 순환 갱신 운영 표본 | [한 파티션 1,914개 성공·실패 0](https://github.com/toilet-project/toilet-web/actions/runs/35158121805), R2 표본의 30일 만료 확인 |
| 최근 퇴역 보호 보강 | 최초 dry-run에서 보호 누락 발견, 삭제 전 수정. [모든 퇴역 버전의 3일 보호](https://github.com/toilet-project/toilet-web/pull/268) |
| 자동 정리 최초 실행 | [후보 없음·삭제 0·unknown 0](https://github.com/toilet-project/toilet-web/actions/runs/35163619844). 자동 삭제 대상이 실제 삭제된 시험은 아님 |

이 결과는 해당 실행 시점의 근거입니다. 미래 갱신·삭제 성공이나 모든 URL의 영구적인 fresh 상태를 보장하지 않습니다. 스키마·권한·경쟁·역순·장애·보호 경계는 자동 시험으로, 자연 운영 수신은 별도 관측으로 구분합니다.
