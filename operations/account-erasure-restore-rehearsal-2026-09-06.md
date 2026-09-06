# 암호화 백업 복원 · 회원 재파기 통합 검증

상태: feature 구현 및 **가상 암호화 백업 통합 리허설 통과**. 운영 배포·실제 회원 삭제·실제 운영 백업 내용 조회는 하지 않았다.

## 최종 결과

| 검증 | 결과 |
| --- | --- |
| [배치 d2a70b3: 암호화 백업·R2 재파기 리허설](https://github.com/toilet-project/toilet-batch/actions/runs/34032004569) | 성공. 실제 실행 1건·실패/오류/건너뜀 0 확인 |
| [배치 d2a70b3: 전체 회귀](https://github.com/toilet-project/toilet-batch/actions/runs/34032004562) | 성공 |
| [API f75d4e2: 계정·격리 MySQL 회귀](https://github.com/toilet-project/toilet-api/actions/runs/34032011126) | 성공 |

통합 리허설의 가상 데이터 결과:

- 복원 직후 회원 2명 → 파기 대상 1명 확인(dry-run에서는 변경 0).
- 재파기 적용 후 회원 1명. 파기 대상이 아닌 회원 유지.
- 제보 1건·화장실 1건 유지. 다시 dry-run하면 삭제 대상 matched=0, absent=1.
- 같은 암호화 백업을 별도 새 컨테이너로 복원하고 기대 대장 건수를 틀리게 지정한 시험은 dry-run 단계에서 거부.
- 가상 R2 객체 삭제 및 해당 prefix 0건 확인. 이 실행의 컨테이너·네트워크가 남지 않은 것을 CI에서 확인.
- main 병합·운영 배포 없음. docs의 wrapper 변경도 로컬 브랜치에만 있으며 미니 PC 설치본은 변경하지 않았다.

실제 R2에는 사용자 기록이 아닌 매번 난수 realm을 쓰는 가상 레코드만 전송했다. GitHub에서 Secret을 실행 환경에 주입했으며 값·키 지문·DB 덤프를 로그/아티팩트로 공개하지 않았다.

## 운영 백업 읽기 전용 확인

2026-09-06 미니 PC에서 비밀값 없이 systemd 설정과 파일 이름·수정 시각만 조회했다.

- 시스템 단위 `geupddong-mysql-backup.timer`는 active, 매일 `03:15:00 Asia/Seoul`이다. 사용자 단위 timer가 아니라 시스템 timer다.
- 서버 OS 시각은 UTC다. 최근 예약 실행 `2026-09-05 18:15 UTC`는 한국시간 `2026-09-06 03:15`다.
- 설정의 `GEUPDDONG_BACKUP_RETENTION_DAYS` 기본값은 14이며 해당 서비스의 조회한 설정에서 별도 기간 재정의는 보이지 않았다.
- 파일 정리는 `find -mtime +14`로 약 15일 경과 후 대상이 되며, 다음 백업이 성공한 뒤 실행된다. 백업 작업이 실패하면 기간을 넘긴 사본이 남을 수 있어 엄격한 14일 만료 보장은 아니다.
- 확인한 정기 백업 디렉터리에 암호화 덤프 10개가 있었다. 다른 디렉터리·내려받은 파일·스냅샷·binlog·Redis 사본까지 없다고 확인한 것은 아니다. 사용자에게 별도 사본 유무를 질문했다.
- 실제 운영 MySQL 바이너리는 8.0.46이다. 이번 CI 격리 검증도 같은 MySQL 버전을 사용한다.

## 복원 연결 방식

기존 docs `operations/scripts/mysql-restore-verify.sh`는 테이블·화장실 건수만 확인했다. 개선안은 기본 모드에서 batch의 `scripts/mysql-restore-erasure-verify.sh`에 위임한다. 도구가 없거나 설정이 빠지면 중단한다. 기존 구조 검사만 필요하면 `GEUPDDONG_RESTORE_MODE=structure-only`를 명시해야 하며, 출력에도 운영 연결 금지를 표시한다. 운영 서버의 설치본은 아직 변경하지 않았다.

새 절차:

1. 명시적으로 선택한 암호화 백업의 SHA-256을 확인한다. 원본 백업과 키 파일은 수정하지 않는다.
2. 매 실행 난수 이름·소유 라벨을 가진 Docker 내부 네트워크와 MySQL 8.0.46 컨테이너를 생성한다. DB의 외부 통신을 차단하고 호스트 포트는 공개하지 않는다. 호스트의 복원 CLI만 Docker inspect로 확인한 내부 IPv4의 43317 포트로 접속한다. 추가 네트워크 연결이나 공개 포트가 있으면 중단한다.
3. 임시 root 비밀번호를 난수로 생성한다. event scheduler, binlog, LOCAL INFILE을 끈다. 백업 안의 예약 이벤트가 복원 중 실행되지 않게 한다.
4. 복호화·압축 해제 결과를 MySQL로 파이프 전달한다. 실제 백업의 평문 SQL을 호스트 파일로 저장하거나 오류 로그를 공유 터미널에 출력하지 않는다.
5. V11 모양의 스키마 존재를 확인하고 새 guard 난수를 생성한다. CLI가 명시된 사설 IPv4·43317 포트·guard·서버 UUID·이벤트 OFF·binlog OFF를 재검증한다. 도메인·공인 IP·localhost를 컨테이너 전용 모드의 대상으로 허용하지 않는다.
6. 호스트의 독립 Java CLI가 R2 전체 대상 목록을 검증한다. DB 컨테이너에 R2 키를 전달하지 않는다. Spring 서버·공공데이터 스케줄러를 기동하지 않는다.
7. dry-run → 격리 DB에 재파기 적용 → 다시 dry-run으로 대상 0건을 확인한다. 전체 회원 수 감소가 재파기 수와 맞는지, 제보·화장실 건수가 유지되는지 검사한다.
8. 성공·실패 모두 이번 실행이 만든 컨테이너/익명 볼륨/네트워크를 식별자와 라벨 확인 후 정리한다. 운영 DB로 승격하거나 애플리케이션에 연결하는 기능은 없다.

## 실행 전 필수 조건

- `./gradlew installErasureTools`로 batch의 CLI classpath를 생성한다. `build/erasure-tools/lib`에는 plain jar와 런타임 라이브러리가 들어가며 devtools는 제외한다.
- `GEUPDDONG_ERASURE_TOOL_DIR`은 `lib` 상위 경로, `GEUPDDONG_BACKUP_KEY_FILE`은 기존 백업 복호화 키 경로다.
- R2 환경 변수는 [기존 R2 가이드](account-erasure-r2-2026-09-06.md)의 값을 사용한다. 복원 전용 읽기 전용 S3 키 발급을 권장한다. 키 원문을 쉘 명령 인수나 기록에 넣지 않는다.
- `ERASURE_RESTORE_WRITERS_STOPPED=true`: R2 파기 기록 작성자를 중지했거나, CI처럼 독립된 가상 realm에 다른 작성자가 없음을 확인한다.
- `ERASURE_RESTORE_INVENTORY_CONFIRMED=true`와 `ERASURE_RESTORE_EXPECTED_OBJECTS`: 신뢰할 수 있는 독립 목록과 기대 건수를 확인한다. 누락된 R2 목록을 보고 기대 건수를 줄여 통과시키지 않는다.
- wrapper에는 `GEUPDDONG_ERASURE_RESTORE_SCRIPT`로 설치한 batch 스크립트 경로를 지정한다.

```bash
# 키는 보호된 실행 환경에 먼저 주입. 아래는 비밀값 없는 실행 형식만 제시한다.
bash scripts/mysql-restore-erasure-verify.sh /absolute/path/to/selected.sql.gz.enc
```

서버 장애로 작성자를 멈출 수 없는 경우, 별도 복원 절차와 검증된 일관성 있는 목록이 마련되기 전 운영 승격하지 않는다. 새 격리 DB는 Redis에 연결하지 않지만, 실제 운영 복원 시 기존 Redis 세션 폐기는 별도로 필요하다.

## 보관 기간을 바로 설정하지 않은 이유

R2 레코드는 DB 삭제 성공 기록이 아니라 **삭제 전 파기 의도**다. R2 작성 후 DB 삭제가 오래 실패할 수 있으므로 객체 생성 후 단순히 30일 TTL을 주는 것은 안전하지 않다. 뒤늦게 DB 삭제가 성공했는데 이전 백업이 아직 남아 있을 때 대장이 먼저 만료될 수 있다.

따라서 운영 활성화 전 다음을 확정해야 한다.

- 모든 복구 가능한 사본의 최장 보관 기간과, 백업 성공 여부와 독립적인 만료 처리·실패 경보.
- 계정 삭제 완료/부재를 확인한 뒤 마지막 개인정보 포함 백업의 만료까지 대장을 보존하는 조건부 정리 절차.
- 의도 대장·삭제 완료 증빙·키링의 보관 및 복구 정책. 기한이 지난 레코드를 무조건 영구 보관하지도, 객체 나이만 보고 자동 삭제하지도 않는다.
- R2 보존 잠금은 삭제·덮어쓰기를 막고 lifecycle보다 우선한다. 적용 범위는 운영 prefix로 제한하고 가상 검증 영역과 분리한다. 아직 변경하지 않았다. [Cloudflare 공식 문서](https://developers.cloudflare.com/r2/buckets/bucket-locks/)

별도 백업 사본에 대한 사용자 확인을 받기 전에는 R2 자동 만료·보존 기간을 확정 적용하지 않는다. 이 작업은 법적 적합성을 확정하는 검토를 대체하지 않는다.

## 검증에서 발견한 문제와 보완

- 최초 리허설은 Docker 내부 네트워크에서 공개 포트를 조회하는 단계에서 실패했다. 격리를 해제하지 않고, 공개 포트를 없앤 내부 IP 접속 방식으로 수정했다. [Docker bridge 공식 설명](https://docs.docker.com/engine/network/drivers/bridge/)
- 로컬 MySQL 8.0.25에서 JVM UTC/DB +09:00 조건을 만들었을 때, `DATETIME → java.sql.Timestamp → LocalDateTime` 변환으로 가상 계정의 생성 시각 비교가 실패하는 것을 재현했다. API·배치의 대장 작성/복원 비교, 배치 파기 기한을 JDBC `LocalDateTime`으로 직접 읽도록 변경했다. 기존 DB 값을 수정하지 않는다. [MySQL 시간 변환 설명](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-datetime-types-processing.html)
- 같은 격리 테스트에서 UTC와 Asia/Seoul 모두 원래 DB 시각을 유지하고 dry-run 대상이 일치하는 것을 확인했다. 로컬 배치 선택 검증은 20건 중 18 통과·외부 실행 전용 2 건너뜀, 실패 0이다. API 계정 수명주기·대장 테스트 22건도 통과했다.
- CLI와 셸 오류는 고정된 단계 코드만 표시하고 SQL·키·상세 서버 로그를 출력하지 않는다. 최초 실패 기록을 성공으로 덮어쓰지 않고 후속 실행 결과와 구분한다.
- 이번에 실행한 로컬 MySQL 테스트 서버만 종료했고, 기존 Windows MySQL80 서비스는 그대로 Running이다.

## 남아 있는 범위

- 실제 운영 전체 스키마/과거 백업의 격리 복원 리허설. 이번 시험 데이터는 V11 형식의 가상 데이터다. V11 이전 백업은 자동으로 운영 DDL을 변경하지 않고 거부한다.
- 실제 복호화 키 복구 사본, 미니 PC CLI/환경 주입, 복원 전용 읽기 권한, 타이머·모니터링 설치.
- 독립 목록의 누락 방지와 보관 정책 최종 적용.
- 사용자 승인 후 main 병합·운영 배포·활성화. 현재는 feature 단계다.
