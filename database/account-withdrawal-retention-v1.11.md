# 회원 탈퇴·선택 복구 데이터 모델 V11

2026-09-10 현재 운영 적용 상태. V11은 앞선 준비 배포에서 적용됐고 이번 문서 작업은 DDL을 실행하지 않는다. 실행 원본은 API Flyway `V11__account_withdrawal_retention.sql`, 이 문서의 [SQL 사본](ddl/v1.11-account-withdrawal-retention.sql)은 설명·대조용이다. 중복 적용 금지.

| 변경 | 목적 |
| --- | --- |
| app_user.auth_version BIGINT NOT NULL DEFAULT 0 | 탈퇴·복구 후 과거 access token 재사용 차단 |
| audit_log.actor_erased BOOLEAN NOT NULL DEFAULT FALSE | 시스템 행위와 탈퇴한 행위자 구분 |
| toilet_report.reporter_user_id NULL 허용 | 제보 행 보존 및 회원 FK 분리 |
| coordinate_revision.applied_by_user_id NULL 허용 | 좌표 변경 업무 이력 보존 및 회원 연결 분리 |
| account_withdrawal | 탈퇴 회차·선택 보관·기한·재시도 상태 |

## account_withdrawal

| 필드 | 의미 |
| --- | --- |
| user_id | PK, app_user FK |
| withdrawal_key | 탈퇴 회차 UUID. 다른 회차의 복구 증명 사용 금지 |
| withdrawn_at / purge_after | KST DATETIME(6). 복구는 purge_after 미만에서만 가능 |
| recovery_allowed | 별도 선택 동의 여부. 미동의 또는 삭제 요청은 false |
| consent_version | 실제 복구 보관 안내 버전. 정책 게시 버전과 별도 |
| recovery_display_name | 동의한 경우만 복구 닉네임 사본 |
| attempts / next_attempt_at / last_failure_code | 파기 재시도 횟수·가능 시각·고정 실패 코드 |

인덱스 `idx_withdrawal_due(next_attempt_at, user_id)`와 user_id PK를 사용한다. 배치는 user_id keyset으로 순회한다. 이번 문서화에서 인덱스 추가나 쿼리 성능 보장을 하지 않는다.

## 삭제와 보존

회원정보 파기는 해당 회원의 세션·소셜 연결·역할·알림·동의 원본·계정/탈퇴 행 및 제보/감사의 개인정보 연결을 대상으로 한다. 구조화된 화장실 정보와 개인정보를 제거한 업무 이력 행은 유지한다. 모든 제보·감사를 기간 기준으로 지우는 기능은 범위에서 철회됐다.

미동의 파기 204와 미완료 202를 구분한다. 같은 소셜 재인증과 명시 복구를 요구하며 ADMIN은 자동 복원하지 않는다. 기한 만료 후 삭제가 지연돼도 복구는 불가하다. 기존 탈퇴 행에 동의·기한을 소급 생성하지 않는다.

배포 설정을 되돌리는 것과 파기된 회원 데이터 복구는 다르다. 활성화 이후 복원은 국내 보호 기록·독립 기준을 재적용하는 승인된 복원 절차를 따라야 한다. [현재 구조·API·운영 근거](../operations/account-lifecycle-current-2026-09-10.md).
