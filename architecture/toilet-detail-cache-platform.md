# 화장실 상세 캐시 구조와 사전 생성 운영안

2026-09-15 · WBS [DOCS #101](https://github.com/toilet-project/docs/issues/101), [API #131](https://github.com/toilet-project/toilet-api/issues/131), [WEB #242](https://github.com/toilet-project/toilet-web/issues/242), [WEB #243](https://github.com/toilet-project/toilet-web/issues/243)

## 상태와 범위

이 문서는 구현 후보와 운영 전환 절차를 함께 기록한다. 코드와 비활성 자동화는 각 작업 브랜치에서 구현·검증하지만, 운영 Worker 배포, 운영 R2 삭제·무효화, 운영 사전 생성, 부하 시험은 별도 승인 전까지 수행하지 않는다.

여기서 **전체 화장실 상세 캐싱**은 사이트맵에 포함된 모든 공개 화장실의 `/toilet/{id}` URL을 요청해 배포별 Next.js/OpenNext 페이지 결과를 미리 만드는 것을 뜻한다. 약 5.3만 개 URL을 하나의 큰 파일로 합치는 방식이 아니다. 각 URL은 독립적으로 생성되어 일부 실패를 재시도하고 중단 지점부터 이어갈 수 있다.

상세 화면의 시설명·주소·좌표·시설 수·개방시간·관리기관 등 공개 시설 데이터는 배포와 독립된 R2 공유 데이터 캐시를 사용한다. HTML/RSC를 포함한 Next.js 증분 페이지 결과는 코드와 렌더링 결과가 섞이지 않도록 배포별로 유지한다.

리뷰 목록·평점·프로필 사진은 브라우저에서 별도 공개 API와 사진 주소로 불러온다. 따라서 “모든 상세 URL 사전 생성”에는 포함되지만, 리뷰 데이터 자체를 페이지 R2 객체에 고정하지 않는다. 리뷰 작성·수정·작성자 분리는 기존 리뷰 브라우저 캐시 갱신 경로를 사용하며 시설 데이터 캐시를 무효화하지 않는다. 지도 목록도 브라우저가 공개 API를 직접 조회하므로 현재 OpenNext R2 정리 대상이 아니다.

## 현재 구조와 목표 구조

현재 운영 구조는 다음과 같다.

- Next.js/OpenNext가 Cloudflare Worker에서 실행된다.
- OpenNext 증분 캐시는 `incremental-cache/{OPEN_NEXT_BUILD_ID}/...` 형식으로 R2에 저장되고, 태그 갱신 시각은 D1에 저장된다.
- 화장실 상세 데이터 요청은 1시간 재검증과 `toilet:{id}` 태그를 사용한다.
- 미니 PC API는 MySQL 변경 트리거 → outbox → HMAC 서명 수신 API 흐름으로 상세 태그와 경로를 무효화한다.
- 과거 배포별 R2 객체를 자동으로 정리하는 정책과 배포 전체 사전 생성은 없다.

목표 구조는 다음과 같다.

```text
상세 요청 /toilet/{id}
  ├─ 배포별 OpenNext 페이지 캐시 HIT → 응답
  └─ MISS
      └─ 공유 공개 데이터 캐시 public-toilets/v1/toilets/{id}.json
          ├─ fresh HIT → Next.js 렌더링 → 배포별 페이지 캐시 저장
          └─ MISS/만료 → 미니 PC 공개 API 조회 → 공유 캐시 저장 → 렌더링

공개 데이터 변경 커밋
  → MySQL trigger/outbox revision 증가
  → API 서명 이벤트 v2 전송
  → 공유 데이터 무효화 + toilet:{id} 태그/상세 경로 무효화
  → 추가·삭제·공개 상태 변화면 사이트맵도 무효화
```

공유 캐시 스키마 버전 `v1`은 애플리케이션 배포 ID와 독립적이다. 응답 필드를 명시적으로 복사하므로 원본 API에 인증·내부 필드가 추가돼도 공유 객체에 따라 들어가지 않는다. 방문자의 Cookie나 Authorization도 원본 공개 데이터 요청으로 전달하지 않는다.

## 공유 데이터의 일관성과 장애 동작

| 상황 | 동작 |
| --- | --- |
| 유효한 데이터 HIT | 원본 API 없이 즉시 재사용 |
| 존재하지 않는 ID | 5분간 negative cache 후 다시 확인 |
| 데이터 수정 이벤트 | 해당 ID를 revision이 있는 `invalidated` 상태로 바꾸고 다음 조회가 원본을 다시 저장 |
| 삭제·비공개 이벤트 | 해당 ID를 `deleted` 상태로 바꿔 오래된 데이터 노출 차단 |
| R2 조회·저장 장애 | 공개 API로 fail-open. 원본 실패까지 숨기지는 않음 |
| 원본 API 장애 | fresh가 지난 기존 정상 데이터가 있으면 최대 6시간 stale fallback, 없으면 오류 |
| 손상되거나 호환되지 않는 R2 객체 | 기존 ETag 조건으로 정상 원본 결과를 덮어써 복구 |
| 동시에 여러 조회 | R2 ETag 조건부 쓰기로 한 요청만 승리하고 패자는 최신 객체를 다시 확인 |
| 조회 중 더 최신 변경 발생 | 오래된 조회의 조건부 쓰기가 실패하고 최신 revision 이후 원본을 다시 조회 |
| 중복·역순 이벤트 | 화장실별 증가 revision으로 오래된 이벤트를 무시. 같은 이벤트 재시도는 멱등 처리 |

기본 fresh 시간은 기존과 같은 1시간이다. 변경 이벤트가 정상 전달되면 그 전에 갱신되고, 이벤트 누락이나 수신 장애 때 1시간 재검증이 보조 장치로 남는다. 운영 표본에서 원본 호출량과 변경 반영 지연을 측정하기 전에는 TTL을 늘리거나 제거하지 않는다.

## 변경 이벤트 계약

기존 v1 `{ "toiletIds": [1, 2] }` 수신은 전환 중 계속 지원한다. 공유 데이터 캐시를 켜는 시점에는 API가 아래 v2 이벤트를 전송한다.

```json
{
  "contractVersion": 2,
  "events": [
    { "toiletId": 1, "revision": 17, "action": "UPSERT", "catalogChanged": false }
  ]
}
```

- `revision`: 해당 화장실의 단조 증가 변경 번호
- `action`: `UPSERT`, `DELETE`, `PRIVATE`
- `catalogChanged`: 상세뿐 아니라 공개 ID 목록과 사이트맵도 갱신해야 하는지 표시
- 한 요청은 최대 100건이며 정확한 ID·revision ACK를 받아야 outbox가 전달 완료된다.
- HMAC v1 서명 문자열, 5분 시차 검증, 전용 비밀키, 공개 호출 금지 원칙은 그대로 유지한다.

V2 outbox는 전달 완료 행을 삭제하지 않고 `delivered_at`으로 표시해 다음 이벤트 revision의 기준으로 쓴다. 행에는 화장실 ID, 전송 상태와 제한된 오류 코드만 있으며 개인정보나 응답 본문은 넣지 않는다.

## API·배치별 갱신 대상

현재 코드에서 확인한 공개 데이터 변경 경로다. 실제 `toilet`, 기존 `toilet_region`, 정규화된 `toilet_region_assignment`와 `toilet_region_decision`의 커밋 뒤 DB 트리거가 이벤트를 만든다.

| HTTP 메서드·경로 또는 작업 | 변경 데이터 | 영향받는 캐시 | 현재 연결/보강 |
| --- | --- | --- | --- |
| `POST /api/v1/reports` | 제보 대기열만 생성 | 없음 | 원본 공개 데이터 미변경이므로 무효화 안 함 |
| `POST /api/admin/v1/reports/{reportId}/approve` | 승인 종류에 따라 좌표·주소·개방시간 등 `toilet` | 공유 상세, 배포별 상세 페이지. 좌표는 다음 지도 API 조회에도 반영 | 기존 toilet 트리거, v2 revision으로 보강 |
| `POST /api/admin/v1/reports/{reportId}/reject` | 제보 상태 | 없음 | 공개 데이터 미변경 |
| `POST /api/admin/v1/data-quality/toilets/{toiletId}/coordinates` | 좌표와 확정 주소 | 공유 상세, 배포별 상세 페이지, 다음 지도 API 조회 | 기존 toilet 트리거, v2 revision으로 보강 |
| display-group 생성·수정·삭제 API | 지도 표시 그룹 | 지도 API 응답 | 현재 지도는 브라우저 직접 조회하며 OpenNext R2 캐시 없음 |
| 중복좌표 review 상태 API | 관리자 검토 상태 | 없음 | 공개 시설 데이터 미변경 |
| `POST /api/admin/v1/regions/{id}/district` | 지역 override·decision | 공유 상세, 배포별 상세 페이지 | 정규화 decision 트리거 추가 |
| `POST /api/admin/v1/regions/{id}/coordinates` | 좌표·주소와 지역 재판정 | 공유 상세, 배포별 상세 페이지, 다음 지도 API 조회 | toilet·정규화 지역 트리거로 포착 |
| `POST /api/admin/v1/public-data-change-reviews/{id}/decisions`의 `APPLY` | 공공데이터 후보를 `toilet`에 적용 | 공유 상세, 배포별 상세 페이지 | toilet 트리거로 포착 |
| 같은 API의 `KEEP_CURRENT`, `DEFER` | 검토 상태·이력 | 없음 | 공개 데이터 미변경 |
| 공공데이터 동기화 배치 | toilet 삽입·수정 | 공유 상세, 배포별 상세. 신규 ID는 사이트맵 | DB 트리거로 API 밖 변경도 포착 |
| 행정구역 판정 배치 | assignment·decision | 공유 상세, 배포별 상세 페이지 | 정규화 테이블 트리거 추가 |
| toilet 직접 삭제 | 상세 데이터 삭제 | 공유 상세 tombstone, 상세 404, 사이트맵 | DELETE 이벤트와 catalog 변경 |
| 향후 공개→비공개 전환 | 공개 여부 | 공유 상세 tombstone, 상세 404, 사이트맵 | `PRIVATE` 계약 준비. 현재 별도 HTTP 경로는 없음 |
| 리뷰 작성·수정·작성자 분리 | 리뷰/평점/프로필 표시 | 기존 리뷰 브라우저 캐시와 사진 캐시 | 시설 공유 캐시·페이지 캐시 대상 아님 |

`toilet` 신규 INSERT와 DELETE는 `catalogChanged=true`다. 일반 정보·좌표·지역 변경은 상세 데이터만 바꾸므로 사이트맵 전체를 다시 만들지 않는다. 향후 공개 여부 컬럼이 생기면 공개 전환도 catalog 변경 이벤트로 연결한다.

## 전체 상세 페이지 사전 생성

수동 GitHub Actions 후속 작업이 다음 순서로 실행된다.

1. `/version.json`이 입력한 정확한 배포 ID인지 확인한다.
2. 사이트맵 인덱스와 같은 origin의 화장실 shard만 읽어 공개 ID를 중복 제거한다.
3. 서비스는 이미 사용자 요청을 처리하는 상태로 둔 채 `/toilet/{id}`를 백그라운드 요청한다.
4. 전역 초당 요청 수와 동시 요청 수를 제한하고 429/5xx만 지수 재시도한다.
5. 화장실마다 체크포인트를 원자적으로 저장한다. Actions cache를 통해 같은 배포의 다음 실행이 이어받는다.
6. 실행 중 배포 ID를 주기적으로 다시 확인한다. 새 실행은 이전 배포의 Actions 작업을 취소한다.
7. 완료 항목 일부를 다시 요청해 `x-nextjs-cache` 또는 `x-opennext-cache`의 HIT/STALE/REVALIDATED 증거를 확인한다.
8. 성공·실패 ID, 속도, 검증 결과와 치명 오류를 artifact 보고서로 남긴다.

워크플로는 `workflow_dispatch` 전용이며 저장소 변수 `CACHE_PREWARM_ENABLED=true`와 보호된 `production-cache-maintenance` 환경 승인을 모두 받아야 실행된다. 현재 변수는 활성화하지 않는다. 표본 ID → 한 sitemap shard → 전체 순서로 확대한다.

약 53,600개를 오류 없이 요청할 때 이론상 시간은 1 req/s 약 14시간 53분, 2 req/s 약 7시간 27분, 4 req/s 약 3시간 43분이다. 실제 시간은 응답과 재시도에 따라 늘어난다. 기본 전체 계획은 2 req/s이고 5시간 제한에서 중단되면 같은 배포 체크포인트로 다음 실행을 이어간다. 표본 측정 전 임의로 속도를 높이지 않는다.

## 오래된 배포 캐시 정리

정리 대상은 운영 증분 캐시 버킷의 `incremental-cache/{buildId}/...` 중 릴리스 기록으로 배포를 식별할 수 있는 객체뿐이다.

- Worker의 현재 트래픽 분배에 포함된 모든 버전을 보호한다.
- 직전 정상 배포는 퇴역 시점부터 최소 3일 보호한다.
- 공유 데이터 `public-toilets/v1/...`, 정적 자산, 프로필 사진과 다른 버킷은 대상이 아니다.
- 릴리스 기록이 없거나 경로를 해석할 수 없는 객체는 보고서의 unknown으로 분류하고 삭제하지 않는다.
- 실행 시작과 삭제 직전에 Worker 활성 버전을 다시 읽는다. 배포가 바뀌거나 활성 버전의 manifest가 없으면 중단한다.
- dry-run이 기본이며 삭제에는 별도 `--execute`와 `CACHE_CLEANUP_ENABLED=true`가 모두 필요하다.
- 대상·보호·unknown의 파일 수와 용량, 보존 사유, 실제 삭제 결과를 JSON으로 남긴다.
- 정리 실패는 배포를 자동 롤백하지 않고 별도 운영 실패로 보고한다.

배포 기록은 Worker UUID, 앱 배포 ID, OpenNext build ID, 소스 커밋과 배포 시각을 함께 보존한다. 객체 생성일만으로 삭제 여부를 판단하지 않는다.

## 설정과 비밀정보

| 위치 | 이름 | 용도 |
| --- | --- | --- |
| Worker 비밀 | `CACHE_REVALIDATION_SECRET` | API → Worker HMAC 검증. 기존 키 유지 |
| Worker 변수 | `SHARED_TOILET_CACHE_ENABLED` | 공유 상세 데이터 캐시. 초기 `false` |
| Worker 변수 | `SHARED_TOILET_CACHE_FRESH_SECONDS` | 기본 3600초 |
| Worker 변수 | `SHARED_TOILET_CACHE_STALE_SECONDS` | 장애 fallback 기본 21600초 |
| Worker 변수 | `SHARED_TOILET_CACHE_NEGATIVE_SECONDS` | 404 기본 300초 |
| Worker R2 binding | `PUBLIC_TOILET_DATA_CACHE_R2` | 환경별 기존 OpenNext R2 버킷을 가리키며 `public-toilets/v1/` prefix만 사용 |
| API 변수 | `WEB_CACHE_CONTRACT_VERSION` | 초기 `1`, 공유 캐시 전환 뒤 `2` |
| Actions 변수 | `CACHE_PREWARM_ENABLED` | 사전 생성 이중 잠금. 초기 미설정/false |
| Actions 변수 | `CACHE_CLEANUP_DRY_RUN_ENABLED` | 정리 계획 생성 이중 잠금. 초기 미설정/false |
| Actions secret | `CACHE_STATUS_API_TOKEN` | Worker 활성 배포 읽기 전용 |
| Actions secret | `R2_CACHE_READ_ACCESS_KEY_ID`, `R2_CACHE_READ_SECRET_ACCESS_KEY` | 정리 dry-run용 목록 읽기 전용 |

실제 비밀값은 코드, 문서, WBS, Actions artifact에 기록하지 않는다. 삭제 자동화를 나중에 승인할 경우에도 읽기 키와 별도 최소 권한 삭제 키를 분리한다.

## 운영 전환 순서

1. 코드 검사와 격리 MySQL CI를 통과시킨다. 현재 운영 값과 객체 수를 읽기 전용으로 기록한다.
2. 환경별 기존 OpenNext R2 버킷의 공유 데이터 전용 binding과 `public-toilets/v1/` 분리를 확인하되 기능 플래그는 `false`로 둔다. 새 버킷은 필요하지 않다.
3. DB 백업·트리거 충돌·테이블 존재를 확인한 뒤 수동 V2 outbox SQL을 적용하고 설치 검증 SQL을 실행한다.
4. V2 컬럼을 읽을 수 있는 API를 배포하되 `WEB_CACHE_CONTRACT_VERSION=1`을 유지한다.
5. v1/v2를 모두 받는 Web을 배포한다. 기능이 꺼져 있으면 기존 1시간 Next fetch 경로가 그대로 동작한다.
6. 공유 캐시를 preview와 운영 표본에서 차례로 켜고 HIT, 원본 장애, 수정·삭제 반영을 확인한다.
7. API 계약을 `2`로 바꾸고 outbox 전달 지연·실패·revision 증가를 확인한다.
8. 사전 생성은 소수 ID, 한 shard, 전체 순서로 승인·실행한다. 전체 서비스는 먼저 열린 상태를 유지한다.
9. 릴리스 기록을 충분히 모은 뒤 정리 dry-run만 실행한다. active/직전/unknown 판정을 사람이 확인하고 최소 3일 후 삭제를 별도 승인한다.

되돌릴 때는 공유 캐시 플래그를 먼저 끄면 기존 1시간 Next fetch 경로로 즉시 돌아간다. API 계약은 `1`로 되돌릴 수 있고 V2 수신자는 v1을 계속 받는다. 트리거 문제가 있으면 승인 후 rollback SQL로 이 작업이 만든 트리거만 제거하고 outbox 행과 원본 업무 데이터는 보존한다. 페이지 문제는 검증된 직전 Worker 버전으로 트래픽을 되돌리며 공유 R2와 증분 R2를 삭제하지 않는다.

## 검증과 아직 남은 항목

단위 검사 범위는 배포 간 공유 데이터 재사용, 개인정보 필드 제외, negative cache, 손상 객체 복구, 수정 중 오래된 조회 경쟁, 삭제·역순 이벤트, 원본 장애 fallback, 사전 생성 속도 제한·체크포인트·배포 변경 감지, 정리 active/rollback/unknown 보호를 포함한다. Web lint·typecheck·Next/OpenNext 빌드와 API 단위 검사를 함께 수행한다.

MySQL 8 트리거의 commit/rollback, revision 증가, normalized region 변경, 삭제 tombstone, 전송 재시작은 Testcontainers 통합 검사 대상이다. 로컬 Docker가 없으면 운영 DB로 대신하지 않고 Linux CI 결과를 운영 전환 조건으로 남긴다. 실제 운영 부하, 전체 사전 생성 시간, 운영 R2 삭제, 공개→비공개 전환 API는 이번 구현 검증에 포함하지 않는다.
