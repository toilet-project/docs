# 독립 체크포인트·백업 만료 점검 v1

작성: 2026-09-06. **구현/격리 검증 단계이며 운영 미설치**. 실제 DB·백업·binlog·R2 객체 삭제, 계정 파기 기능 활성화는 하지 않았다.

## 완료 범위

- 승인받은 조직 비공개 저장소 `toilet-project/operations-checkpoints` 생성, private 확인.
- 집계 전용 JSON 형식·이전 해시 연결·기존 파일 수정/삭제 검사 및 GitHub CI 등록.
- batch `CatalogueCheckpoint`: 검증한 목록으로 집계 건수·목록 SHA-256·복원 세대·이전 체크포인트 해시 생성. 명시적 대상 집합 검토 없이는 생성하지 않는다.
- batch `BackupRetentionMaintenance` / `BackupRetentionCli`: 기본 dry-run, 승인한 계획 해시와 최신 복원 검증 백업을 요구하는 파일 정리 도구.
- `RetentionFailureNotice`: 점검 보류/만료 후보 발견·정상 복구 알림, 같은 상태 6시간 중복 억제, Discord 실패 시 전송 완료로 기록하지 않음.
- [실행 wrapper](scripts/mysql-backup-retention.sh), [점검 service](systemd/geupddong-backup-retention.service), [timer](systemd/geupddong-backup-retention.timer) 템플릿. 백업 성공 여부와 독립적으로 04:15 KST 점검하며 **예약 명령은 항상 dry-run**이다.

## 비공개 체크포인트의 의미

허용 필드는 version, realm, databaseEpoch, sequence, count, inventorySha256, previousCheckpointSha256, recordedAt뿐이다. 회원 ID/이메일/의도별 목록·R2 객체 원문·백업·키는 업로드하지 않는다. 아직 실제 운영 체크포인트가 없으며 빈 저장소가 운영 대상 0건을 증명하지 않는다.

생성 절차: 작성자와 복원 작업 중지 → 기존 독립 기준과 실제 대상 집합 대조 → private 목록 파일 생성 → `CatalogueCheckpoint.next`로 집계 생성 → 새 순번 파일 추가 → 검증/검토 → Git 커밋. 현재 생성 로직과 저장소 검증까지 구현했으며 서버 자동 업로드/자격 증명은 연결하지 않았다. 처음 기준을 확립하는 별도 운영 검증이 필요하다.

단순 건수 증가만으로 누락 없음이 증명되지 않는다. 부모 해시 불일치, 건수 감소, realm/DB 세대 변경, 시각 역행은 거부한다. DB 복원 세대 변경과 정상적인 대장 보관 만료로 건수가 줄어드는 경우도 현재는 중지하며 별도 전환 절차가 필요하다.

GitHub는 R2와 다른 저장소지만 WORM 저장소는 아니다. 보호 브랜치/필수 검토·권한 정책은 아직 확인/설정하지 않았다. 관리자 권한으로 검증 코드나 기록을 바꾸는 경우까지 방지한다고 주장하지 않는다. GitHub CI가 실패한 변경을 main에 기술적으로 차단하려면 별도 브랜치 보호 설정이 필요하다.

## 백업 만료 판정

| 조건 | 동작 |
| --- | --- |
| 캡처 완료 후 14일 경과 | 만료 후보. 자동 삭제 아님 |
| 36시간 이내 생성되고 별도 복원 시험을 통과한 백업 hash 제공 | 해당 백업은 보호. 운영자가 복원 시험 사실을 입증해야 함 |
| metadata 없는 기존 파일 | HOLD_LEGACY_METADATA. 파일명/mtime으로 임의 보충하지 않음 |
| 미분류/고아 파일·손상 checksum·metadata | 보류/실패. 빈 목록으로 무시하지 않음 |
| 서버 UUID/복원 세대 불일치 | HOLD_IDENTITY |
| 최근 복원 검증 백업 없음 | HOLD_NO_RECENT_VERIFIED_BACKUP |
| 스캔 5분 초과·시각 역행 | HOLD_STALE_SCAN |

실행 시 전체 파일의 이름·내용 해시·크기·mtime·metadata·판정·검증 기준으로 계획 SHA-256을 계산한다. 검토한 해시를 승인값으로 전달하고 새 스캔 결과가 동일해야 삭제한다. 하나라도 달라지면 새 계획을 검토한다. 삭제 전 새 journal을 배타 생성하고 fsync하며, 만료된 덤프·checksum·metadata 3개만 정확한 경로로 삭제한다. 최신 복원 검증 백업은 남긴다.

부분 실패는 journal에 `INCOMPLETE_REVIEW_REQUIRED`를 남기고 중단한다. 남은 고아 파일은 후속 점검에서 보류한다. 자동으로 강제 삭제하거나 이전 journal을 덮어쓰지 않는다. 삭제는 되돌릴 수 없으므로 실제 `--apply`에는 대상 목록에 대한 별도 운영 승인이 필요하다. 테스트의 삭제 대상은 임시 가상 파일뿐이다.

### 실행 전 설정 (값은 비공개 설정 파일에 보관)

| 환경 변수 | 용도 |
| --- | --- |
| GEUPDDONG_BACKUP_DIR | canonical 백업 디렉터리 |
| GEUPDDONG_RETENTION_STATE_DIR | 백업 폴더 밖 소유자 전용 0700 상태/journal 디렉터리 |
| GEUPDDONG_ERASURE_TOOL_DIR | `installErasureTools` 결과의 `lib` 상위 경로 |
| GEUPDDONG_MYSQL_SERVER_UUID / GEUPDDONG_DATABASE_EPOCH | 검증한 대상 서버·복원 세대 |
| GEUPDDONG_RESTORE_VERIFIED_BACKUP_SHA256 | 실제 복원 검증한 최근 암호화 백업 hash |
| GEUPDDONG_RETENTION_NOTIFICATIONS_ENABLED | 기본 미활성. true일 때만 Discord/알림 상태 기록 |
| BATCH_FAILURE_WEBHOOK_URL | 기존 Discord 웹훅. 문서/저장소/출력에 값 포함 금지 |
| GEUPDDONG_APPROVED_RETENTION_PLAN_SHA256 | `--apply`의 검토된 실행 계획 |
| GEUPDDONG_RESTORE_AND_WRITERS_STOPPED=true | `--apply` 전 복원 및 다른 작성자 중지 확인 |

`GEUPDDONG_RETENTION_LOCK_HELD`는 wrapper가 같은 `.backup.lock`의 flock을 획득한 뒤 전달한다. 이 잠금은 협력하는 백업 작업만 배제하므로 다른 수동 프로세스/복원 작업 중지는 별도 확인한다. Linux POSIX 권한을 확인하며 지원하지 않는 플랫폼에서 운영 CLI 실행을 허용하지 않는다.

종료 코드: 0 정상/후보 없음, 2 확인 필요(후보/보류), 1 오류. dry-run도 알림을 활성화하면 Discord 전송과 알림 상태 파일 기록은 할 수 있으나 백업 삭제는 하지 않는다.

## 알림과 남은 연결

알림에는 상태 코드와 집계만 들어가며 Discord mentions를 비활성화한다. HTTPS 공식 webhook만 허용하고 리다이렉트는 따르지 않는다. 실제 Discord 전송은 이번에 하지 않았으며 가상 transport로 실패/재시도/복구를 검증했다.

wrapper 사전 검사·잠금 실패, JVM 기동 실패, 누락된 설정/손상된 알림 상태는 프로그램 내부 알림 전에 실패할 수 있다. **독립 systemd 실패/미실행 감시 연결이 추가로 필요**하며 모든 장애가 Discord로 간다고 간주하지 않는다. 같은 상태의 후보 건수가 바뀌면 새로운 상태로 간주해 다시 알릴 수 있다.

## 실제 검증 결과

- batch 전체 **161건: 157 통과, 4 건너뜀, 실패/오류 0**. 신규 15건(만료 정리 8, 알림 4, 체크포인트 3) 통과. 빌드 및 `installErasureTools` 패키징 성공.
- private 저장소 Node 테스트 **6건 통과**, GitHub CI 성공. 검사 출력 `records=0 operationalBaseline=not-established` 확인. 초기 코드 커밋 `046ffd0`.
- API/배치 공유 계약 8개 파일 일치. 이번 단계 API 코드는 변경하지 않았다.
- Bash 문법 검사 2개, Git 공백 검사 통과. 실제 Linux systemd/권한/잠금·운영 DB/R2·Discord 실전송은 미검증.
- 파일 정리 시험은 임시 가상 백업만 사용: 14일 경계, 최근 복원 검증본 보존, 누락/변조/세대/계획 변경 보류, journal 덮어쓰기 거부, 중간 실패 기록과 재시도 차단 확인.
- 최초 빌드는 추가 코드가 참조한 시간 직렬화 모듈이 없어 실패했다. 외부 의존성을 추가하지 않고 명시적 UTC Instant 문자열 직렬화로 수정한 뒤 전체 테스트를 재실행해 통과했다.

## 운영 전 남은 필수 조건

1. 운영 목록 최초 기준 확립, private 저장소 권한/보호 검토, 집합 변경 검증과 체크포인트 생성·검토 절차 실행.
2. 실제 Linux에서 flock·권한·journal·systemd·실패 감시를 격리 검증하고, 실제 백업 복원 시험으로 보호 hash 확정.
3. metadata 없는 기존 백업 처리와 모든 백업 위치·binlog·스냅샷·Redis 사본 확인. 이 도구는 binlog/R2/외부 사본을 삭제하지 않는다.
4. 로컬 metadata는 서명된 출처 증명이 아니다. 조작 방지와 전체 작성자/복원 상호 배제를 별도 검토.
5. 새 백업 스크립트는 기존 성공 후 만료 삭제를 제거하므로 **이 점검 도구만으로 무인 보관 기간 강제가 완료되지는 않는다**. 보류 대응/정리 운영 절차 없이 단독 교체하지 않는다.
6. 서버 설치·정책/키 복구·복원 리허설 검토 후 기능 활성화는 별도 승인. R2 대장 정리는 계속 비활성이다.

이번 단계는 운영 투입 준비를 위한 안전한 도구와 검증 기준 구축이며 회원정보 파기 전체 기능의 완료 선언이 아니다.
