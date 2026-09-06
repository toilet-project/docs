# 회원정보 자동 파기 운영 절차

상태: 로컬 구현. **운영 활성화·실제 회원 삭제는 아직 하지 않았다.**

후속 검증: [로컬 MySQL 8.0.25에서 17건 통과](account-retention-native-mysql-2026-09-06.md). 운영 동일 버전/전체 스키마 검증은 남아 있다.
[백업 재파기 설계](account-erasure-backup-design.md)는 별도 저장소 선택을 기다리는 초안이며 아직 구현되지 않았다.

## 적용 전 체크

- [ ] 개인정보처리방침의 기존 탈퇴 시 보유 기간과 선택 동의 문구·시행일을 검토하고 사전 안내.
- [ ] 운영 DB 스키마와 FK 전체 확인. 아래 목록에 새 회원 참조가 있으면 파기 코드부터 보완.
- [ ] 실제 MySQL의 격리 복제 스키마에 V11 DDL 설치·복구·파기·동시 요청 시험.
- [ ] 제보 사유·검토 메모를 파기하는 것에 따른 운영상 영향 확인. 구조화된 수정안과 이미 반영된 화장실은 유지.
- [ ] 백업 보관 기간, SQL 덤프·스냅샷·binlog·Redis 백업·외부 사본의 위치와 파기 방법 확정.
- [ ] 삭제 대장을 백업 장애 영역 밖에 보호해 보존하고, 복원 후 파기 재적용 리허설 완료.
- [ ] 배치의 API와 동일한 Redis 인스턴스/DB 설정, 회원 관련 DB SELECT/UPDATE/DELETE 권한, API·배치 SQL 계약 일치 확인.
- [ ] 매일 공공데이터 동기화 종료 후 파기하는 처리 주기와 실제 삭제 지연 가능성을 정책에 반영.
- [ ] 위 체크 전에는 `ACCOUNT_RETENTION_ENABLED=false` 유지. 이 상태의 신규 탈퇴 요청은 503 점검 안내이며 개인정보 문의 경로를 제공.

운영 스키마 점검용 읽기 SQL:

```sql
SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME = 'app_user';

SELECT COUNT(*) AS legacy_withdrawn_accounts
FROM app_user u LEFT JOIN account_withdrawal w ON w.user_id=u.user_id
WHERE u.status='WITHDRAWN' AND w.user_id IS NULL;
```

두 번째 쿼리는 V11 설치 후 사용한다. 기존 탈퇴 행을 자동으로 새 3개월 보관에 편입하지 않는다.

## 적용 순서

1. 쓰기 점검 창을 확보하고 운영 DB 복구 가능한 백업을 확인한다.
2. 격리 MySQL에서 [DDL](../database/ddl/v1.11-account-withdrawal-retention.sql)과 현재 전체 회원 FK를 검증한다. MySQL DDL은 일반 데이터 트랜잭션처럼 전체 롤백되지 않는다.
3. 수동 DDL/기존 Flyway 운영 절차 중 하나로만 설치한다. 중복 적용·체크섬 임의 수정 금지.
4. 새 API와 배치를 배포하되 각각 ACCOUNT_RETENTION_ENABLED=false / ACCOUNT_ERASURE_ENABLED=false 유지. API에는 정기 파기 스케줄러가 없다. auth_version=0인 기존 JWT는 계속 호환된다.
5. mock UI 검증과 테스트 계정으로 실제 OAuth 인증·선택 동의·복구·권한 경계를 검증한다. 정상 사용자 계정을 실험용으로 삭제하지 않는다.
6. 정책/웹을 함께 반영하고 백업·모니터링 준비가 확인된 뒤 두 스위치를 활성화한다. 현재 배치 배포 스크립트는 ACCOUNT_ERASURE_ENABLED=false로 고정했으므로 검증 후 별도 변경 승인이 필요하다. API에만 enabled=true를 설정해서 정기 파기가 된다고 판단하지 않는다.
7. 기한을 짧게 조정한 **격리 테스트 DB**에서 자동 파기를 확인한다. 운영 회원의 기한을 테스트 목적으로 변경하지 않는다.

## 매일 확인할 지표

- `account_erasure_completed_total`: 프로세스 기동 이후 파기 성공 수
- `account_erasure_failed_total`: 프로세스 기동 이후 실패 수
- `account_erasure_overdue`: 기한 경과 미완료 수
- DB 체크포인트는 재기동 후에도 유지되며 메트릭 카운터는 재기동하면 초기화된다.

```sql
SELECT COUNT(*) AS overdue,
       MIN(purge_after) AS oldest_deadline,
       MAX(attempts) AS max_attempts
FROM account_withdrawal
WHERE purge_after <= NOW();

SELECT last_failure_code, COUNT(*) AS accounts
FROM account_withdrawal
WHERE attempts > 0
GROUP BY last_failure_code;
```

DB 세션의 NOW()가 KST인지 먼저 확인한다. 정기 파기는 02:00 동기화 종료 후이므로 기한 직후 5분 대기만으로 장애라고 판단하지 않는다. 후속 작업 종료 뒤 실패·미완료가 남거나 일일 배치 자체가 끝나지 않으면 운영자가 조사한다. 코드상 기존 BATCH_FAILURE_WEBHOOK_URL로 집계 알림을 연결했지만 실제 Discord 전달은 아직 검증하지 않았다. 파기 성공 이력은 프로세스 로그·메트릭이며 별도 영구 삭제 대장이 아니다.

## 실패 처리

- SQL 오류/FK 추가: 회원 연결을 일부만 삭제하지 않도록 전체 트랜잭션이 롤백된다. FK를 무조건 제거하거나 FOREIGN_KEY_CHECKS=0으로 우회하지 않는다.
- Redis 장애: 복구·리프레시 증명을 확실히 지우기 전 DB 파기를 끝내지 않는다. WITHDRAWN/auth_version 검사로 서비스 접근·복구는 계속 막는다.
- 서비스 중지: 다시 시작한 뒤 다음 일일 공공데이터 동기화 종료 시 next_attempt_at 기준으로 기한 경과 건을 찾는다. 동일 스케줄 누락을 이유로 복구 기한을 연장하지 않는다.
- 공공데이터 동기화가 실패로 종료돼도 파기는 실행한다. 동기화가 종료되지 않은 장기 실행/중단이라면 후속 작업도 시작되지 않으므로 배치 실행 완료 감시가 필요하다.
- 한 실행 최대 5,000명(설정 가능), 50명씩 처리한다. 실패한 계정/상한 초과 건은 다음 일일 실행까지 남으므로 집계 알림을 확인한다.
- 실패 코드에는 개인정보를 쓰지 않는다. 상세 SQL/사용자 행은 필요할 때 제한된 관리자 권한으로만 확인한다.

## 백업에서 다시 살아나는 것을 방지

**현재 코드가 DB 행을 지우는 것만으로 기존 백업 파일까지 즉시 삭제되는 것은 아니다.** 기존 백업 스크립트는 기본 14일이지만 운영 환경 변수·스냅샷·수동 백업의 실제 기간은 이번 작업에서 확인하지 않았다.

활성화 전 반드시 다음을 별도로 완성한다.

1. 파기 작업과 연동한 삭제 대장을 별도 장애 영역에 내보낸다. 복원 대상 식별에 필요한 최소 정보·삭제 시각만 보존하고 접근 제한·최대 보관 기간을 정한다. 이것 역시 개인정보 관리 대상이며 별도 근거가 필요하다.
2. 백업은 일반 서비스 조회·재가입 복구에 사용하지 않는다. 명시된 보관 기간이 지나면 덤프뿐 아니라 복제본·임시 복호화 파일·로그 사본까지 파기한다.
3. 복구는 외부 네트워크가 차단된 환경에서 실행한다. 복원 시점 이후의 삭제 대장을 재적용한 뒤 회원·소셜·제보 연결·Redis 키가 다시 생기지 않았는지 검사한다.
4. 재적용 검증이 끝나기 전 복구 DB를 운영 트래픽에 연결하지 않는다.
5. 삭제 대장 자동 내보내기와 실제 백업 만료 처리 연동은 아직 미구현이다. 이 조건이 해소되기 전 운영 자동 파기를 활성화하지 않는다.

## 롤백

- 활성화 전이면 API/웹을 이전 버전으로 되돌릴 수 있으나 WITHDRAWN 복구 대기 계정이 생긴 이후에는 기존 OAuth 코드로 롤백하면 안 된다. 기존 코드는 복구 상태를 처리하지 못한다.
- 문제가 생기면 먼저 신규 접수와 OAuth 복구를 점검 모드로 차단하고 데이터를 보존한 상태로 전진 수정한다. 파기 지연과 개인정보 요청 대응을 운영자가 관리한다.
- 이미 파기한 회원정보는 일반 기능으로 되살리지 않는다. 파기된 사용자 복구를 위해 운영 백업을 복원하는 것은 금지한다.
- nullable 변경은 파기된 제보가 생긴 뒤 NOT NULL로 되돌릴 수 없다. 스키마 롤백 SQL을 무조건 실행하지 않는다.

## 남은 범위

기존 탈퇴 회원 정리, 제보/감사 전체의 3년 경과 자동 파기, 외부 소셜 제공자 측 연결 해제 API, 백업 삭제 대장 연동은 별도 검토·구현 대상이다. 본 기능을 구현했다고 개인정보 수명주기 전체가 완료된 것으로 표시하지 않는다.
