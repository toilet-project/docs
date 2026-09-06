# 독립 초기 기준·정기 메타데이터 백업 전환

2026-09-07 KST. **정기 백업·삭제 없는 점검/알림 설치 완료. 회원 자동 파기·운영 V11/API 배포는 미실행.**

## 승인과 초기 기준

운영자는 준비된 검증 외에 해당 R2 버킷에 실제 회원 파기 대장을 기록·삭제한 적이 없음을 확인했다. 운영 V11/파기 기능 미배포 점검 및 R2 HEAD/LIST 재검사(00:42 KST, 현재 버킷·운영 의도·catalogue 모두 비어 있음)와 함께 최초 0건 기준을 검토했다. 관측값만 임의로 복사해 초기화하지 않았다.

- 비공개 `operations-checkpoints`에 순번 1·count 0·목록 hash·복원 세대·기록 시각을 등록했다. 커밋 `06b4699`.
- 실제 프로젝트 `CatalogueCheckpoint.next`와 빈 검증 목록으로 생성했으며, 허용 필드/정규 JSON 검사와 로컬 6건 테스트 통과.
- GitHub 체크포인트 CI [실행 성공](https://github.com/toilet-project/operations-checkpoints/actions/runs/34043319897).
- [검증한 신규 metadata 백업](account-erasure-metadata-backup-rehearsal-2026-09-07.md)의 후보 세대를 현재 기준으로 채택했다. 과거 백업 metadata를 소급 생성하지 않았다. 향후 DB 복원 시에는 새 세대와 전환 검토가 필요하다.
- 회원 ID·이메일·키·덤프·회원별 목록은 체크포인트에 넣지 않았다. 실제 값은 비공개 저장소/운영 설정에서 관리한다.

비공개 저장소는 현재 플랜의 강제 브랜치 보호 제한이 남아 있다. CI/검토 절차는 불변 저장소가 아니다. 서버의 자동 체크포인트 갱신은 아직 연결하지 않았으므로 **초기 기준 등록을 지속적 갱신 완료로 해석하지 않는다**.

## 운영에 설치한 범위

| 구성 | 위치/동작 |
| --- | --- |
| metadata 백업 | `/home/luha/.local/bin/mysql-backup.sh` |
| 복원 세대 설정 | `/home/luha/.config/geupddong/database-epoch.env`, 권한 0600 |
| 점검 설정 | `/home/luha/.config/geupddong/backup-retention.env`, 권한 0600 |
| 점검 실행 | `mysql-backup-retention.sh --dry-run` 및 `/home/luha/erasure-tools/lib/` |
| 실패 알림 | `systemd-retention-failure.py`, 기존 Discord webhook 파일의 값만 사용 |
| 기존 백업 timer | 매일 03:15 KST 유지, active/enabled |
| 새 독립 점검 timer | 매일 04:15 KST + 최대 60초 지연, active/enabled |
| 복구용 사본 | `/home/luha/.local/state/geupddong-backup-transition/20260907/` |

기존 스크립트/백업 service를 사본으로 보존하고, 기존 파일 hash와 실행 상태를 검사한 뒤 백업 timer를 잠시 중지했다. 같은 백업 lock을 잡은 상태에서 파일/설정/유닛을 설치·검사하고 timer를 다시 시작했다. 기존 백업 디렉터리의 파일 hash는 모두 유지됐다. 실패 시 기존 백업 스크립트/service 복구 절차를 준비했으며 이번 설치에서는 사용하지 않았다.

기존 백업의 성공 후 자동 만료 삭제는 **사용자가 승인한 대로 중지**했다. 새 점검 timer는 항상 dry-run이고 삭제 승인 해시/`--apply`를 제공하지 않는다. 기존 백업을 자동으로 지우거나 회원 파기를 켜지 않는다.

설치 준비 폴더 약 166.2 MB는 검증 후 제거했다. 설치된 도구·설정·복구용 사본·백업은 남겨 두었다.

## 첫 실제 점검·Discord 결과

```text
dryRun=true
status=HOLD_LEGACY_METADATA
expired=0
ExecMainStatus=2
SYSTEMD_FAILURE_NOTICE_SENT
```

메타데이터가 없는 예전 백업 때문에 계획을 보류하는 **예상된 확인 필요 상태**다. `expired=0`을 만료 백업 없음의 최종 판정으로 해석하지 않는다. systemd는 exit 2를 failed로 표시해 OnFailure를 호출하며, 이를 정상 성공으로 숨기지 않았다. 알림 handler는 exit 0으로 종료했고 Discord 전송 성공 응답을 확인했다. 사용자의 실제 읽음 확인까지 뜻하지는 않는다.

실제 보류 알림 1건을 사용자 승인 범위에서 보냈다. 같은 실패 유형은 6시간 중복 억제하므로, 하루 뒤 같은 보류가 남으면 다시 알림이 갈 수 있다. 회원정보나 webhook 원문은 출력하지 않았다.

백업 실패와 점검 보류는 별도 알림 service/state를 사용한다. 백업 실패 문구는 `MySQL 백업 실패`로 구분했다. 이번에는 실제 백업 실패를 유발하는 추가 시험 메시지는 보내지 않았다. 로컬 알림 검사 18건 중 10 통과·Linux 전용 8 건너뜀, 실제 Linux 점검 OnFailure→Discord 경로 성공을 각각 구분해 기록한다.

## 남은 운영 과제

1. **03:15 첫 정기 실행 확인**: 설치 후 즉시 추가 덤프를 만들지는 않았다. 직전 1회 검증 성공과 다음 예약 실행 성공은 다르다. 새 checksum/metadata·실패 상태를 확인한다.
2. **기존 metadata 없는 백업 정리 계획**: 현재는 삭제 보류다. 계속 보관하면 사용량/보관 기간이 늘어나므로 백업별 범위·대체 복구본을 검토하고 별도 승인 후 정리한다. 이 전환으로 보관 기간 강제가 완료된 것은 아니다.
3. **최근 복원 검증 증빙 갱신**: 현재 설정은 검증한 백업 hash를 보호한다. 검증 후 36시간이 지나면 최신 검증본 조건을 충족하지 못할 수 있다. 자동 복원 검증/증빙 갱신을 아직 구현·설치하지 않았으며 파일 생성만으로 값을 자동 갱신하지 않는다.
4. **지속 체크포인트 갱신**: 실제 파기 활성화 전에 대장 변경별 독립 기준 갱신·실패 보류 경로를 운영 절차와 연결해야 한다.
5. **전체 사본·정책·API 전환**: binlog/Redis/외부 사본 범위, 정책·V11·OAuth/배치 런타임 검증은 별도다. 회원 자동 파기와 R2 객체 삭제는 계속 비활성이다.

복구용 사본을 무조건 되돌리면 예전 자동 만료 삭제도 다시 활성화될 수 있다. 롤백도 보관 정책 영향을 검토하고 수행하며, 기존 백업 삭제를 우회하는 수단으로 사용하지 않는다.
