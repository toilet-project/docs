# 5단계 준비 배포 결과

2026-09-07 KST. **API·배치 준비 배포와 V11·Redis 비영속 전환 완료**, 사용자 로그인 후 홈페이지 복귀 확인. 사용자가 **V11·API·배치 준비 배포와 Redis 전환을 승인**했다. 자동 파기·R2 쓰기 활성화, 기존 Redis 파일 삭제, 웹 정책 공개는 승인 범위에서 제외했다. 자동 파기는 별도 6단계다.

## 변경한 준비 배포

| 대상 | 변경 | 운영 영향 / 경계 |
| --- | --- | --- |
| Redis | `save ''`, `appendonly no`, `/data` tmpfs. 기존 named volume 미연결 | 재시작 시 refresh 세션 유실·재로그인. 기존 RDB/AOF는 삭제하지 않으며 새 프로세스에서 읽지 않음 |
| API | commit SHA 이미지로 고정, 배포 전 소유자 전용 설정·이전 image ID 보존 | 새 기동에서 기존 Flyway 경로로 V11 적용. 탈퇴·계정 복구 점검, 일반 로그인 유지 |
| batch | commit SHA 이미지로 고정, 이전 설정·image ID 보존 | 정기 공공데이터 수집은 유지, 회원 자동 파기는 계속 OFF |
| 공통 | `set -eu`, 처음부터 `umask 077`, Compose 사전 검사·시작 대기 | image prune·remove-orphans 사용하지 않음. 컨테이너 실행 확인은 HTTP/DB/OAuth 확인의 대체가 아님 |

코드: [API PR #86](https://github.com/toilet-project/toilet-api/pull/86), [batch PR #38](https://github.com/toilet-project/toilet-batch/pull/38).
이번 추가 commit: API `2f65978`, batch `f710d99`.

### Redis 의미

설정만 끄면 기존 RDB를 다시 읽을 수 있으므로 **기존 볼륨을 새 Redis에 마운트하지 않는다.** tmpfs에는 복구 파일이 없고 새 세션은 메모리에서 시작한다. 기존 Redis 파일과 키·DB 백업은 이번 단계에서 삭제하지 않는다.

이는 과거 디스크 사본 파기 완료를 의미하지 않는다. 실제 전환 후 기존 볼륨 내 정확한 파일/크기/hash를 다시 확인하고 별도 승인으로 처리한다. swap·core dump·디스크 물리적 잔류까지 없다고 보증하지 않는다. 재시작은 refresh 세션을 잃게 하지만 이미 발급된 access JWT를 즉시 모두 무효화하는 작업은 아니다.

배포 시 생기는 `rollback-preparation.*`에는 비밀 설정이 포함된다. 소유자 전용으로 보관하고 공개 저장소·이슈·로그에 원문을 올리지 않는다. 이미지 ID와 함께 복구에 쓰되, 예전 Compose를 그대로 복구하면 Redis 영속화/오래된 세션 로딩도 다시 켜질 수 있으므로 Redis 정책은 유지한 채 앱 이미지 복구를 우선 검토한다.

## DB 변경과 되돌리기

V11은 다음을 적용한다.

- `app_user.auth_version`, `audit_log.actor_erased` 추가.
- `toilet_report.reporter_user_id`, `coordinate_revision.applied_by_user_id` NULL 허용.
- `account_withdrawal` 및 `idx_withdrawal_due(next_attempt_at, user_id)` 추가.
- 기존 탈퇴 계정을 동의 없이 3개월 보관으로 편입하지 않음.

기존 API의 Flyway만 사용한다. docs DDL을 먼저 수동 실행하거나 Flyway 이력을 조작하지 않는다. MySQL DDL 묶음은 일반 SQL 트랜잭션처럼 통째로 자동 롤백되지 않는다. 중간 실패 시 실제 적용된 컬럼/테이블/Flyway 이력부터 점검하며 blind retry·DROP으로 해결하지 않는다. 이전 앱 이미지로 되돌리는 것과 DB 스키마 복구는 별개다.

## 확인한 운영 상태

9월 7일 **01:36 KST**, 읽기 전용:

- API·Redis·batch·admin·MySQL 실행 중, Redis healthy.
- 암호화 백업 11개 중 metadata 포함 1개. 최신 `toilet-db-20260906-153502.sql.gz.enc`의 SHA256 sidecar 일치, 생성 약 1시간 경과.
- 03:15 백업·03:35 격리 복원·04:15 삭제 없는 점검 timer 활성화.
- **첫 정기 실행과 04:20 확인은 아직 미래 시각**. 성공으로 표시하지 않는다.
- 기존 백업 내용 복호화·DB 업데이트·컨테이너 재시작 없음.

## 검사

- API 로컬 Node: 8개 중 7 통과, 실제 Docker 1개는 로컬 Docker가 없어 skip.
- batch 로컬 Node: 7/7 통과.
- [API CI](https://github.com/toilet-project/toilet-api/actions/runs/34045959058)의 격리 Redis 단계 성공. 생산 Compose의 Redis 항목 그대로 사용하되 자원 이름과 합성 비밀번호만 분리했다. 호스트 포트·운영 네트워크·영속 볼륨 없음.
  - `$`·`#`가 포함된 합성 비밀번호 인증 성공.
  - save 빈 설정, appendonly no, `/data` 실제 tmpfs 확인.
  - 합성 세션 기록 후 재시작하면 존재하지 않음.
  - 재시작 전후 `/data`에 저장 파일 없음.
  - 테스트 Compose 자원 정리 성공.
- 실제 사용자 Google/Kakao 재로그인·앱 연결은 배포 후 확인할 항목이다. 위 합성 검사로 완료 처리하지 않는다.

## 적용 순서와 남은 경계

1. 완료: PR 최종 head/검사 통과, main 변경 없음, 배포 전 V10 확인. 02:00 정기 작업 전에 컨테이너 교체 완료.
2. 완료: 새 백업/metadata/hash와 격리 복원 검증본 확인.
3. 완료: 승인 변수로 준비 배포. API V11·Redis 전환 → HTTP/DB/Redis 상태 확인 → batch 배포·기능 OFF 확인.
4. 완료: 읽기 전용 연결과 사용자 정상 로그인 확인. 기존 Redis 파일 삭제 없이 별도 목록/승인으로 남김.
5. 웹 feature는 아직 PR 없음. 선택 보관 정책·시행일·외부 저장 고지와 UI 검사를 마친 뒤 별도 공개. 현재 웹을 이미 새 정책으로 배포했다고 표시하지 않음.
6. 실제 파기·R2/독립 체크포인트 쓰기 및 전체 사용자 흐름은 **별도 승인된 활성화 단계**에서 진행.

현재 준비 workflow는 maintenance=true, retention/erasure/ledger/catalogue/checkpoint=false를 강제한다. 정책·백업 검증이 미완료인데 플래그만 바꿔 운영 완료로 취급하지 않는다.

## 운영 적용 기록

- 01:39:37~01:39:43 KST 배포 직전 백업 추가: `toilet-db-20260906-163937.sql.gz.enc`. 기존 백업 삭제 없음, 총 12개 중 metadata 포함 2개.
- 01:40:01~01:40:41 KST 새 백업 격리 복원 성공, 보호 검증본 갱신. 원본 DB 수정 없음.
- API 최종 PR 검사 전부 성공 후 01:41:14 KST [PR #86](https://github.com/toilet-project/toilet-api/pull/86) main 병합. merge `fc66cd1`. [운영 CI/CD](https://github.com/toilet-project/toilet-api/actions/runs/34046244587) 성공. 01:43:11 KST 새 API 기동.
- Redis 첫 전환에서는 실제 `/data`가 tmpfs였지만 Docker inspect에 기존 named volume 정보가 승계됐다. CI의 새 컨테이너 검증만으로는 이 기존→신규 전환을 확인하지 못했다. 운영에서 이를 추가 발견하여 `docker compose stop redis` → `docker compose rm -f redis` → `docker compose up -d --wait --wait-timeout 120 redis api`로 Redis **컨테이너만** 다시 생성했다. `-v`·volume 삭제·FLUSHALL 없음. 이후 inspect Mounts 빈 배열, HostConfig Tmpfs 및 `/proc/mounts`의 실제 tmpfs를 확인했다.
- 01:45:07 KST [batch PR #38](https://github.com/toilet-project/toilet-batch/pull/38) main 병합. merge `f174f5d`. [운영 CI/CD](https://github.com/toilet-project/toilet-batch/actions/runs/34046447648) 성공. 01:46:44 KST 새 batch 기동.

### 최종 읽기 전용 검사 — 01:47 KST

- Flyway V11 success=1. 새 컬럼 2개, FK 참조 컬럼 2개의 NULL 허용, `account_withdrawal` 존재 및 0행 확인.
- API/batch 모두 merge SHA 이미지 사용, Running=true, RestartCount=0.
- 두 프로세스 모두 maintenance=true, retention/erasure/ledger/catalogue/checkpoint=false. 체크포인트 자격 증명 전달 여부만 확인했고 비밀값은 출력하지 않음.
- Redis healthy, AUTH/PING 성공, `appendonly=no`, `save` 빈 값, `/data` 파일 0개, 기존 volume 연결 없음.
- batch의 실제 전달된 비밀번호가 API와 동일함을 값 출력 없이 비교. batch 네트워크를 공유하는 임시 클라이언트에서 AUTH/SELECT 0/PING 성공, 클라이언트 자동 제거. Redis 키 생성/삭제 없음.
- 내부/외부 `/api/health` 200 및 DB 응답 확인. Google/Kakao OAuth 시작 경로 302·예상 제공자 도메인 확인. 초기 Python HTTP 도구에서 실패한 외부 요청은 curl로 다시 검사해 200 확인했으며 장애로 단정하지 않음.
- 사용자가 실제 소셜 로그인 후 홈페이지 복귀를 확인함. 제공자 종류는 답변에서 특정하지 않았으므로 Google와 Kakao **양쪽 모두의 실제 로그인 완료**로 확대 기록하지 않음.

### 그대로 남긴 자료와 작업

기존 volume `/var/snap/docker/common/var-lib-docker/volumes/toilet-api_redis-data/_data`의 파일 4개 보존: `dump.rdb` 6,934 bytes, `appendonly.aof.manifest` 88 bytes, `appendonly.aof.1.base.rdb` 89 bytes, `appendonly.aof.1.incr.aof` 48,062 bytes. 실행 중 컨테이너의 해당 볼륨 참조 없음. 첫 Redis 종료에서 마지막 저장으로 파일 크기가 이전 조사와 달라질 수 있어 삭제 전 다시 hash 검증해야 한다. 이번 작업에서 회원 데이터/기존 백업 파일은 삭제하지 않았다.

복구용 API 설정 디렉터리 `rollback-preparation.eZCPzb7y`는 0700. V11 이전 백업으로 DB를 되돌리면 그 이후 서비스 쓰기가 유실될 수 있으므로 전체 DB 복원은 자동 롤백이 아니다. 정기 파기 활성화·정책/웹 공개·과거 사본 정리·독립 체크포인트 실제 쓰기/장애 복구 시험은 미완료로 남긴다.

03:15/03:35/04:15 첫 정기 작업 및 04:20 확인은 이 보고 시점에 아직 실행 전이다. 이번 수동 백업/복원 성공으로 정기 실행 체크를 대체하지 않는다.
