# 백업 만료 점검 systemd → Discord 실패 알림

검증일: 2026-09-06 KST. **구현과 임시 서비스 통합 검증 완료, 운영 영구 설치/활성화 전**.

선행 [Linux 격리 검증](account-erasure-linux-retention-rehearsal-2026-09-06.md)에서는 systemd 실패 감지와 Discord 전송을 각각 확인했다. 이번에는 실제 `OnFailure`를 통해 연결하고 중복 억제까지 검증했다.

## 동작

`geupddong-backup-retention.service` 실패 → `geupddong-retention-failure.service` → 독립 Python 3 표준 라이브러리 스크립트 → Discord.

- [점검 unit](systemd/geupddong-backup-retention.service)에 OnFailure를 추가했다.
- [알림 unit](systemd/geupddong-retention-failure.service)은 [독립 스크립트](scripts/systemd-retention-failure.py)를 실행한다. JVM·Spring·DB·Redis·R2·외부 Python 패키지를 사용하지 않는다.
- systemd가 전달한 실패 unit, 실행 ID, 결과, 종료 상태만 검증한다. 애플리케이션 로그/journal 본문을 메시지에 붙이지 않는다.
- 공식 systemd v255 문서의 [MONITOR 변수 계약](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml)을 기준으로 구현했다. 이 전달 방식은 v251부터 제공된다. 실제 서버는 v255다. 하나의 handler를 여러 실패 source에 공유하면 변수 전달이 보장되지 않으므로 이번 handler는 점검 unit 한 개 전용이다.
- 종료 코드 2는 만료 후보/보류 확인 요청, 나머지 실패는 점검 실행 실패로 표시한다. 데이터 삭제나 재시작은 하지 않는다.
- 점검 예약 unit에서는 JVM 내부 알림을 명시적으로 비활성화하여 같은 실패에 Java와 systemd가 중복 발송하지 않게 했다. 수동 Java CLI의 선택적 알림 기능 자체는 제거하지 않았다.

## 알림 안전장치

| 항목 | 처리 |
| --- | --- |
| 메시지 | 고정 문구·검증된 unit/상태 코드만 포함. 원문 로그·회원 정보·키 없음 |
| 전송 대상 | `https://discord.com/api/webhooks/...`만 허용. 쿼리/포트/리다이렉트/프록시 상속 거부 |
| 웹훅 | 기존 batch 설정의 `BATCH_FAILURE_WEBHOOK_URL` 한 항목만 읽음. shell source/실행 인자/로그에 URL을 넣지 않음 |
| 상태 저장 | 소유자 전용 0700 디렉터리, 0600 파일, flock·임시 파일·atomic replace·fsync |
| 중복 | 같은 실행 ID는 다시 보내지 않음. 다른 실행도 같은 unit/결과/종료코드이면 6시간 억제 |
| 변경된 실패 | 새 실행 ID와 다른 상태이면 cooldown 중에도 전송 가능 |
| 실패 | HTTP 성공 전에 전송 완료로 기록하지 않음. 실패 시 handler 자체가 exit 1 |
| 비정상 상태 | 손상된 JSON, 중복 키, 잘못된 권한/symlink/시각 역행은 실패 처리 |
| 자동 재시도 | 없음. 불확실한 timeout 뒤 중복 발송을 방지하기 위해 무조건 재전송하지 않음 |

전송 성공 후 로컬 상태 저장에 실패하면 Discord에는 전달됐지만 완료 기록이 없을 수 있다. 정확히 한 번 전달을 보장하는 시스템은 아니다. 이 경우 새로 실행하기 전에 채널과 handler 상태를 확인해야 한다. 다음 실제 실패가 다시 발생하면 미완료 상태에서 전송을 다시 시도한다.

## 실제 검증

- Windows: 정책/형식/노출 방지 **9건 통과**, Linux 전용 8건은 건너뜀.
- 미니 PC Python 3.12.3/Linux: **17건 모두 통과**, 건너뜀/실패 없음. 실제 POSIX 권한, flock 경합, 파일 동기화·원자 교체, 실패 미확인 처리까지 포함.
- `systemd-analyze --user verify`로 임시 handler 구문 검증.
- 별도 임시 source의 `ExecStartPre=/usr/bin/false`를 실행해 주 프로세스 시작 전 실패를 유도했다. Java나 원래 점검 CLI는 시작하지 않았다.
- systemd가 OnFailure handler를 자동 실행했고, handler `Result=success` 및 `SYSTEMD_FAILURE_NOTICE_SENT` 확인. 승인받은 ‘장애 알림 연결 테스트 · 실제 장애 아님’ 메시지 **1건 HTTP 성공 후 상태 기록**.
- 같은 임시 source를 다시 실패시켰을 때 `SYSTEMD_FAILURE_NOTICE_SUPPRESSED`, 상태 파일 해시 불변 확인. 추가 Discord 전송 없음.
- 실제 상태 디렉터리 0700, 상태 파일 0600 확인. 운영 백업 타이머는 전후 active.
- 원문 환경 파일/웹훅은 로컬로 다운로드하거나 테스트 결과에 남기지 않았다.

검증은 `/tmp/geupddong-onfailure-check.*`와 `/run/user/1000/systemd/user`의 임시 user unit 링크에서 수행했다. 운영 system service의 영구 설치·재부팅 실행까지 완료한 것은 아니다.

시험 후 비활성 상태·경로·소유자·링크 대상을 확인하고 이번에 만든 runtime 링크 1개와 약 60 KiB 임시 폴더를 제거했다. 운영 타이머는 그대로 active다. 삭제한 것은 재생성 가능한 시험 코드 사본/상태 파일뿐이며 영구 백업이 아니다. 테스트 코드는 로컬 feature에 보존했고 시험 메시지는 추가로 보내지 않는다.

## 운영 설치 시 구성

| 설정 | 운영 예정 값/의미 |
| --- | --- |
| GEUPDDONG_SYSTEMD_FAILURE_ENABLED | true. 직접 실행 시 기본 미활성 |
| GEUPDDONG_FAILURE_EXPECTED_UNIT | geupddong-backup-retention.service |
| GEUPDDONG_FAILURE_STATE_DIR | /var/lib/geupddong-retention-failure; StateDirectory로 관리 |
| GEUPDDONG_FAILURE_WEBHOOK_FILE | 기존 batch 설정 파일. 값은 비공개 |
| GEUPDDONG_FAILURE_TEST_MESSAGE | 운영에는 설정하지 않음 |

설치 순서: Python/설정 접근 확인 → handler 스크립트·unit 배치 → 점검 unit의 OnFailure 대상 로드 확인 → systemd 구문 검사/reload → 별도 승인한 점검 dry-run. 코드/설정 교체만 하고 handler unit이 없는 상태로 점검을 활성화하지 않는다. 실제 삭제는 예약하지 않는다.

재현: `python3 -B -m unittest discover -s operations/scripts/tests -p test_retention_onfailure.py -v`. 이 자동 테스트는 외부 메시지를 보내지 않는다. 실제 Discord E2E는 별도 승인을 받고 임시 source/handler로만 수행한다.

## 한계와 다음 단계

- 이 연결은 **백업 만료 점검 unit 전용**이다. 기존 매일 DB 백업 생성 unit이나 API·공공데이터 batch 장애 전체에 이번 handler를 연결한 것이 아니다.
- OnFailure는 실행 실패를 처리한다. 타이머가 꺼져 아예 실행되지 않는 경우, 장비 전원/네트워크 자체 장애는 외부 감시가 별도로 필요하다.
- Python/웹훅/디스크까지 장애이면 handler도 실패할 수 있다. handler 자체에 OnFailure를 붙여 재귀 알림을 만들지 않았다. handler 실패는 systemd에 남으며 운영자가 확인해야 한다.
- 이번 연결은 실패 알림만 제공하며 정상 복구 알림은 자동 연결하지 않았다.
- 실제 최근 백업 복원과 보호 hash 확정, 기존 metadata 없는 백업의 처리 계획, private 체크포인트 최초 운영 기준 확립은 남아 있다. 이 조건을 완료한 후 점검·알림의 영구 설치와 기능 활성화를 별도 진행한다.
- 운영 DB/백업/R2 수정, 계정 파기 활성화, 기존 타이머 교체는 하지 않았다.
