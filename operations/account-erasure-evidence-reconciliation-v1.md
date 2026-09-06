# 회원 삭제 완료 증빙 · 백업 목록 대조 v1

상태: feature 로컬 구현. 기존 운영 계정 파기 경로/기능 스위치를 바꾸지 않았다. 이번에는 **운영 DB 조회, 운영 R2 전송, 실제 백업 스캔·삭제, 서버 설치·배포를 수행하지 않았다.**

## 구현한 흐름

후속 [사전 목록·백업 메타데이터 구현](account-erasure-catalogue-backup-metadata-v1.md)에서 별도 선기록과 목록 파일 생성, 신규 백업 캡처 정보 읽기를 추가했다. 아래의 기존 백업 관련 제약은 metadata 없는 파일에 계속 적용된다. 독립 검증 기준의 외부 보존과 운영 설치는 아직 남아 있다.

기존 API 즉시 파기와 배치 정기 파기는 R2 의도를 먼저 기록하고 SQL을 삭제한다. 완료 증빙은 그 트랜잭션 안에 넣지 않았다. 별도 `AccountErasureEvidenceCli`가 다음 순서로 확인한다.

1. 운영자가 준비한 **독립 의도 목록** 파일과 별도 신뢰 경로의 SHA-256을 확인한다. JSON 중복 키·형식·realm·DB 복원 세대를 검증한다.
2. 명시된 백업 디렉터리를 비재귀·읽기 전용으로 스캔한다. 암호화 파일 해시와 `.sha256`을 비교한다. 복호화하지 않는다.
3. 지정한 loopback MySQL의 서버 UUID를 확인한다. 읽기 전용 복제본은 거부한다. DB 질의는 서버 식별과 `app_user` 조회뿐이며 DELETE/UPDATE/DDL을 호출하지 않는다.
4. R2 의도 목록의 **전체 건수와 각 의도 내용 해시**를 독립 목록과 비교한다. 동일 건수여도 다른 대상이면 거부한다. 중복 사용자 ID·대상 키도 거부한다.
5. 모든 대상의 ID/생성 시각을 먼저 확인한다. 남아 있는 계정은 pending, 다른 생성 시각의 같은 ID는 충돌로 중단한다. 파기 기한 전 의도에는 완료 증빙을 만들지 않는다.
6. 계정 부재를 새 조회로 다시 확인한다. 기본 dry-run에서는 기존 완료 증빙만 읽고 새로 쓸 건수를 계산한다.
7. 명시적 `--record-completions`일 때만 암호화 R2 완료 증빙을 조건부 최초 쓰기하고 읽어 검증한다. 원래 의도도 다시 읽어 해시를 비교한다. DB 쓰기·백업 삭제·R2 삭제는 어느 모드에도 없다.

트랜잭션이 활성화된 상태에서 증빙 수집을 호출하면 거부한다. 독립 CLI는 삭제 작업의 SQL 커밋 이후 DB 부재를 확인하므로, API/배치 양쪽에서 발생한 파기를 같은 방식으로 확인한다. R2 장애로 완료 기록이 실패해도 원래 의도는 남아 있어 다음 실행에서 재조회할 수 있다. 기존 `account_withdrawal` 행이 이미 삭제됐다고 재시도 대상을 잃지 않는다.

## 완료 증빙 형식과 보존

```text
completion-v1/<realm>/<databaseEpoch>/<withdrawalKey>.bin
```

- 필드: version, realm, withdrawalKey, intentDigest, databaseEpoch, firstConfirmedAbsentAt.
- `firstConfirmedAbsentAt`은 UTC Instant 문자열이다. 원래 계정 식별은 모든 의도 필드에 대한 도메인 분리 SHA-256으로 연결한다. 이메일/소셜 원문/이름/제보 원문은 추가하지 않는다.
- AES-256-GCM의 기존 envelope를 재사용한다. 키 ID는 암호문 헤더에 포함되고 realm/객체 경로와 함께 인증된다. 기존 `v1/` 의도 포맷과 AAD는 유지했다.
- `If-None-Match: *`로 최초 기록만 만들고, 재시도는 기존 최초 시각을 유지한다. 응답 유실 뒤에도 읽어서 재확인한다. 미래 증빙·다른 의도 해시·변조·잘못된 키/realm/복원 세대는 거부한다.
- DB 파기가 늦게 성공한 경우 의도 생성일로 소급하지 않는다. 완료 증빙 저장이 늦어졌다면 최초 신뢰 가능한 부재 확인일도 늦어져 보존 검토가 보수적으로 미뤄질 수 있다.
- 완료 증빙을 만들었다고 백업 삭제 조건을 통과하는 것은 아니다. 기존 [32일 정리 검토 정책](account-erasure-retention-policy-v1.md)의 나머지 조건은 계속 필요하다.

DB 복원 세대는 서버 UUID와 다르다. 같은 MySQL 인스턴스에 백업을 덮어 복원해도 UUID는 유지될 수 있으므로, 운영 복원 때 새로운 세대 UUID를 발급하고 독립 목록/설정을 함께 갱신해야 한다. 이 회전은 아직 자동화하지 않았다. 이전 세대 증빙으로 새 세대의 보존 시간을 계산하지 않는다.

## 백업 목록 비교에서 확인하는 것과 못 하는 것

확인: 정확한 디렉터리, 암호화 파일 이름·크기·mtime·SHA-256, checksum sidecar 일치, 스캔 전후 파일 변경 여부. 링크 경로를 따라가지 않으며 알 수 없는 파일·하위 디렉터리·임시 파일·고아 sidecar는 미분류 항목으로 센다. 파일 내용이나 경로를 공유 로그에 출력하지 않는다.

계정별 완료 확인 시각과 파일 수정 시각을 비교하는 함수는 있지만, mtime을 실제 백업 캡처 시작 시각으로 취급하지 않는다. 현재 백업은 캡처 메타데이터가 없으므로 `captureMetadataUnknown`으로 남긴다. 디렉터리가 비어 있어도 binlog·스냅샷·다른 사본이 없다는 증거는 아니므로 **allCopiesCleared/retentionClearance는 항상 false**다.

따라서 이 단계의 ‘대조’는 파일 무결성과 확인되지 않은 사본을 드러내는 진단이다. 자동 삭제 가능 판정을 만드는 완성된 전체 사본 목록 시스템은 아니다. 캡처 시각/세대가 있는 신뢰 가능한 백업 메타데이터, 실제 로그·모든 저장 위치의 제거 확인은 후속 구현이다. 파일 해시 계산은 읽기 I/O를 사용하며 운영 첫 실행은 백업·복원 중지가 가능한 점검 창에서 한다.

## 실행 도구와 안전 조건

```bash
./gradlew installErasureTools
java -cp 'build/erasure-tools/lib/*' \
  com.example.toiletbatch.account.AccountErasureEvidenceCli --dry-run
# 별도 승인 및 같은 점검 조건 아래에서만 사용. 쓰기 대상은 R2 완료 증빙뿐이다.
java -cp 'build/erasure-tools/lib/*' \
  com.example.toiletbatch.account.AccountErasureEvidenceCli --record-completions
```

환경 변수(실제 값은 보호된 환경 파일/Secret으로 주입하며 명령 기록·문서에 붙이지 않는다):

| 이름 | 용도 |
| --- | --- |
| 기존 ERASURE_LEDGER_* | 기존 R2 realm/endpoint/bucket/S3/AES 키링 설정 |
| ERASURE_EVIDENCE_WRITERS_STOPPED=true | 즉시 파기·배치·복원·백업 등 관련 작성자가 중지되고 점검 중 유지됨을 운영자가 확인 |
| ERASURE_EVIDENCE_INDEPENDENT_INVENTORY_CONFIRMED=true | R2 LIST를 그대로 복제한 목록이 아닌 독립 원본의 완전성을 확인 |
| ERASURE_EVIDENCE_INVENTORY_FILE / INVENTORY_SHA256 | 독립 JSON 목록 파일 / 별도 신뢰 경로에서 확보한 해시 |
| ERASURE_EVIDENCE_DATABASE_EPOCH | 독립 목록과 일치하는 복원 세대 UUID |
| ERASURE_EVIDENCE_BACKUP_DIRECTORY | 승인한 암호화 백업 디렉터리의 정규 절대 경로 |
| ERASURE_EVIDENCE_DB_URL | jdbc:mysql://127.0.0.1:포트/toilet_db, 추가 URL 옵션 금지 |
| ERASURE_EVIDENCE_DB_USER / DB_PASSWORD | 읽기 점검용 DB 계정. DDL·DELETE 권한 불필요 |
| ERASURE_EVIDENCE_SERVER_UUID | 사전에 확인한 실제 MySQL 서버 UUID |

목록 JSON 형식:

```json
{
  "version": 1,
  "realm": "verification",
  "databaseEpoch": "01234567-1234-1234-1234-123456789012",
  "intentDigests": {
    "v1/verification/01234567-1234-1234-1234-123456789013.bin": "<의도 전체 필드의 SHA-256 64자리>"
  }
}
```

이 예시는 형식 설명이며 실행 가능한 운영 목록이 아니다. JSON은 최대 32 MiB/10만 의도, 백업 스캔은 디렉터리 항목 2만 개/파일 20 GiB 상한을 둔다. 스캔은 재귀적으로 다른 저장 위치를 탐색하지 않는다.

중요: SHA-256은 파일 변조 확인이지 목록 출처의 증명은 아니다. 현재 **독립 목록 자동 생성·변경 세대 보존은 미구현**이다. 신뢰 원본이 없으면 `INDEPENDENT_INVENTORY_CONFIRMED=true`를 임의로 넣거나 R2의 현재 건수로 맞추지 말고 중단한다. `WRITERS_STOPPED`도 자동 분산 잠금이 아니라 운영 전제다. 이 도구를 그대로 무인 스케줄러로 등록하면 안 된다.

출력은 pending/absent/confirmed/wouldRecord/확인되지 않은 백업 관련 건수 등 집계뿐이다. 실패는 고정된 단계 코드로 종료한다. R2 응답·키·SQL/계정 원문은 출력하지 않는다. 부분 전송 후 실패한 경우 다음 실행은 기존 완료 시각을 읽어 재개한다.

## 배포 전 남은 조건

### 실제 실행한 검증

- 신규 테스트 **25건 통과**: 완료 증빙 7, 부재/롤백/재시도 수집 9, 암호화 백업 파일 스캔 5, 독립 목록 대조 4.
- 배치 전체 **134건 중 130 통과·4 건너뜀·실패/오류 0**. 건너뜀은 별도 지역 원본 표본, 실제 R2 왕복, 실제 R2+Docker 복원, 별도 MySQL 시간대 시험이다.
- API 관련 회귀 **28건 중 27 통과·실제 R2 시험 1 건너뜀·실패/오류 0**. 기존 의도 암호화/복호화·계정 수명주기·복구/탈퇴 접근 검증을 실행했다.
- H2의 실제 롤백 후 pending 유지, 활성 삭제 트랜잭션 안에서 증빙 수집 거부, ID 충돌/목록 변조 시 R2 쓰기 금지, 계정 재등장 시 보류를 확인했다.
- S3 mock으로 암호화 최초 쓰기/읽기, 응답 유실 재시도, 최초 확인 시각 유지, 변조·다른 epoch/realm/키·원래 의도 누락을 검증했다. 실제 운영 R2 전송 시험으로 간주하지 않는다.
- 가상 암호문 파일의 checksum 검증, 미분류 파일/고아 sidecar, 변경·미래 mtime·잘못된 checksum 경로 및 빈 디렉터리 미확정 판정을 확인했다.
- 독립 CLI classpath 패키징 성공. 실제 CLI 프로세스를 시작했을 때 `WRITERS_STOPPED=false`이면 DB/R2 접근 전 고정 오류로 거부하는 것 확인.
- API/배치 공유 계약 8개 소스 동일 확인. 테스트 JVM 임시 경로만 작업 폴더로 지정했으며 운영 설정은 변경하지 않았다.

### 후속 작업

- 독립 의도 목록의 신뢰 원본·변경 기록·누락 감지 및 DB 복원 세대 관리 자동화
- 백업 생성 메타데이터와 binlog/Redis/스냅샷 포함 전체 사본 점검
- 작성자/복원과의 자동 상호 배제, 제한된 권한의 점검 실행·경보 연결
- 실제 MySQL + 실제 R2 + 실제 백업 목록의 승인된 통합 점검
- 정책 고지·키 복구·전체 스키마 복원 검증 뒤 main 병합/배포/활성화 별도 승인

이번 단계에는 새 DDL, 사용자 화면, API 인증/탈퇴 트랜잭션 변경, 운영 기능 스위치 변경이 없다.
