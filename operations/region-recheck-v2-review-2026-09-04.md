# 행정구역 자동 재검증 v2 구현·검증 보고서

> 공개 요약본입니다. 작성 당시의 수치·검증 단계를 보존합니다. 최신 배포 및 남은 검증은 [관리자 검토 배포 보고서](region-admin-review-release-2026-09-05.md)를 참고하세요. 전체 JSON·시설별 검토 원문·운영 접속정보는 공개하지 않습니다.

2026-09-04 · API/batch/docs `feature/administrative-region-normalization` · 로컬 변경, 미커밋/미푸시/미배포

## 결과

이전 승인된 표본 분석의 저장 응답 1,000건을 실제 새 RegionNormalizer/Kakao 응답 파서로 재현했다. 추가 API 요청은 0회이며 운영 DB에 접근하거나 수정하지 않았다.

| 항목 | 결과 |
|---|---:|
| 기록 응답 재현 대상 | 1,000 |
| 기존 기본 판정 VERIFIED | 963 |
| v2 추가 검증으로 VERIFIED | 28 |
| v2 재현의 최종 VERIFIED | 991 |
| 수동 확인 유지 | 9 |
| 재현 실패 | 0 |
| 재현 중 원본 Source/평가 좌표 변경 | 0 |

위 수치는 같은 과거 응답을 사용한 회귀 결과다. 새 실시간 API 분석이나 운영 데이터 반영 결과가 아니며 전국 정확도 추정으로 사용하지 않는다. 좌표 없는 1,288건의 추가 실측을 이번에 수행하지 않았다.

수동 확인 유지 ID: **16501, 45043, 45217, 45564, 49027, 52159, 52160, 52205, 52638**. [37건 원래 분석 근거](region-normalization-random1000-review-list-2026-09-04.md)를 함께 본다. 원래 v1 판정 파일은 변경하지 않았다.

유등천 좌안-14는 API 간 지역 충돌을 보류하는 제어 테스트로 검증했다. 용산구 주소 붙임도 추가 구조화 증거가 있을 때만 승격하는 제어 테스트로 검증했다. 두 건을 이번에 실시간 API로 다시 조회한 것은 아니다.

## 실행한 검증

- batch `test bootJar`: **63 tests / 실패 0 / skip 0**, 빌드 성공. `REGION_REPLAY_DIR=C:\fork\tiolet\.tmp`를 설정해 1,000건 기록 응답 재현 테스트를 실제 실행했다.
- API `RegionAssessmentMigrationTest`: **1 test 통과**. 실제 V10 DDL을 H2 MySQL 호환 모드에서 실행, 기존 행 보존·재실행 중복 방지·독립 이력 보존·격리 스키마 롤백 검증. **실제 MySQL 8 검증을 대체하지 않는다.**
- 주소 0건/여러 건, 잘못된 코드, 먼 거리, 두 주소 중 한 쪽 불일치, 역지오코딩 API 간 충돌, 도로명/지번 객체 간 충돌, 일시 장애/한도 중단, 이전 알고리즘 체크포인트 무효화 검증.
- 현재 원본 동시 변경 시 쓰기 취소, 이력 재적용 중복 방지, 다음 판정 이후 이전 근거 보존, 이력 저장 실패 시 현재 상태 저장 롤백 검증.
- API/docs V10 DDL 동일성, 세 저장소 git diff whitespace 검사 통과.
- 기본 실행은 dry-run, 운영 워커는 여전히 OFF.

## 이번 변경 파일

batch `src/main/java/com/example/toiletbatch/region/`:
RegionModel, RegionProvider, AddressRegionCheck, KakaoRegionProvider, RegionNormalizer, **RegionRecheck(신규)**, RegionRepository, RegionJob.

batch `src/test/java/com/example/toiletbatch/region/`:
RegionNormalizerTest, RegionRepositoryTest, KakaoRegionHttpTest, **RegionRecheckTest(신규)**, **RegionRecordedSampleTest(신규)**.

API:
- `src/main/resources/db/migration/V10__create_toilet_region_assessment_history.sql`
- `src/test/java/com/example/toiletapi/geocoding/RegionAssessmentMigrationTest.java`

docs:
- [v1.10 설계·관리자 연결 계약](../database/region-assessment-history-v1.10.md)
- [v1.10 DDL](../database/ddl/v1.10-region-assessment-history.sql)
- 본 보고서, README, CHANGELOG

## 운영 반영 전 남은 항목

사용자 확정 정책: 공공데이터 최초 지오코딩의 첫 검색 결과 선택을 유지하며 이를 단일 결과 전용으로 바꾸는 작업은 하지 않는다. 빈 좌표는 정규화 작업으로 자동 채우지 않고 관리자 확정 후 정규화한다. 따라서 최초 지오코딩 변경/자동 좌표 채움 활성화는 아래 배포 선행 작업에 포함하지 않는다. 기존 후보 계산 기능은 남아 있지만 운영에서는 `--fill-missing`을 사용하지 않는다.

1. **후속 완료**: 격리 MySQL 8.0.46에서 V1~V10 SQL 순차 적용·인덱스·rollback을 확인했다. [실제 MySQL 검증 보고서](region-mysql-v10-validation-2026-09-04.md). 운영 데이터 복제/Flyway 앱 기동 검증과는 구분한다.
2. 배치 코드 사용자 검토, main push/배포 및 운영 apply 승인. 기존 요청에 따라 별도 승인 없이 배치 main을 push하지 않는다.
3. 전체 대상 분할 dry-run 및 호출 예산 확인. v2는 v1 체크포인트를 재사용하지 않아 재분석 호출이 필요하다.
4. 50m 기준의 실제 예외 관찰. 산·대형 부지의 대표점 차이는 오류로 단정하지 않는다.
5. 이력/JSONL 보관 기간, 해결된 건 보관/파기 정책, 저장 공간 관측 확정. 임의 자동 삭제는 구현하지 않았다.
6. 관리자 목록·상세·검토 상태·처리자/메모·접근 권한·감사 이벤트 구현은 추후 작업이다. 이번에는 저장 기반과 연결 계약만 구축했다.

현재 운영 DB에 이력 테이블/근거가 생성되었다는 의미는 아니다. **dry-run 결과는 JSONL에만 남고, 새 DB 이력은 migration 후 승인된 apply에서 저장된다.**
