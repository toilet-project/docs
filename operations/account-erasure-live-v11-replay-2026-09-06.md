# 최신 백업 V1.11 적용·가상 회원 파기 재적용 검증

검증일: 2026-09-06 KST. **격리 복사본 검증 통과 / 운영 DDL·파기 기능은 아직 미적용**.

## 결과

| 검사 | 결과 |
| --- | --- |
| 사용 백업 | `toilet-db-20260905-181509.sql.gz.enc` — 앞선 구조 복원 검사와 동일 파일 |
| 실행 시간 | 23:45:16~23:46:10 KST, 약 54초 |
| 실제 엔진 | 운영과 같은 로컬 이미지의 MySQL 8.0.46, 별도 일회용 컨테이너 |
| 복원 직후 | 기존 16개 테이블, 화장실 53,583건, 13개 외래키 관계의 참조 불일치 0 |
| V1.11 DDL | 기존 SQL 파일 그대로 적용 성공. DDL 자체 수정 없음 |
| DDL 전후 보존 | 기존 16개 테이블의 원래 컬럼 전체에 대해 PK 정렬·SHA-256 비교 일치 |
| 신규 값 | `auth_version=0`, `actor_erased=false`, `account_withdrawal` 빈 상태 확인 |
| nullable·인덱스 | 제보자/좌표 수정자 컬럼 nullable, 파기 재시도 복합 인덱스 확인 |
| dry-run | 가상 대상 2건 매칭, 실제 삭제 0, 전체 내용 동일 |
| 회원 식별 불일치 | 두 번째 대상의 생성 시각 불일치 → 첫 번째 대상도 변경되지 않음 |
| 알 수 없는 FK | 두 번째 대상에 검증용 FK 추가 → 첫 번째 파기를 포함한 전체 트랜잭션 롤백 |
| 파기 적용 | 실제 공유 Java 서비스로 가상 회원 2건 파기 커밋 확인 |
| 제보·감사 이력 | 제보/좌표 값은 유지, 탈퇴자 연결·사유·검토 메모·감사 상세 정보는 설계대로 제거 |
| 재실행 | 이미 파기된 2건은 부재 처리, 추가 삭제/변경 0 |
| 최종 원본 보존 | 가상 자료 정리 후 기존 16개 테이블의 원래 컬럼 전체 해시 동일 |
| 검증 확인문 | Java 런타임 assertion 75개 통과. 서로 독립된 테스트 75건이라는 의미는 아님 |
| 정리 | 일회용 DB 컨테이너·익명 볼륨·전용 내부 네트워크 제거 확인 |

운영 회원을 시험 파기 대상으로 선택하지 않았다. 실제 백업의 회원 데이터는 격리 DB에서 보존 대조를 위해 프로세스 메모리로만 읽었다. 개별 행·해시·덤프·키·원문 SQL 오류를 출력하거나 로컬로 가져오지 않았다.

## 적용한 DDL과 실행 코드

- [V1.11 DDL](../database/ddl/v1.11-account-withdrawal-retention.sql): `app_user.auth_version`, `audit_log.actor_erased`, 두 참조 컬럼의 NULL 허용, `account_withdrawal` 및 재시도 인덱스.
- [격리 실행 도구](scripts/verify-live-backup-isolated.py): 기본 구조 검사 유지, 명시적인 `--v11-synthetic-replay` 모드 추가.
- [Java 검증 소스](scripts/LiveBackupV11Replay.java): Spring 서버를 시작하지 않는 시험용 source launcher. 배치 feature의 실제 `AccountErasureRestore`와 `AccountErasureSql`을 호출한다.
- 배치 도구는 `feature/account-withdrawal-retention`의 `d9e31f6`에서 `installErasureTools`로 확인했다. 공유 계약 Java 8개는 API와 동일했다. 이번에 API/배치 애플리케이션 소스는 변경하지 않았다.

DDL SHA-256:

```text
c02aee7f50ac3ed68d378150d076f40f2f43adaff4b871d897fd8595f000fced
```

실행한 Java 검증 소스 SHA-256:

```text
f82c60ceb990384a6b286418faef817983b6274edb124109050f527d651c3f9c
```

## 격리와 보존 방식

1. 승인된 암호화 백업의 checksum·크기·mtime·inode를 확인한다. 원본 백업은 읽기만 한다.
2. 난수 이름/소유 라벨을 가진 컨테이너와 Docker `--internal` 네트워크를 생성한다. 호스트 포트를 공개하거나 운영 데이터 디렉터리를 마운트하지 않는다. CPU 1개·메모리 1 GiB로 제한한다.
3. MySQL은 임시 비밀번호·전용 43317 포트로 기동하고 event scheduler DISABLED, binlog/LOCAL INFILE OFF, secure_file_priv NULL을 확인한다.
4. 복호화 → gzip 해제 → 임시 MySQL로 파이프 적재한다. 평문 SQL을 호스트 파일로 남기지 않는다. 적재 중에만 `innodb_flush_log_at_trx_commit=2`, 완료 후 1로 복구하고 로그를 flush한다.
5. 호스트의 별도 Java 프로세스가 내부 IP로 접근한다. 무작위 DB 표식, server UUID, 포트·엔진 설정을 대조한 뒤 쓰기를 허용한다. 운영 API/배치 환경 파일이나 R2 설정은 전달하지 않는다.
6. 기존 테이블의 PK 순서로 모든 원래 컬럼을 스트리밍 해시한다. NULL 표시와 필드 길이를 포함해 단순 문자열 연결의 모호함을 피한다. DDL 후에는 신규 컬럼을 제외한 동일 투영을 비교한다.
7. 가상 계정/제보/알림/동의/역할/좌표 이력/감사 로그를 만들고 커밋·실패·반복 실행을 검증한다. 외부 키 충돌 시험도 실제 트랜잭션을 사용한다. 전체 시험을 바깥 트랜잭션으로 감싸 항상 롤백하는 방식이 아니다.
8. 가상 자료만 정리하고 원래 컬럼 전체를 다시 대조한다. 테스트로 증가한 AUTO_INCREMENT 값 등 스키마 메타데이터까지 원복했다는 의미는 아니다. DB 자체는 승격하지 않고 폐기한다.
9. 소유 라벨/ID를 확인해 컨테이너·익명 볼륨·네트워크를 제거한다. 집계 결과를 보존한 뒤 임시 실행 파일 사본도 제거한다.

실제 원본 화장실 좌표·주소·정규화 정보·회원·제보·감사 기록은 운영에서 수정하지 않았다. 운영 컨테이너 재시작, 타이머 변경, R2 쓰기, Discord 전송도 없었다.

## 검증 자료와 자동 테스트

- [이전 구조 복원 결과](account-erasure-live-backup-restore-2026-09-06.md)와 같은 백업 SHA-256 `8b83a248f93f590b2e3f2f34423def8521fb51b7067132cbefa5381baf7fe034`를 사용했다. 이번에도 원본 불변을 확인했다.
- 집계 결과 JSON은 비공개 로컬 작업 폴더에 보존했다. 소수 회원 집계가 포함되어 원본 JSON은 공개 docs에 올리지 않는다.
- 결과 JSON SHA-256: `3ea2c4079d043b307b5d5cdfa97df2fa6c8f310e71576ae536a49c8c95fed257`.
- Java 21 컴파일 성공, 배치 `installErasureTools` 성공, API/배치 공유 계약 8개 동일.
- docs Python 테스트 19개 중 11개 통과, 기존 Linux 전용 8개 건너뜀. 이번 DB 검증은 위 실제 미니 PC MySQL 실행으로 별도 확인했다.

## 아직 완료가 아닌 부분

결과는 `V11_SYNTHETIC_VERIFIED_NOT_ERASURE_CLEARED`이다.

- `syntheticReplayVerified=true`: 실제 스키마 복사본에서 **가상** 파기 기록 2건의 SQL 재적용을 검증했다.
- `productionLedgerReplayVerified=false`: 실제 R2 파기 대장 전체 목록을 내려받아 재생한 것이 아니다. 가상 결과를 실제 운영 회원 파기 완료 증빙으로 사용하지 않는다.
- `retentionEligible=false`: 기존 백업에 캡처 metadata/DB 복원 세대가 없고 실제 독립 대장 기준도 미확정이다. 백업/대장 자동 삭제 기준으로 등록하면 안 된다.

다음 단계는 V1.11 운영 DDL 및 API/배치 feature diff·기능 플래그·롤백 절차를 묶어 검토하고 **운영 반영 승인을 별도로 받는 것**이다. 승인 전에는 운영 DDL이나 3개월 파기 스케줄을 켜지 않는다. 이후 캡처 metadata가 있는 새 백업, 실제 대장·독립 체크포인트 기준, 복구/재가입과 Redis 세션 무효화 통합 검증을 차례로 확인한다.

과거 백업 삭제, 실제 파기 대장 정리, 미니 PC 전체 유실 복구, 전원 차단 내구성까지 이번 시험으로 완료된 것은 아니다.
