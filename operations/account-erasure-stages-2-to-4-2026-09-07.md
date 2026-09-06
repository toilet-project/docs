# 운영 전 단계 2~4 결과와 배포 경계

2026-09-07 KST. 이 문서는 이전 준비 보고서들의 최신 상태를 정리한다. **API/배치 main 병합, V11 운영 적용, 회원 파기 활성화, 기존 백업·로그 삭제는 하지 않았다.**

| 단계 | 결과 | 남은 확인 |
| --- | --- | --- |
| 1. 첫 정기 실행 | 03:15 백업·04:15 점검의 04:20 읽기 전용 확인 예약 유지 | 아직 첫 실행 시각 전. 성공으로 체크하지 않음 |
| 2. 자동 격리 복원 연결 | 운영 설치, 실제 복원 성공, 03:35 timer 활성화 | 첫 정기 03:35 실행 확인. 구조 복원은 파기 대장 재적용 시험과 별개 |
| 3. 독립 체크포인트 | API·배치 feature 구현, 실패 시 파기 차단, 전용 GitHub 인증 읽기 검증 성공 | 5~6단계 배포 후 실제 경로/권한·재시도 검증. 지금 운영 쓰기 미활성 |
| 4. 사본·정책 점검 | 덤프·binlog·Redis·서버 스냅샷 점검, Redis 비영속 정책 선택 | 정책 고지 시행 및 선택한 Redis 변경·기존 파일 처리는 배포 단계에서 실행 |

## 2. 매일 자동 격리 복원

일정: **03:15 암호화 백업 → 03:35 격리 복원/검증본 갱신 → 04:15 삭제 없는 점검**. 각 스크립트는 같은 백업 flock을 사용한다. 백업이 지연되면 복원이 무리하게 병행되지 않고 실패 알림 경로로 진행한다.

설치 파일:

- `~/.local/bin/verify-and-refresh-backup.py`
- `~/.local/bin/verify-live-backup-isolated.py`
- `~/.local/bin/refresh-restore-verification.py`
- 기존 `systemd-retention-failure.py`에 복원 실패 문구 추가
- `geupddong-backup-restore.service`, `.timer`, `geupddong-restore-failure.service`

기존 일반 Docker service는 이중 기동 방지를 위해 masked였으므로 첫 유닛 검증에서 중단됐다. 실제 활성 엔진인 `snap.docker.dockerd.service` 의존성으로 수정했다. Docker 설정이나 기존 컨테이너를 재시작하지 않았다.

### 실제 실행

- 2026-09-07 **01:19:03~01:19:41 KST**, 약 38초.
- systemd 종료 0, `BACKUP_RESTORE_VERIFIED_AND_PROTECTED`.
- 백업 캡처 metadata로 가장 최신 파일을 선택. legacy 파일명/mtime을 신뢰 기준으로 사용하지 않음.
- 기존 검증본과 같은 백업이므로 보호 hash는 `ALREADY_CURRENT`. 새 검증 시각의 최소 증빙을 별도로 기록.
- 임시 MySQL: 운영과 같은 이미지, 1 CPU/1 GiB 제한, 네트워크 없음, host port 없음, 별도 익명 볼륨. 운영 SQL 쓰기 없음.
- 임시 컨테이너/볼륨 정리 성공 후 그 실행에서 생성한 `ATTEMPTED`, `result.json`, 비공개 오류 로그 3개만 제거. 백업 파일 삭제 없음.
- 설치 staging 약 64.6 KB 제거. 설치본·기존 알림 스크립트 복구용 사본은 보존.
- 다음 timer: **9월 7일 03:35 KST**, active/enabled.

검증 결과 hash `508853e05e088c04d145590f532c82f07f94f9b98f745e7f60e953d3a878b903`. 집계 receipt는 `~/.local/state/geupddong-backup-restore/receipts/`, 설치/복구 이력은 `~/.local/state/geupddong-backup-restore-install/20260907/`에 소유자 전용으로 저장한다.

실패하면 private `failed-run.json`을 남기고 다음 새 복원 시도를 보류한다. 운영자가 해당 run의 Docker label·volume·로그를 확인하고 해결한 뒤 재개해야 한다. 시간 초과 시 SIGTERM 정리를 시도하나 강제 종료/서버 정전 때는 임시 자원 잔류 가능성을 점검한다. 성공 여부와 무관하게 백업 자체는 지우지 않는다. 새 실제 실패를 일부러 만들어 Discord를 보내는 추가 시험은 하지 않았다.

## 3. 독립 체크포인트가 확인된 뒤에만 파기

API 직접 파기와 배치 파기 양쪽의 Spring bean에 같은 공유 구현을 연결했다.

1. 같은 MySQL 인스턴스의 advisory lock 확보. API/배치가 transaction-bound connection으로 동일 이름을 사용한다.
2. 비공개 `operations-checkpoints`의 기존 기준을 읽는다. 빈/누락/잘린 응답으로 0건 기준을 재생성하지 않는다.
3. R2 의도·catalogue 두 목록을 복호화 검증하고, 구성원의 digest를 독립 기준과 비교한다. 단순 건수 비교가 아니다.
4. 현재 처리하는 **정확히 한 의도**의 부분 기록만 복구를 허용한다. 다른 회원의 누락·동일 건수 바꿔치기·예상 밖 의도는 중단한다.
5. R2 선기록·읽기 검증 후 집계 체크포인트를 GitHub에 추가하고 다시 읽어 확인한다.
6. 위 단계가 모두 성공해야 기존 호출자가 Redis 정리와 SQL 파기를 수행한다. GitHub 장애/401·403/요청 제한/경합은 예외로 반환되어 회원 파기를 진행하지 않는다.

Git 추가는 기존 commit을 부모로 하는 단일 새 commit과 `force=false` ref 갱신이다. 부모가 달라지면 강제 덮어쓰기하지 않는다. GitHub 응답을 잃은 재시도는 기존 확인된 의도를 대조해 중복 체크포인트를 만들지 않는다. R2에만 기록된 의도는 원래 작업이 재시도될 때 복구하며, 다른 작업이 임의로 승인하지 않는다.

GitHub에는 count/hash/세대/연결 hash/시각만 전송한다. 회원 ID·이메일·R2 회원별 목록·복호화 원문은 전송하지 않는다. 완료 증빙 객체의 개별 상태가 아니라 **파기 의도 집합**을 추적하는 기준이며 R2 객체 삭제는 여전히 미구현/비활성이다.

### 인증·운영 제한

- 사용자 발급 fine-grained 토큰: 지정 비공개 저장소 1개, Contents 읽기·쓰기. API/batch `ERASURE_CHECKPOINT_GITHUB_TOKEN` 시크릿에 등록 확인. 값 출력/로컬 복사 없음.
- 확정된 세대는 두 저장소의 `ERASURE_CHECKPOINT_DATABASE_EPOCH` 준비 변수에 등록. 준비 배포는 `ERASURE_CHECKPOINT_ENABLED=false` 강제 유지.
- [새 토큰 실제 읽기 검증](https://github.com/toilet-project/toilet-batch/actions/runs/34045385160) 성공. DB/R2 접근·GitHub 쓰기는 하지 않았다. 이 결과는 실제 쓰기 권한/운영 SQL lock 통합 검증까지 완료했다는 뜻이 아니다.
- 코드: [API PR #86](https://github.com/toilet-project/toilet-api/pull/86), [batch PR #38](https://github.com/toilet-project/toilet-batch/pull/38). feature만 반영했으며 운영 writer는 아직 예전 버전이다.
- GitHub 인증/가용성에 새 의존성이 생긴다. 실패하면 즉시 파기 성공으로 응답하지 않으며 배치의 기존 재시도/실패 기록 경로를 이용한다. 토큰 만료 시 재발급이 필요하다. 장기적으로 GitHub App을 권장한다.
- v1은 전체 목록을 검증하는 보수적 구현이다. 파기 1건마다 R2 요청 수가 목록 크기에 비례한다. 100,000건 상한·Git 트리 응답 잘림/크기 제한에서는 보류하며 규모가 커지기 전에 증분 증명 구조를 검토해야 한다.
- GitHub도 WORM이 아니며 전용 토큰의 Contents 권한 자체가 append-only 권한은 아니다. 현재 플랜의 강제 브랜치 보호 제한과 관리자/서버 계정 침해 위험은 남는다.

## 4. 사본 범위와 선택한 정책

2026-09-07 01:10~01:13 KST 읽기 전용 검사. DB 행·Redis 값·로그 원문을 읽지 않았다.

| 대상 | 실제 확인 | 처리 정책 |
| --- | --- | --- |
| 암호화 SQL 덤프 | 관련 경로 11개, metadata 없는 기존 10개 유지 | 신규 metadata 기준 14일 검토. legacy는 정확한 파일/hash별 별도 정리 승인. 이번 삭제 0 |
| MySQL binlog | 30일 자동 만료 설정, 실제 `binlog.000001`~`000016` 파일 존재 | 30일 유지안. 강제 PURGE/RESET/flush 없음. 설정만으로 삭제 완료 판단 금지 |
| Redis | AOF 켜짐, `dump.rdb`와 AOF base/incremental/manifest 존재 | **사용자 선택: 디스크 영속화 중지, 재시작 시 재로그인**. 실제 설정/파일 변경은 아직 하지 않음 |
| Docker volume | 프로젝트 MySQL 1개·Redis 1개 | 기존 볼륨은 백업과 구분. Redis 파일은 설정 중지만으로 사라지지 않으므로 후속 확인 필수 |
| 서버 스냅샷 | LVM snapshot 없음, `snap saved` 없음 | 외부 스토리지/새 수동 사본 도입 시 목록 갱신. 사용자 별도 사본 없다는 앞선 확인 유지 |
| R2 의도·완료 대장 | 암호화 선기록 및 독립 기준 설계 | 객체 생성 나이로 TTL 삭제 금지. 실제 부재 확인·사본 제거 증빙 후 별도 검토 |

MySQL 애플리케이션 계정은 `SHOW BINARY LOGS` 권한이 없어, 확인된 볼륨에서 로그의 이름·크기·mtime만 확인했다. 가장 오래된 파일의 mtime은 8월 20일이며 30일을 넘는 mtime 표시는 없었다. **파일 mtime은 로그 내부 이벤트 시각·복구 필요 범위·제거 완료 증빙을 대체하지 않는다.** 관련 home 백업 경로·Docker volume·LVM/snap 목록을 점검했으며 접근 불가능한 외부 사본의 부재까지 기술적으로 보증하지 않는다.

### Redis 배포 시 체크 — 지금 미실행

- [ ] API가 아닌 Redis 프로세스의 `save`/`appendonly` 설정을 모두 비활성으로 변경하고 재시작 영향 안내.
- [ ] 재시작 후 RDB/AOF를 다시 로딩하지 않도록 기존 persistence 파일 처리 계획을 함께 적용.
- [ ] 위에서 확인한 정확한 RDB/AOF/manifest 경로·hash·크기를 재확인하고 별도 승인 후 처리. Redis 볼륨 전체 삭제/FLUSHALL로 대체하지 않음.
- [ ] 재시작 후 기존 refresh 세션으로 갱신되지 않고 Google/Kakao 재로그인이 정상 동작하는지 확인.
- [ ] disk에 이전 파일이 남거나 새 persistence 파일이 생성되지 않았는지 확인. swap·메모리 이미지·core dump까지 영구 흔적이 없다고 보증하지 않음.

### 사용자 고지 검토

현재 feature 정책안에는 선택 동의한 복구용 정보만 달력상 3개월 보관하고 이메일/소셜 토큰은 복구용으로 보관하지 않는 내용이 있다. 선택 동의 거부·철회 경로와 실제 처리 주기, 장애 재시도 중 접근 차단을 화면과 함께 검증해야 한다. 이번에 운영 정책 페이지나 시행일을 변경하지 않았다.

추가 고지 초안: “탈퇴 시 서비스 이용과 세션을 중지하며, 별도 동의한 복구용 정보 외 회원정보는 파기합니다. 장애 복구용 백업에 남은 정보는 접근을 제한하고 정해진 보관·파기 절차로 관리합니다. 백업 복원 시 이미 파기한 회원정보가 서비스에 재사용되지 않도록 파기 이력을 재적용합니다.” 실제 설정과 일치하는 보유 기간·수탁/외부 저장·국외 이전 항목을 확정한 뒤 게시해야 한다.

**14일 덤프·30일 로그·32일 대장 검토 기준은 기술 운영안이지 법정 유예 기간이 아니다.** 3개월 복구 동의를 모든 사본/대장의 무제한 보관 근거로 쓰지 않는다. 처리 목적이 끝난 개인정보 파기와 복구·재생 방지 원칙에 맞게 필요성·최소 정보·접근 제한·실제 삭제 확인을 함께 검토해야 한다. [개인정보 보호법 제21조](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?ancYnChk=&chrClsCd=010202&lsJoLnkSeq=1020398651). 이 점검은 법률 적합성 확정 의견을 대신하지 않는다.

## 테스트와 다음 경계

- 자동 복원 Linux 합성 테스트 **46/46 통과**, [CI](https://github.com/toilet-project/docs/actions/runs/34044637719). 실제 운영 백업 격리 시험 성공은 별도로 위에 기록했다.
- batch 로컬 전체 **184개: 176 통과, 8 skip, 실패 0**. skip은 별도 자격 증명/격리 서버가 필요한 테스트이며 새 GitHub 읽기 시험은 위 별도 CI에서 수행했다.
- API 로컬 인증/공유 파기 테스트 **91개: 87 통과, 4 skip, 실패 0**. 전체 API 테스트를 이 수치로 표현하지 않는다.
- Node 배포 준비 검사 **10개 통과**. API/batch 공유 계약 **12개 파일 동일**.
- API PR #86과 batch PR #38의 등록된 테스트·CodeQL 검사 전부 성공 확인. [batch 통합 검사](https://github.com/toilet-project/toilet-batch/actions/runs/34045387375), [API 인증/프로필 검사](https://github.com/toilet-project/toilet-api/actions/runs/34045348883). API commit `d1b6cbb`, batch 코드 `2c5a726` 및 읽기 전용 CI 연결 `4b6adb1`.
- GitHub 쓰기/CAS·부분 R2 실패·누락·동일 건수 변조·재시도는 합성 transport/fixture 테스트. 실회원 파기, 실제 GitHub 집계 추가, 운영 SQL advisory lock 동시성 시험은 미실행.

다음은 첫 정기 실행 확인과 위 Redis/정책 배포 체크를 포함한 **5단계 배포 계획 검토**다. 실제 main 병합/V11 적용/API·배치 재배포 및 6단계 활성화는 별도 승인 범위다. 지금 상태를 회원 자동 파기 기능의 운영 완료로 표시하지 않는다.
