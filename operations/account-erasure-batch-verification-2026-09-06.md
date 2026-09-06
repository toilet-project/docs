# 회원정보 파기 배치 이관 검증 — 2026-09-06

상태: **로컬 구현 및 테스트 완료. 원격 push/병합/배포/운영 회원 삭제는 하지 않음.**

기존 [탈퇴·복구 검증](account-retention-verification-2026-09-06.md) 이후 결정: API의 1분 타이머 대신 공공데이터 수집이 끝나면 배치 서버에서 자동 파기한다.

## 변경 사항

- toilet-batch main b246d4d 기반 별도 로컬 feature/account-withdrawal-retention 작업 디렉터리. 기존 행정구역 정규화 브랜치는 보존했다.
- RestroomSyncScheduler finally에서 AccountErasureJob 실행. 동기화 성공/실패 종료 모두 실행하되 공공데이터 실행 이력을 파기 결과로 바꾸지 않는다.
- API AccountErasureScheduler 제거. 즉시 파기/만료 후 OAuth 재가입에 쓰는 AccountErasureService 유지.
- API와 배치 AccountErasureSql v1 동일 사본 및 비교 스크립트. 자동 공유 모듈은 아니므로 릴리스 전 일치 검사가 필수다.
- Redis 회원별 인증 키 삭제, 트랜잭션·행 잠금·상태 재확인, 50명 keyset 순회/실행당 기본 5,000명 상한, 실패 체크포인트·집계 알림.
- 마지막 회원 삭제 행 수가 1이 아니면 롤백. DDL 변경은 없고 기존 V11 사용.
- 운영 자동 파기는 기본 false, 배치 배포 워크플로에서도 false로 고정.

## 실제 실행 결과

| 검증 | 결과 |
| --- | --- |
| 배치 전체 테스트 | 84건 중 **83 통과 / 1 건너뜀 / 실패 0** |
| 신규 파기 및 동기화 연결 테스트 | 전체 결과에 포함된 **16건 통과** |
| API auth·policy·제보·알림 회귀 | 74건 중 **72 통과 / 2 건너뜀 / 실패 0** |
| API ↔ batch AccountErasureSql 비교 | 줄바꿈 정규화 후 동일 |
| git diff --check | 변경 저장소 통과 |

배치 건너뜀: 기존 RegionRecordedSampleTest는 비공개 표본 경로 REGION_REPLAY_DIR가 없어 미실행.
API 건너뜀: Docker가 필요한 AccountWithdrawalMySqlTest, AuthDataModelIntegrationTest. 실제 MySQL 통과로 간주하지 않는다.

배치 전체 최초 실행은 Windows 임시 폴더 권한으로 기존 테스트 19건이 실패했다. 정상 임시 폴더 접근 권한으로 재실행한 위 최종 결과와 구분한다. 테스트 단언은 완화하지 않았다.

### 검증 시나리오

- 동기화 성공 후 파기, 실패 후 파기, 동기화 실패 알림 오류에도 후속 실행.
- 비활성 상태에서 DB/Redis 미접근.
- Redis refresh/recovery 회원별 키만 삭제, Redis 오류 전파.
- SQL/미확인 FK 오류 시 모든 DB 변경 롤백, 재시도 체크포인트 기록.
- 한 회원 실패·체크포인트 오류가 있어도 다음 회원 계속 처리.
- 기한 전/복구 완료/새 동의가 없는 과거 탈퇴 회원 삭제 제외.
- 구조화된 제보 좌표 수정안 유지, 작성자·자유 텍스트 제거.
- 삭제 중 keyset 순회 누락 방지, 상한 초과 백로그 알림.
- 복구가 회원 행 잠금을 잡은 경우 파기는 대기 후 커밋된 ACTIVE 상태를 보고 삭제하지 않음(H2).
- 기반 시스템/알림 실패가 다음 호출을 막거나 공공데이터 실행 이력을 바꾸지 않음.

## 실행 명령

```powershell
# toilet-batch
./gradlew.bat test
./scripts/verify-account-erasure-contract.ps1 -ApiRepository C:/fork/tiolet/.codex-api-profile
# toilet-api
./gradlew.bat test --tests '*auth.*' --tests '*policy.*' --tests '*ToiletReportServiceTest' --tests '*UserNotificationServiceTest'
```

Temurin 21.0.12, Gradle 9.5.1. 격리 H2/모의 Redis 및 로컬 HTTP 응답 사용. 운영 DB·Redis·Discord 미접근, 공개 Maven 의존성 다운로드만 수행.

## 운영 전 남은 조건

1. 실제 MySQL V11/FK/동시 복구·파기/쿼리 계획 검증.
2. 배치 런타임 DB 권한, API와 동일한 Redis 연결/DB 번호, 배치 저장소 REDIS_PASSWORD 설정 확인.
3. 백업 삭제 대장 외부 저장 및 복원 후 재파기 적용 — **아직 미구현**.
4. 실제 OAuth 및 Discord 알림 검증.
5. 정책/동의 문구에 정확한 복구 기한과 다음 일일 배치의 물리 파기 시점 구분.
6. 소스 원격 업로드/CI와 배포 승인. 두 기능 스위치는 비활성.

자동 재시도는 다음 일일 실행이다. 재시작 즉시 삭제하지 않고 수동 수집/정규화 CLI에도 파기를 붙이지 않았다. 동기화가 종료되지 않는 장기 장애에는 파기도 지연되므로 배치 완료 감시가 필요하다. 성공 로그·메트릭은 영구 삭제 대장을 대체하지 않는다.
