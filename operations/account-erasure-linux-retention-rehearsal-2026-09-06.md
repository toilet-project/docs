# 백업 만료 점검 Linux 격리 검증

검증일: 2026-09-06 KST. 선행 문서: [독립 체크포인트·백업 만료 점검 v1](account-erasure-checkpoints-retention-v1.md).

## 결론

미니 PC의 실제 Linux에서 **가상 파일 검증 17건 통과**, 임시 systemd 서비스 정상/실패 판정, 승인받은 Discord 테스트 메시지 **1건 HTTP 2xx 응답**을 확인했다. 운영 백업·회원 데이터·R2 객체는 수정/삭제하지 않았고 운영 타이머/컨테이너/계정 파기 기능도 변경하지 않았다.

이는 백업 파일 점검/정리 도구의 격리 검증이며 **실제 백업 복원 성공, 실제 회원 파기, 전체 장애 자동 알림, 운영 설치 완료**를 의미하지 않는다.

## 격리 방식

- 서버 Java 21.0.12, systemd 255, 실제 Linux POSIX 파일 권한과 `/usr/bin/flock` 사용.
- `/tmp/geupddong-retention-check.*`의 명시적으로 생성한 소유자 전용 0700 폴더만 사용했다. 검증 도구는 canonical 경로·격리 표식·도구 경로를 확인하고, 다른 위치에서는 실행을 거부한다.
- 파일에는 `SYNTHETIC_NOT_A_DATABASE_BACKUP` 표시만 넣었다. 실제 DB 덤프가 아니며 암호화/복원 시험으로 간주하지 않는다.
- 단독 Java 검증 코드가 batch 클래스만 호출한다. Spring 서버/스케줄러를 기동하지 않고 MySQL/Redis/R2에도 연결하지 않는다.
- 최초 배포 묶음 SHA-256: `92406324b9279c28374f494cf0c5d6519792f995401cc47141e02a2c2b5f85b1`. 잠금 보완 후에는 변경한 검증 코드와 wrapper를 새 격리 폴더로 보내 다시 실행했다.
- Discord는 별도 1회 검증에서만 기존 batch 설정의 webhook 항목을 읽었다. 키를 출력/다운로드/문서화하지 않았다.

## 실제 통과 항목

| 항목 | 확인 결과 |
| --- | --- |
| dry-run | 만료 후보가 있어도 모든 가상 백업 보존, 종료 코드 2 |
| 상태 파일 | 알림 비활성 시 기록 없음, 상태 폴더 0700 |
| 직접 CLI 진입 | 잠금 확인값 없이 실행 거부 |
| POSIX 권한 | 0750 상태 디렉터리 거부 |
| 실제 잠금 | 별도 프로세스가 flock 보유 시 두 번째 실행 차단 |
| 내용 있는 잠금 파일 | 내용 보존하고 중단, 빈 파일로 덮어쓰지 않음 |
| FIFO 잠금 파일 | 대기하지 않고 즉시 거부 |
| 잘못된 계획 해시 | 삭제하지 않고 실패 |
| 작성자/복원 중지 미확인 | apply 거부 |
| 승인한 가상 정리 | 오래된 가상 파일 3종만 제거, 최근 파일 보존, journal 0600 및 COMPLETE |
| metadata 없는 기존 형식 | HOLD_LEGACY_METADATA |
| 복원 세대 불일치 | HOLD_IDENTITY |
| checksum 손상 | scan 실패, 조용히 누락하지 않음 |
| 백업 폴더의 symlink | HOLD_UNKNOWN_FILES, 링크 대상 내용 보존 |
| 상태 폴더 symlink | 실행 거부 |
| 중간 삭제 실패 | INCOMPLETE_REVIEW_REQUIRED 기록, 후속 실행은 고아 파일 보류 |
| 잘못된 webhook | 고정 오류 코드, URL 미출력, 전송 완료 상태 미기록 |

### 검증 중 보완

기존 wrapper와 신규 백업 캡처 스크립트는 잠금 파일을 `>`로 열어 기존 내용을 지울 수 있었다. 일반 파일/빈 내용인지 먼저 검사하고 `>>`로 열도록 변경했다. 비정상 파일을 정상 잠금 파일처럼 바꾸거나 FIFO에서 대기하는 것을 막는다. 운영 설치본은 변경하지 않았다.

## systemd 실행 결과

`systemd-run --user --wait --collect`로 임시 oneshot을 실행했다. luha 사용자, UMask=0077, NoNewPrivileges=true, PrivateTmp=true, ProtectSystem=strict, ProtectHome=read-only 설정을 사용했다. `/tmp` 격리 파일 접근을 위해 시험 폴더만 BindPaths/ReadWritePaths로 허용했다.

- 정상 시 status=0, result=success. 보완한 최종 wrapper에서도 다시 통과.
- 도구 디렉터리를 의도적으로 존재하지 않는 격리 경로로 지정하면 status=1, systemd failed 감지.
- 임시 unit은 collect되어 실행 후 inactive. 영구 unit 설치/enable/타이머 시작은 하지 않았다.
- `04:15 Asia/Seoul` 예약 표현은 systemd가 다음 실행을 UTC 19:15(다음 날 KST 04:15)로 계산했다.
- 운영 `geupddong-mysql-backup.timer`는 전후 active 상태였다.

사용자 임시 unit 검증이므로 운영 system service의 EnvironmentFile 배치·부팅 후 실행·자동 실패 전달까지 모두 확인했다고 주장하지 않는다.

## Discord 확인 범위

사용자 승인 후 ‘[테스트 · 급똥] 백업 만료 점검 알림 경로 확인’ 메시지를 실제 transport로 **1회만** 전송했고 HTTP 2xx 응답을 받았다. 개인정보·백업 내용·비밀키·멘션은 넣지 않았다. 불확실한 전송 결과에 자동 재전송하지 않도록 시도 표식을 먼저 남기는 검증 도구를 사용했다.

API 접수 성공이며 사용자가 실제 채널에서 읽었다는 증거는 아니다. 실패 알림을 실제 삭제 실패로 가장해 발송하지 않았다. wrapper/JVM 사전 실패를 Discord로 전달할 **독립 실패 감시 연결은 여전히 필요**하다. 이번에는 그 실패를 systemd가 감지하는 것까지만 확인했다.

## 재현 도구와 변경 파일

로컬 batch 회귀 검증은 **162건 중 158 통과·4 건너뜀·실패/오류 0**, 도구 패키징 성공. 추가한 잠금 보존 회귀 시험도 통과했다. 건너뛴 항목은 별도 지역 표본과 실제 R2/DB 복원·MySQL 시간대 통합 시험이며 이번 Linux 파일 시험으로 대체되었다고 간주하지 않는다. Bash 문법 검사와 Git 공백 검사도 통과했다.

### 임시 자원 정리

검증 완료 후 이번에 만든 서버 `/tmp` 폴더 2개(약 232 MiB)의 canonical 경로·소유자·격리 표식·실행 중인 임시 unit 없음을 확인하고 삭제했다. 가상 백업/가상 journal/복사한 jar만 제거했으며 운영 백업은 제거하지 않았다. 원본 코드는 로컬 feature에 보존되므로 가상 파일은 재생성 가능하지만 삭제한 시험 파일 자체를 복구하는 기능은 제공하지 않는다. Discord 시도/접수 표식도 가상 폴더와 함께 정리했으므로 새 시험은 새 승인 없이 재실행하지 않는다.

batch `scripts/RetentionLinuxRehearsal.java`, `scripts/retention-rehearsal-marker.txt`: 전용 임시 폴더 안에서 Linux 17건 재현. `java -cp 'lib/*' RetentionLinuxRehearsal.java <격리 폴더> <격리 wrapper> <도구 폴더>`로 실행한다. 운영 백업 경로로 바꾸어 실행하지 않는다.

batch `scripts/RetentionDiscordSmoke.java`: 별도 승인 시에만 1회 테스트. 자동 테스트/정기 배치에 연결하지 않는다.

batch `BackupCaptureScriptTest`: 비정상 잠금 내용 보존 회귀 검증 추가.

docs `operations/scripts/mysql-backup.sh`, `operations/scripts/mysql-backup-retention.sh`: 비정상 잠금 파일 거부·내용 보존.

## 남은 운영 적용 조건

1. 독립 실패/미실행 감시 연결. systemd 실패 감지와 실제 Discord 전송 성공이 각각 확인됐다고 해서 두 기능이 자동으로 연결된 것은 아니다.
2. 기존 metadata 없는 백업의 처리 계획과 실제 최근 백업 복원 시험/보호 hash 확정. 이 시험의 가상 hash를 운영 설정에 사용하면 안 된다.
3. 운영 파기 목록 최초 기준 확립·private 체크포인트 등록/권한 보호, 작성자·복원 상호 배제 절차.
4. 모든 백업/binlog/Redis/스냅샷 확인, 정책/키 복구/복원 리허설 검토 후 설치와 기능 활성화 별도 승인.

운영 데이터나 비공개 기준값을 임의로 만들지 않았으며 R2 대장 정리와 계정 파기 기능은 계속 비활성이다.
