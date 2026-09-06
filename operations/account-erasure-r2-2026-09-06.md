# R2 암호화 파기 대장 — 구현·검증 보고서

검증일: 2026-09-06. 사용자의 추가 승인 후 API·배치 `feature/account-withdrawal-retention`을 원격에 push했다. docs는 로컬 브랜치다. **main 병합·운영 배포·회원 파기·실제 회원정보 외부 전송은 하지 않았다.**

## 저장소와 비용

- 기존 Cloudflare 계정에 비공개 Standard 버킷 `geupddong-account-erasure-ledger`를 생성했다. 기존 웹 캐시 버킷과 분리했다.
- r2.dev 공개 접근은 비활성화, custom domain은 없다. 플랜·결제 설정을 변경하지 않았다.
- APAC 위치 힌트를 사용했으나 한국 내 보관을 보장하는 설정은 아니다. 실제 식별정보 전송 전 처리방침·국외 보관 관련 검토가 필요하다. [공식 위치 안내](https://developers.cloudflare.com/r2/reference/data-location/)
- Standard 무료 제공량은 월 저장 10 GB-month, Class A 100만 회, Class B 1,000만 회다. 기존 캐시 버킷 사용량도 함께 고려해야 하며 초과 사용은 과금될 수 있다. 항상 무료라고 보장하지 않는다. [공식 요금](https://developers.cloudflare.com/r2/pricing/)

## 처리 순서와 안전 장치

1. 회원/탈퇴 회차를 잠그고 파기 기한 및 상태를 확인한다.
2. 최소 파기 의도를 AES-256-GCM으로 암호화한다. R2 업로드 전에 애플리케이션에서 암호화한다.
3. `v1/<realm>/<withdrawalKey>.bin`에 `If-None-Match: *` 조건부 저장한다. 기존 객체는 덮어쓰지 않고 복호화 결과의 동일성을 확인한다.
4. 업로드 후 다시 읽어 인증 태그와 전체 레코드가 일치하는지 검증한다.
5. 확인된 경우에만 Redis 증명 정리 → 기존 회원 파기 SQL 트랜잭션을 진행한다.

R2 기록은 **파기 의도**이지 DB 삭제 성공 영수증이 아니다. 외부 저장 성공 뒤 DB가 롤백될 수 있다. 동일 회차 재실행은 같은 객체 검증 후 계속 진행한다. 업로드 응답 유실도 다음 실행의 읽기 검증으로 복구할 수 있다.

R2 전역 장애나 미설정은 삭제를 보류하고 배치의 추가 외부 요청을 중지한다. 기존 집계 경보에 실패를 반영한다. 개별 SQL 오류는 트랜잭션 롤백·체크포인트 재시도 대상이다. 실제 Discord 도달은 아직 검증하지 않았다.

## 암호화 레코드

| 필드 | 의미 |
| --- | --- |
| version | 형식 버전 1 |
| realm | DB 환경 구분. 운영 production, 테스트 verification |
| userId | 원래 회원 ID |
| userCreatedAt | 실제 DB에 저장된 계정 생성 시각 |
| withdrawalKey | 탈퇴 회차 UUID |
| eligibleAt | 파기 가능한 기준 시각 |

이메일·닉네임·소셜 원문·제보 원문은 넣지 않는다. 위 식별자도 개인과 연결될 수 있으므로 개인정보로 보호한다. 객체 키에는 탈퇴 회차 UUID만 노출된다.

키 ID·랜덤 12바이트 nonce·암호문·인증 태그를 포함하는 버전형 envelope를 사용한다. realm과 객체 경로를 AAD에 결합해 다른 경로로 바꿔치기한 데이터를 거부한다. 키링으로 이전 키의 복호화를 지원한다. 이전 객체가 남아 있는 동안 이전 키를 제거하면 복원이 실패한다.

## 라이브러리·설정

Java 21 JCA AES/GCM, 기존 Jackson JSON, AWS SDK for Java v2 `s3`/`url-connection-client` 2.54.13을 사용한다. R2 HTTPS endpoint만 허용하고 region auto, path-style, chunked encoding 비활성화로 구성했다. [R2 Java SDK 안내](https://developers.cloudflare.com/r2/examples/aws/aws-sdk-java/)

연결 2초·소켓 4초·SDK 개별 시도 5초·전체 API 호출 15초 제한이다. SDK 재시도는 전체 호출 제한 안에서 동작하며, 해결되지 않은 파기는 기존 다음 일일 배치 재시도로 남긴다.

| 환경 변수 | 설정 |
| --- | --- |
| ERASURE_LEDGER_ENABLED | 기본 false. 미설정은 삭제 허용이 아니라 실패 처리 |
| ERASURE_LEDGER_REALM | production |
| ERASURE_LEDGER_BUCKET | geupddong-account-erasure-ledger |
| ERASURE_LEDGER_ENDPOINT | 해당 계정의 R2 S3 HTTPS endpoint |
| ERASURE_LEDGER_ACCESS_KEY_ID | 해당 버킷에만 제한한 S3 Access Key ID |
| ERASURE_LEDGER_SECRET_ACCESS_KEY | S3 Secret Access Key |
| ERASURE_LEDGER_ACTIVE_KEY_ID | 최초 k1 |
| ERASURE_LEDGER_KEYS_JSON | 키 ID → CSPRNG로 생성한 32바이트 키의 Base64 값인 JSON |

키 원문은 문서·Git·채팅에 남기지 않는다. JWT 키와 재사용하지 않는다. API와 배치가 같은 키링으로 기록을 읽을 수 있어야 한다. 복원용 읽기 전용 자격 증명은 별도로 발급하고, 암호화 키링은 미니 PC/DB 백업과 다른 비밀번호 관리 저장소에도 복구 가능하게 보관해야 한다.

사용자가 두 저장소에 S3 키 2개와 암호화 키링 Secret을 등록했다. GitHub에서는 등록 이름만 조회하고, 비밀값을 다시 꺼내거나 출력하지 않았다. 가상 데이터 검증 workflow에서만 실행 환경으로 주입한다. 미니 PC 배포 환경의 Secret 주입과 실제 서버에서의 연결 확인은 별도로 남아 있다. `ACCOUNT_RETENTION_ENABLED`, `ACCOUNT_ERASURE_ENABLED`, `ERASURE_LEDGER_ENABLED`는 운영에서 활성화하지 않는다.

## 격리 복원 도구

배치의 `accountErasureRestore` Gradle JavaExec 태스크는 기본 dry-run이며 명시적인 `--apply`에서만 변경한다. 웹 API나 정기 스케줄로 노출하지 않았다.

- localhost의 비운영 포트와 `erasure_restore_<난수>` 스키마만 허용한다.
- DB의 `erasure_restore_guard.marker`가 별도 32자리 난수와 일치해야 한다.
- 쓰기 중단 확인이 필요하며 apply에는 Redis 세션 초기화 확인도 필요하다.
- 예상 객체 수와 전체 목록이 일치하고 모든 레코드의 복호화·realm·파기 기준 시각 검증이 끝난 후에만 DB를 처리한다.
- 회원 생성 시각이 다르면 전체 작업을 중단한다. 이미 없는 회원은 별도 집계한다. 과거 백업의 ACTIVE 계정도 기록된 원래 계정이면 재파기한다.
- 출력은 records/matched/absent/erased 집계이며 회원 원문을 로그에 쓰지 않는다.

추가 환경 변수: `ERASURE_RESTORE_URL`, `ERASURE_RESTORE_DB_USER`, `ERASURE_RESTORE_DB_PASSWORD`, `ERASURE_RESTORE_MARKER`, `ERASURE_RESTORE_EXPECTED_OBJECTS`, `ERASURE_RESTORE_WRITERS_STOPPED=true`, 적용 시 `ERASURE_RESTORE_REDIS_RESET_CONFIRMED=true`. 일반 Spring Boot 기동이 아니므로 위 R2 설정도 환경 변수로 모두 제공한다.

**제한:** 예상 건수를 신뢰할 수 있는 독립 목록으로 확인해야 한다. 이미 객체가 유실된 목록을 보고 예상 건수를 줄이면 누락 탐지가 되지 않는다. R2 보존 잠금·실제 최장 백업 기간·대장 만료 정책은 아직 미설정이다. 기존 `mysql-restore-verify.sh`에 이 도구를 통합한 전체 백업 복원 리허설도 남아 있다. 현재 도구만으로 복원 운영 승인 조건을 충족했다고 보지 않는다.

## 실제 검증 결과

| 실행 | 결과 |
| --- | --- |
| API 관련 기본 회귀 | 87건 중 84 통과, 3 건너뜀, 실패 0 |
| 배치 전체 기본 테스트 | 86건 중 85 통과, 1 건너뜀, 실패 0 |
| native MySQL API 선택 실행 | 23 통과: 실제 DB 사용 14 + 암호화/S3 mock 9 |
| native MySQL 배치 선택 실행 | 18 통과: 실제 DB 사용 7 + 기타 단위 테스트 11 |
| API·배치 공유 계약 | Java 소스 7개 동일 |
| 실제 R2 가상 암호문 전송 | 업로드·다운로드 SHA-256 일치 |
| 실제 R2 가상 객체 정리 | 삭제 후 Key does not exist 확인 |

기본 API 건너뜀은 Docker 필요 2건과 native MySQL 환경 전용 1건이다. 배치 건너뜀은 비공개 지역 정규화 기록 fixture 미지정 1건이다. MySQL은 격리 로컬 8.0.25였으며 운영 버전/전체 스키마 검증으로 대체하지 않는다. 기존 MySQL80 서비스는 유지하고 이번 테스트 서버만 종료했다.

위 최초 R2 왕복은 Wrangler 인증을 사용한 **가상 데이터**다. 후속 Java/GitHub Secrets 검증은 아래 별도로 기록한다. 가상 암호화 fixture의 테스트 키를 운영에 사용하지 않는다. 최초 Wrangler 원격 가상 객체는 삭제했고 로컬 테스트 증빙만 남겼다.

테스트는 위변조/realm·객체 경로 변경, 키 교체, 기존 객체 재시도, 읽기 검증 실패, 응답 유실, R2 실패 시 DB·Redis 보존, dry-run, 백업 ACTIVE 계정 재파기, 다른 생성 시각 충돌 시 전체 롤백을 포함한다.

## 변경 파일과 남은 순서

### 후속 GitHub Secrets 실제 연결 검증 — 2026-09-06

사용자의 feature push·검증 실행 승인으로 아래 검증을 실행했고 모두 성공했다.

| 저장소·커밋 | 검증 | 결과 |
| --- | --- | --- |
| API `8cce474` | [실제 R2 가상 객체 저장·읽기](https://github.com/toilet-project/toilet-api/actions/runs/34030834777) | 성공 |
| API `8cce474` | [계정 수명주기·격리 MySQL 회귀](https://github.com/toilet-project/toilet-api/actions/runs/34030834843) | 성공 |
| Batch `a06488e` | [교차 복호화·저장·정리](https://github.com/toilet-project/toilet-batch/actions/runs/34030940376) | 성공 |
| Batch `a06488e` | [배치 전체 격리 회귀](https://github.com/toilet-project/toilet-batch/actions/runs/34030940389) | 성공 |

두 저장소의 `ERASURE_LEDGER_ACCESS_KEY_ID`, `ERASURE_LEDGER_SECRET_ACCESS_KEY`, `ERASURE_LEDGER_KEYS_JSON`을 GitHub Actions 내부에서만 사용했다. 실제 Java SDK/프로젝트 암호화 구현으로 JSON 형식·32바이트 k1·R2 연결·업로드 후 복호화를 확인했다. API가 먼저 저장한 가상 암호문을 배치가 자신의 Secret으로 읽어야 통과하므로 두 저장소의 k1 호환성도 검증했다. Secret 값이나 키 지문은 출력하지 않았다.

검증 전용 realm `verification-20260906-c72e`, 가상 ID `Long.MAX_VALUE`와 그 이전 값, 고정 가상 시각으로 레코드 2개만 사용했다. 배치는 API 객체가 이미 있는지 확인한 후 자신의 객체를 생성했다. 성공 후 그 2개만 삭제하고 테스트 prefix 목록이 0건임을 확인했다. `v1/production/` 객체는 조회·수정하지 않았다.

테스트는 Spring 서버를 기동하지 않았고 MySQL·Redis·실제 회원정보에 접근하지 않았다. 회귀 작업의 MySQL은 Actions의 격리 테스트용이다. 배포 workflow는 main push 전용이므로 이번 feature push에서는 운영 배포를 실행하지 않았다. 검증 workflow는 feature의 지정 파일 변경에만 동작하며 PR에는 Secret을 전달하지 않는다. 기존 가상 run을 재실행하려면 API writer 성공 → batch 검증·정리 순서를 지켜야 한다. 중도 실패 시 남은 검증 객체는 원인을 확인하고 정확한 대상만 정리한다.

**완료 범위:** GitHub 저장 키의 실제 연결·교차 암호화 검증. **미완료 범위:** 미니 PC 런타임 주입·연결, 키의 별도 보관 확인, 보존 잠금·백업 최장 기간, 기존 백업 복원 스크립트 통합, 운영 승인·배포·활성화. 아직 운영 파기를 켜지 않는다.

- API/배치 공통: `com/geupddong/account/`의 ErasureLedger, ErasureRecord, ErasureCipher, R2ErasureLedger, ErasureLedgerFactory, AccountErasureRestore.
- API: ErasureLedgerConfiguration, AccountErasureService, AccountLifecycleIntegrationTest, ErasureLedgerTest, build.gradle, application.yml, 선택 CI 테스트 목록.
- 배치: ErasureLedgerConfiguration, AccountErasureWorker/Job, AccountErasureRestoreCli, Worker/Job 테스트, build.gradle, application.yml, 공유 계약 확인 스크립트.
- docs: 이 보고서, 백업 재파기 설계, Runbook, README, 변경 이력. 기존 V11 외 추가 DDL은 없다.

운영 전 남은 순서: 키의 별도 복구 사본 확인 → 실제 최장 백업 기간/대장 보존·잠금·키 복구 정책 확정 → 복원 스크립트 통합 및 격리 리허설 → 정책·운영 동일 스키마·권한 검증 → 별도 승인 후 main 반영/런타임 주입/배포/활성화. 정상 사용자를 테스트 목적으로 삭제하지 않는다.
