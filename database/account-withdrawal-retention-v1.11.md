# 회원 탈퇴 · 선택적 3개월 복구 · 자동 파기 v1.11

상태: **로컬 구현·격리 검증 단계. 운영 DB·운영 서비스에 미적용.**

## 결정

- 탈퇴는 즉시 이용 중지다. 복구용 정보 보관은 기본 미선택이며 동의하지 않아도 탈퇴할 수 있다.
- 선택 동의한 계정만 한국시간 탈퇴 시각의 **달력상 3개월 뒤**까지 복구 가능하다. 90일로 계산하지 않는다. 1월 31일 → 4월 30일처럼 말일은 해당 달의 마지막 날로 조정한다.
- 복구는 동일 Google/Kakao 고유 계정으로 새 OAuth 인증 후 사용자가 명시적으로 확인해야 한다. 이메일 일치로 연결하지 않는다.
- 복구는 기존 회원 ID·닉네임·제보 연결을 유지하지만 ADMIN은 복구하지 않는다. USER만 부여하고 필수 정책에 다시 동의한다.
- 미동의·보관 철회·기한 만료 시 회원정보를 물리 삭제한다. 제보는 구조화된 화장실 수정 정보와 처리 상태를 남기고 작성자 연결·자유 입력 사유를 제거한다.
- 기존 WITHDRAWN 행은 복구 동의가 없으므로 새 정책에 자동 편입하거나 무단 일괄 삭제하지 않는다. 별도 점검 대상이다.

## 데이터 모델

[DDL](ddl/v1.11-account-withdrawal-retention.sql)은 API Flyway V11과 같은 내용이다. 운영은 기존 수동 DDL 정책과 Flyway 이력 관리 방식에 맞춰 적용하며, 두 경로로 중복 실행하지 않는다.

| 구조 | 용도 |
| --- | --- |
| `app_user.auth_version` | 탈퇴·복구 시 증가. 탈퇴 전에 발급한 JWT가 복구 후 다시 살아나는 것을 차단 |
| `audit_log.actor_erased` | 파기된 작성자를 시스템 이벤트와 구분해 `탈퇴한 사용자`로 표시 |
| `toilet_report.reporter_user_id NULL 허용` | 제보를 보존하면서 회원 FK 연결 제거 |
| `coordinate_revision.applied_by_user_id NULL 허용` | 좌표 수정 이력을 보존하면서 파기된 회원 연결 제거 |
| `account_withdrawal` | 동의·탈퇴 시각, 복구 허용 여부, 기한, 닉네임 복구 사본, 재시도 체크포인트 |

### account_withdrawal 속성

| 속성 | 한글명 · 의미 |
| --- | --- |
| user_id | 회원 ID. PK·app_user FK |
| withdrawal_key | 탈퇴 회차 난수. 이전 회차 인증으로 재복구하지 못하도록 구분 |
| withdrawn_at | 탈퇴 접수·선택 동의 시각(KST) |
| purge_after | 파기 기준 시각. 복구는 이 시각 **미만**에서만 허용 |
| recovery_allowed | 선택 동의 여부. 즉시 삭제 요청 시 false |
| consent_version | 실제 선택 동의한 안내 버전. `recovery-2026-09-v1` |
| recovery_display_name | 선택 동의한 경우만 닉네임 복구 사본 |
| attempts | 파기 실패 후 재시도 횟수 |
| next_attempt_at | 다음 처리 가능 시각. 초기에는 purge_after |
| last_failure_code | 개인정보 없는 고정 실패 코드 |

인덱스 `idx_withdrawal_due(next_attempt_at, user_id)`는 `WHERE next_attempt_at <= now ORDER BY next_attempt_at,user_id LIMIT 50`에 대응한다.

## 탈퇴 즉시 처리

1. 회원 행을 잠그고 선택 동의 버전을 확인한다. 동일 탈퇴 요청으로 기한을 연장하지 않는다.
2. 계정을 WITHDRAWN으로 변경하고 이름을 `탈퇴한 사용자`로 대체한다. 이메일·인증 여부·최근 로그인 시각을 정리한다.
3. 기존 역할 제거, 기존 필수 정책 동의에 철회 시각 기록, Redis 리프레시 토큰 전체 폐기.
4. 복구 선택 시 소셜 제공자·기존 고유 식별자 해시만 연결용으로 유지하고 제공자 이메일·최근 로그인 시각을 지운다. 해시도 개인정보로 취급한다.
5. 미선택이면 소셜 연결을 삭제하고 같은 요청에서 파기 서비스를 실행한다. 실패하면 HTTP 202(접수·재시도)이며 파기 완료라고 안내하지 않는다.

## 복구 인증

- 일반 access/refresh 토큰을 발급하지 않고 10분짜리 랜덤 256-bit 확인 쿠키만 발급한다.
- 쿠키는 HttpOnly·Secure·SameSite=Lax·`/api/v1/auth/recovery` 전용 경로다. URL에는 토큰·회원 ID가 없다.
- Redis 증명에는 회원 ID와 탈퇴 회차만 저장한다. API 요청은 DB의 회차·기한·상태를 다시 검사한다.
- OAuth 세션을 종료해 서비스 인증 세션으로 우회하지 못하게 한다.
- 복구/즉시 삭제 요청은 허용된 웹 Origin만 수락한다. 다른 사이트나 이메일만으로는 복구 불가.
- 복구 또는 파기 시 DB 상태가 변경되므로 동시 요청·재사용 증명은 거부된다.

## 실제 파기 범위

회원 한 명마다 별도 트랜잭션으로 다음을 수행한다.

| 데이터 | 조치 |
| --- | --- |
| Redis refresh·복구 증명 | 해당 회원 키 삭제. 접근 권한은 DB 상태/버전 검증으로도 차단 |
| user_social_account / user_role | 해당 회원 행 삭제; 다른 역할의 부여자 참조는 NULL |
| user_notification / user_policy_consent | 회원별 알림·동의 원본 삭제 |
| toilet_report | 제보 유지, reporter_user_id=NULL, 자유 사유 대체, 검토 메모·중복요청 연결 해시 제거 |
| 제보 검토자·좌표 변경자·품질검토자 | 해당 회원 참조 NULL, 자유 검토 메모 제거 |
| audit_log | 해당 회원 actor/USER target 연결과 상세 JSON 제거. 이벤트 종류·시각 등 남김 |
| account_withdrawal / app_user | 마지막에 행 삭제 |
| toilet 및 확정된 좌표·주소·개방시간 | 변경하지 않음 |

닉네임만 바꾸는 것을 완전 익명화라고 표현하지 않는다. 제보 주소·시간 등 다른 정보와 결합한 재식별 위험도 별도로 평가해야 한다. 이 기능은 회원 연결 정보 파기이며 제보·감사 전체의 3년 만료 정리 작업까지 구현한 것은 아니다.

## 자동 파기 및 장애

- Spring 스케줄러가 **1분마다 최대 50명**을 처리한다. AI나 사용자 PC가 계속 실행될 필요가 없다.
- `ACCOUNT_RETENTION_ENABLED=true` 활성화가 필요하다. 기본 false이며 배포 전 검증을 마친 후 설정한다.
- 재시작 시 DB의 미처리 기한을 다시 조회하므로 누락된 작업도 이어서 처리한다.
- 복구/파기 모두 회원 행 잠금으로 직렬화한다. 만료 시각이 지나면 실제 삭제가 지연돼도 복구는 불가하다.
- SQL·새 FK·Redis 장애 시 DB 파기 전체를 롤백하고 별도 트랜잭션으로 실패 횟수를 갱신한다. 2·4·8·16·32·최대 60분 간격으로 재시도한다.
- 한 회원 실패가 다른 회원 처리를 막지 않는다. 동일 계정의 중복 실행은 상태 재확인 후 no-op이다.
- 성공/실패 건수와 기한 경과 대기 건수를 Prometheus에 제공한다. 로그에는 이름·소셜 식별자·SQL 인자·예외 원문을 남기지 않는다.

## API 계약

| API | 용도 |
| --- | --- |
| GET /api/v1/auth/withdrawal-options | 로그인 필요. 기능 활성화, 선택 동의 버전, 예상 삭제일 |
| DELETE /api/v1/auth/me | `{retainForRecovery, consentVersion}`. false 또는 본문 미제공은 복구 미선택 |
| GET /api/v1/auth/recovery | OAuth 확인 쿠키로 삭제 예정일·복구 닉네임 확인(no-store) |
| POST /api/v1/auth/recovery | `{action:"RESTORE"}` 또는 `{action:"ERASE"}`. 명시 확인 |
| DELETE /api/v1/auth/recovery | 확인 쿠키 종료. 계정 상태는 변경하지 않음 |

토큰 만료 시 소셜 인증부터 다시 시작한다. 로컬 개발 Origin을 운영 복구 API에 임의 추가하지 않는다. 로컬 UI 검증은 mock API를 사용한다.

## 배포 및 백업 안전장치

[운영 적용·파기 검증 절차](../operations/account-erasure-runbook.md)를 반드시 먼저 확인한다. 정책 문구는 배포 예정 초안이며 실제 시행일·백업 기간·관련 고지를 운영 설정과 일치시킨 후 공개한다.
