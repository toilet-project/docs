# 계정 파기 준비: CI 및 기존 Redis 연결 검증

2026-09-07 KST. **읽기 전용 연결 검사 통과 / 운영 배포·파기 활성화 미실행**.

## 검토 대상과 CI

- [API PR #86](https://github.com/toilet-project/toilet-api/pull/86), `fd9cf2a`: 보고 시점 등록된 검사 모두 통과(계정 수명주기, 인증·기타 회귀, CodeQL 포함).
- [배치 PR #38](https://github.com/toilet-project/toilet-batch/pull/38), `55ecac1`: 보고 시점 등록된 검사 모두 통과(배치 테스트, CodeQL 포함).
- [문서 PR #71](https://github.com/toilet-project/docs/pull/71): 초안으로 검토 중. 별도 자동 검사는 등록되어 있지 않다.

CI 통과는 운영 활성화 승인이나 실제 계정의 파기 완료를 뜻하지 않는다. 세 PR 모두 초안 상태를 유지한다.

## 미니 PC Redis 읽기 전용 검사

기존 API 런타임의 비밀번호를 서버 메모리에서만 읽어 사용했다. 현재 배치 컨테이너 안에서 `nc`로 접속했으며, 비밀번호를 명령 인자·파일·로그에 넣지 않고 표준 입력으로 RESP 요청을 전달했다.

| 확인 | 결과 |
| --- | --- |
| API·배치·Redis의 공통 Docker 네트워크 | 확인 |
| 배치에서 `redis` 이름이 기존 Redis 컨테이너 주소로 해석됨 | 확인 |
| 기존 API 자격 증명으로 AUTH | 성공 |
| 연결 단위 SELECT 0 | 성공 |
| PING | PONG |
| QUIT | 정상 종료 |
| 회원 키/값 조회·수정·삭제 | 수행하지 않음 |
| 컨테이너 재생성·설정 변경·배포 | 수행하지 않음 |

이 결과는 **배치 네트워크에서 기존 Redis에 접속할 수 있다는 증거**다. GitHub에 저장한 Secret 값을 다시 읽은 검증이나, 새 배치 Spring 애플리케이션의 런타임 검증은 아니다. 현재 운영 배치 설정은 아직 API와 일치하지 않으며, 이는 미배포 상태로 구분한다. 전체 키 목록 조회나 테스트 키 생성/삭제도 하지 않았다.

## 남아 있는 설정과 다음 순서

API·배치 저장소의 repository variable 이름을 확인했을 때 `ERASURE_LEDGER_ENDPOINT`, `ERASURE_LEDGER_REALM`, `ERASURE_LEDGER_BUCKET`, `ERASURE_LEDGER_ACTIVE_KEY_ID` 및 `ACCOUNT_LIFECYCLE_DEPLOYMENT_APPROVED`는 없었다. 마지막 승인 변수가 없는 것은 의도한 배포 차단 상태다. 이 검사는 repository variable 범위이며 organization variable을 포함한 모든 설정 공급원을 확인했다고 주장하지 않는다.

배포 workflow는 realm/bucket/key ID에 기본값을 제공하지만 endpoint에는 기본값이 없다. 따라서 시크릿 등록만으로 R2 배포 준비가 완료된 것이 아니다. 다음 순서로 진행한다.

1. 기존 R2 설정 출처와 대상 버킷·키 ID를 대조하고, 읽기 전용 실제 연결·초기 대장/독립 기준을 검증한다. 관측한 목록을 임의로 초기 기대값으로 삼지 않는다.
2. DB 복원 세대·metadata 백업·키 복구 및 웹 정책 전환 조건을 확인한다.
3. 점검 시간과 영향 범위를 안내한 뒤 main 병합/Flyway V11/운영 준비 배포를 별도 승인받는다.
4. 배포 후 Spring 배치의 실제 Redis 설정/연결을 확인한다. 회원 키를 시험 삭제하지 않는다.
5. 모든 선행 조건 확인 뒤 자동 파기를 별도로 활성화한다.

관련 문서: [배포 안전장치](account-erasure-deployment-guards-2026-09-07.md), [운영 절차](account-erasure-runbook.md).
