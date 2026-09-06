# 파기 사전 기록 목록 · 백업 캡처 메타데이터 v1

상태: feature 구현, 운영 미적용. 목록 선기록 기능 기본값은 false다. 미니 PC의 현재 백업 스크립트·타이머·보관 설정과 운영 R2 객체는 변경하지 않았다.

## 파기 전에 별도 목록을 자동 기록

`ERASURE_LEDGER_CATALOGUE_ENABLED=true`일 때 API/배치의 기존 `ensureRecorded` 내부 순서가 다음과 같이 바뀐다.

1. `catalogue-v1/<realm>/<withdrawalKey>.bin`에 전체 파기 의도를 암호화해 최초 기록한다.
2. 읽기·복호화·전체 필드 일치를 검증한다.
3. 기존 `v1/<realm>/<withdrawalKey>.bin`의 파기 의도를 기록/검증한다.
4. 그 뒤에만 기존 Redis 정리와 SQL 파기가 이어진다.

별도 목록은 파기 후 현재 `v1/` LIST를 복사해서 만드는 파일이 아니다. 파기 승인 전에 발급되는 별도 선기록이다. 기록 충돌·R2 실패·읽기 불일치면 기존 파기 서비스까지 오류가 전달되어 DB 파기가 진행되지 않는다.

두 객체를 하나의 원자적 트랜잭션으로 취급하지 않는다. 목록만 남고 의도 기록이 실패했다면 재시도에서 같은 목록을 읽고 의도를 보완한다. DB 삭제 실패나 동시 재시도도 같은 식별자/내용일 때 최초 기록을 덮어쓰지 않는다. 기존 계정이 이미 없는 경우 이 도구가 DB를 생성하거나 다시 파기하지 않는다.

### 보호 범위와 제한

- 기존 의도 객체 누락, 다른 내용으로의 교체, 일부 목록 누락은 별도 목록/기준 건수 대조로 드러난다.
- **두 경로는 같은 R2 버킷/자격 증명을 쓴다.** 별도 장애 영역에 있는 두 번째 백업이나 삭제 불가능한 감사 원장은 아니다. 버킷 전체 유실·두 경로 동시 삭제·권한 보유자의 기준 조작까지 해결했다고 판단하지 않는다.
- 처음 활성화할 때 실제 목록 범위와 기준 건수를 별도 검증해야 한다. 기존 의도만 있는 상태를 자동으로 ‘목록 완비’로 표시하지 않는다. 운영 계정 파기를 활성화하기 전에 이 초기화 절차가 필요하다.
- 기준 건수/해시의 자동 버전 관리, R2 보존 잠금 및 버킷 밖 검증 기준 보존은 아직 남아 있다. 현재 버킷을 조회한 건수를 그대로 기대값으로 삼아 누락을 정상화하면 안 된다.

## 목록 파일 자동 생성 도구

`ErasureCatalogueExportCli`는 `catalogue-v1/`를 읽고 아래 조건을 검증한 뒤 기존 증빙 도구가 읽는 `ErasureIntentInventory` 형식으로 변환한다.

- 사전에 확인한 기대 건수와 실제 전체 목록 일치
- 모든 객체 복호화·경로/realm/전체 필드 검증
- 중복 대상 키/사용자 ID 거부
- 의도 필드 digest를 정렬해 같은 입력에서 동일한 JSON/파일 SHA-256 생성

```bash
./gradlew installErasureTools
java -cp 'build/erasure-tools/lib/*' \
  com.example.toiletbatch.account.ErasureCatalogueExportCli --dry-run
# 승인된 비공개 디렉터리에 신규 파일을 만들 때만 실행한다.
java -cp 'build/erasure-tools/lib/*' \
  com.example.toiletbatch.account.ErasureCatalogueExportCli --export
```

기존 R2 설정과 함께 필요한 값:

| 환경 변수 | 의미 |
| --- | --- |
| ERASURE_EVIDENCE_WRITERS_STOPPED=true | 점검 중 의도 작성·복원 등 관련 작업 중지 확인. 자동 잠금 아님 |
| ERASURE_CATALOGUE_CHECKPOINT_CONFIRMED=true | 기준 건수의 독립 검증 완료. 임의 지정 금지 |
| ERASURE_CATALOGUE_EXPECTED_OBJECTS | 별도 확인·보존한 기대 목록 건수, 최대 10만 |
| ERASURE_EVIDENCE_DATABASE_EPOCH | 대상 DB의 현재 복원 세대 UUID |
| ERASURE_CATALOGUE_EXPORT_FILE | Linux 소유자 전용 디렉터리의 새 JSON 경로 (`--export` 전용) |

출력은 건수/파일 해시뿐이다. dry-run은 파일을 쓰지 않는다. export는 파일·checksum을 0600으로 생성하고 flush하며 기존 파일/링크를 덮어쓰지 않는다. Linux POSIX 소유자 전용 디렉터리가 아니면 거부한다. 두 파일 생성 사이에 실패하면 부분 파일을 조용히 제거하거나 덮어쓰지 않고 운영자가 확인 후 새 경로로 재실행한다. 명세 파일은 사용자 ID 대신 의도 경로/내용 digest를 담지만 개인정보와 연결될 수 있으므로 공개 저장소에 올리지 않는다.

생성 파일과 출력 해시를 [완료 증빙 도구](account-erasure-evidence-reconciliation-v1.md)의 목록 입력으로 사용할 수 있다. 다만 파일 hash가 생성되었다는 사실 자체는 독립 검증 기준의 영속 보관을 대신하지 않는다.

## 백업 생성 메타데이터

docs `operations/scripts/mysql-backup.sh`의 새 구현은 암호화 덤프와 checksum 옆에 `.metadata.json`을 생성한다.

| 필드 | 내용 |
| --- | --- |
| version | 1 |
| filename / sha256 / bytes | 실제 암호화 덤프 이름·해시·바이트 수 |
| captureStartedAt / captureCompletedAt | 새 mysqldump 프로세스 실행 전 / 암호화 파이프 종료 후 UTC 시각 |
| database | toilet_db |
| serverUuid | 백업 전후 확인한 같은 MySQL 서버 UUID |
| databaseEpoch | 운영자가 관리하는 현재 복원 세대 UUID |

`GEUPDDONG_DATABASE_EPOCH` 설정이 없거나 형식이 틀리면 실행을 거부한다. 이 값은 같은 서버에 과거 백업을 복원해도 반드시 새로 발급해야 한다. MySQL UUID만으로 같은 인스턴스의 복원을 감지하지 못하므로 세대 자동 관리가 완성됐다고 간주하지 않는다.

- 잠금은 백업 스크립트 간 중복 실행만 막는다. 전체 파기/복원 분산 잠금을 대체하지 않는다.
- 시작 시각은 실제 DB consistent snapshot 생성 시각과 동일하다고 주장하지 않는다. 새 mysqldump 프로세스보다 먼저 기록하므로 해당 작업의 보수적인 시작 경계로 사용한다. 파일 mtime이나 완료 시각만 보고 삭제 전 데이터가 없다고 판단하지 않는다.
- 임시 전용 폴더에서 세 파일을 준비한 뒤 hard link로 기존 경로를 덮어쓰지 않고 공개한다. 세 파일 전체가 동시에 공개되는 트랜잭션은 아니다. 부분 결과는 점검에서 불완전으로 남는다.
- 원래 키로 gzip + AES-256-CBC/PBKDF2 암호화하며 키/DB 행을 로그나 metadata에 넣지 않는다. 운영 환경의 암호화 방식 자체는 바꾸지 않았다.
- metadata JSON은 파일 해시와 연결된 **로컬 진단 정보**이며 서명된 출처 증명이 아니다. 고권한 사용자가 덤프와 metadata를 함께 바꾸는 경우까지 탐지하는 기록은 아니다.

### 대조 도구 반영

백업 스캐너가 metadata의 이름·크기·hash·시각 순서·DB UUID/세대 형식을 검사한다. 실제 계정 삭제 확인 시각보다 캡처 시작이 빠른 백업을 따로 계산한다. 다른 세대의 백업을 현재 세대처럼 신뢰하거나, UUID 형식 검증을 현재 DB와의 동일성 검증으로 간주하지 않는다.

metadata가 없는 기존 백업에는 파일 날짜로 값을 채우지 않는다. `captureMetadataUnknown`으로 남긴다. `.metadata.json`이 덤프와 맞지 않으면 실패하고, 고아 metadata는 미분류로 남긴다. binlog·스냅샷 등 전체 사본 확인이 안 됐으므로 `allCopiesCleared=false`는 계속 유지한다.

### 설치 주의: 기존 자동 삭제 분리

새 스크립트에서는 백업 성공 후 실행되던 `find -mtime +14 -delete`를 제거했다. metadata를 함께 관리하는 별도 만료 정리 도구 없이 덤프만 지우거나, 백업 실패 때 점검이 생략되는 구조를 유지하지 않기 위해서다.

**아직 운영 설치 금지**: 독립 만료 정리/경보를 함께 마련하지 않고 새 스크립트만 교체하면 백업이 계속 쌓인다. 운영에 설치된 기존 스크립트는 수정하지 않았다. 서버 설치·보관 기간 변경·실제 삭제는 다음 검증과 별도 승인 뒤 진행한다.

## 검증 결과 (2026-09-06)

- 신규 **12건 통과**: 목록 선기록/누락·충돌/재시도/내보내기 6, 캡처 metadata 5, 가상 백업 스크립트 파이프라인 1.
- 배치 전체 **146건 중 142 통과·4 건너뜀·실패/오류 0**. 별도 지역 원본, 실제 R2 왕복/복원, 별도 MySQL 시간대 시험은 이번에 재실행하지 않았다.
- API 관련 회귀 **28건 중 27 통과·실제 R2 1 건너뜀·실패/오류 0**. 공유 계약 8개 소스 일치 확인.
- 가상 스크립트 검증은 Docker/flock/date/install을 대체하고 실제 gzip/OpenSSL/SHA-256/hard link를 사용했다. 정상 metadata 대조, 동일 파일명 덮어쓰기 거부, 덤프 실패 시 결과 미생성, 잠금 거부 시 중단을 확인했다. 실제 Linux 권한/잠금이나 운영 DB 검증으로 간주하지 않는다.
- 최초 가상 실행은 Git Bash PATH 누락, 이어서 Windows의 Linux 디렉터리 권한 설정 거부로 실패했다. 테스트 환경만 보완했고 운영 스크립트의 권한 검사는 약화하지 않았다.
- Bash 문법 검사, 독립 도구 classpath 패키징, 문서 링크/공백 검사 완료. 서버 설치·설정 변경·운영 R2 기록·백업 삭제는 하지 않았다.

## 다음 운영 단계

1. 기준 건수/해시와 DB 복원 세대의 버킷 밖 보존·버전 관리
2. metadata 출처 검증, 모든 백업·binlog·Redis·스냅샷 범위 확인
3. 독립 만료 정리 도구/실패 경보 및 전체 작성자·복원 상호 배제
4. Linux 실제 잠금·파일 권한·실제 MySQL/R2를 사용하는 격리 통합 검증
5. 정책 고지·키 복구·복원 리허설 후 운영 설치·기능 활성화 별도 승인
