# 탈퇴·복구·자동 파기 구현 검증 · 2026-09-06

후속 변경: 정기 파기 실행 주체를 API에서 배치로 옮겼다. 현재 실행 주기와 최신 테스트 수치는 [배치 이관 검증](account-erasure-batch-verification-2026-09-06.md)을 참고한다. 아래는 최초 구현 시점의 기록이다.

## 결과 요약

**로컬 구현 및 격리 검증 완료 단계. 원격 업로드·운영 DB 변경·운영 배포·자동 파기 활성화는 하지 않았다.**

- 공통 브랜치: `feature/account-withdrawal-retention`
- API 로컬 커밋: `d04eb19` (기능 `004dd70` 포함). 운영 main `4c32cce` 위로 통합.
- 웹 로컬 커밋: `a0463cc`. 운영 main `7f11474` 기준.
- 원격 업로드는 소스 전송의 명시적 승인 필요로 자동 보안 검토에서 차단됐다. 우회하지 않았다.
- [설계·DDL 설명](../database/account-withdrawal-retention-v1.11.md), [DDL](../database/ddl/v1.11-account-withdrawal-retention.sql), [적용·백업 Runbook](account-erasure-runbook.md)

## 검증한 기능

- 선택 동의 기본 미선택; 동의 거부 시에도 즉시 파기 방식 탈퇴 가능.
- 달력상 3개월, 말일 보정, 만료 시각부터 복구 불가.
- 응답의 확정 삭제 예정일은 실제 접수 시각으로 계산한 KST offset 포함 값이다.
- 같은 소셜 계정 인증 후 명시적 복구; 닉네임·회원 ID·제보 연결 복원.
- ADMIN 자동 복구 금지, USER만 부여, 필수 동의 재확인.
- 복구 확인은 일반 JWT/리프레시와 분리. OAuth 세션 종료, 확인 쿠키 HttpOnly/Secure/10분/전용 경로.
- 만료·위조 회차·재사용 인증 거부; 임의 이메일/사용자 ID로 복구 불가.
- 이전 access token은 탈퇴 직후 및 복구 후에도 무효. 기존 닉네임 수정 기능 유지.
- 실제 SQL로 회원 행을 삭제하고 제보의 구조화된 화장실 수정 정보 보존.
- 자유 사유·검토 메모 및 회원 연결 파기, 알림/동의/소셜/역할/복구 정보 제거.
- 알림 대상이 파기됐을 때 알림을 새로 생성하거나 계정 연결을 복원하지 않음.
- 새 FK 오류 시 전체 DB 파기 롤백, Redis 장애 시 DB 데이터 보존, 재시도 체크포인트 저장.
- 서버 재시작 후 기한 경과 미처리 조회, 실패 한 건이 다른 계정 처리를 막지 않음.
- 과거 탈퇴자에 새 동의/복구 기간을 자동 적용하지 않음.

## 실제 실행 결과

| 검증 | 결과 |
| --- | --- |
| API 관련 회귀: auth·policy·제보·알림 | **73 통과, 2 건너뜀**, 실패 0 |
| H2 MySQL mode 실제 SQL/JPA 탈퇴 수명주기 | 10개 통과. 물리 삭제·원본 수정정보 보존·롤백·재시도 포함 |
| 웹 기존 단위 테스트 | 96개 통과 |
| 웹 TypeScript / oxlint | 종료 코드 0 |
| 브라우저 UI | 375×667 모바일, 1440×900 데스크탑 통과 |
| 전체 API 테스트 | **135개 중 125 통과, 5 실패, 5 건너뜀**. 전체 통과 아님 |
| API V11 ↔ docs DDL | 줄바꿈 정규화 후 내용 일치 |
| 실제 Google/Kakao 탈퇴/복구 E2E | 미실행. 실제 사용자 데이터 변경 없음 |
| 실제 MySQL V11 | 로컬 Docker 부재로 건너뜀. CI 검증 준비만 완료 |

전체 실행의 실패 5개:

1. `CacheInvalidationMySqlTest`: Docker 환경 없음.
2. `CacheInvalidationPipelineMySqlTest`: Docker 환경 없음.
3. `ToiletRegionMySqlTest`: Docker 환경 없음.
4. `ToiletSitemapMySqlTest`: Docker 환경 없음.
5. `CoordinateAddressMigrationTest`: 기존 V9의 MySQL 다중 ALTER 구문을 H2가 처리하지 못함. 해당 V9/테스트 파일은 이번에 변경하지 않았다.

건너뛴 5개는 `AccountWithdrawalMySqlTest` 1개, `AuthDataModelIntegrationTest` 1개, `ToiletDatabaseIntegrationTest` 3개다. 건너뜀을 통과로 계산하지 않는다.

브라우저 검증은 로컬 개발 서버에서 모든 업무 API를 mock 응답으로 대체하고 외부 지도 SDK 요청을 차단했다. 실제 OAuth·제보·탈퇴 요청은 보내지 않았다. 개발 배지의 클릭 간섭만 제외하고 런타임 오류 검사는 유지했다. 모바일 긴 안내는 모달 내부 스크롤로 확인했다.

## 실행 방법

```text
API:
./gradlew test --tests '*auth.*' --tests '*policy.*' --tests '*ToiletReportServiceTest' --tests '*UserNotificationServiceTest'
./gradlew test

Web:
node --experimental-strip-types --test tests/*.test.mjs
node node_modules/typescript/bin/tsc --noEmit
node node_modules/oxlint/bin/oxlint src next.config.ts open-next.config.ts
PLAYWRIGHT_MODULE_PATH=<로컬 playwright 경로> node tests/account-withdrawal-regression.cjs
```

CI 설정 `.github/workflows/account-retention-validation.yml`은 승인 후 feature push 시 격리 Docker/MySQL 검증만 실행한다. 운영 배포 workflow는 main push에 한정된다. main/develop 병합은 별도 단계다.

## 운영 활성화 전 남은 필수 항목

- 실제 MySQL DDL·삭제 트랜잭션·동시 복구 검증.
- 운영 스키마의 추가 FK/비-FK 회원 참조 검토.
- 백업 삭제 대장 자동 내보내기·별도 보관 및 복구 후 삭제 재적용 구현·리허설.
- 실제 백업/스냅샷/binlog/Redis 보관 기간 확인 및 정책 고지 확정.
- 운영 OAuth 테스트 계정으로 접수·복구·즉시 파기 E2E.
- 기존 장애 알림에 파기 실패·기한 경과 지표 연결 및 전달 확인.

따라서 기능 플래그는 **비활성**이 기본이다. 회원 행 삭제만 구현하고 백업 사본까지 즉시 파기됐다고 표시하지 않는다.
