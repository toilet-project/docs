# 행정구역 정규화 구현·검증 보고서

> 공개 요약본입니다. 작성 당시의 수치·검증 단계를 보존합니다. 최신 배포 및 남은 검증은 [관리자 검토 배포 보고서](region-admin-review-release-2026-09-05.md)를 참고하세요. 전체 JSON·시설별 검토 원문·운영 접속정보는 공개하지 않습니다.

> 이 문서는 최초 구현 시점의 기록이다. 전수 결과와 사용자 확정된 좌표 누락 정책은 [2026-09-05 최종 보고서](region-full-final-review-2026-09-05.md)가 최신이다. 현재 운영 정책에서는 --fill-missing을 사용하지 않는다.

2026-09-04 · **운영 배포/대량 적용 전** · [설계서](../database/administrative-region-normalization-v1.8.md) · [WBS #35](https://github.com/toilet-project/toilet-batch/issues/35)

## 완료 범위와 미완료 범위

DB·백엔드 feature 구현, 자동 테스트, 격리된 실제 MySQL migration/rollback 검증을 수행했다. 운영 DB에는 새 테이블/좌표/주소를 적용하지 않았고 main push·배포도 하지 않았다. 프론트엔드·SEO·지도 UI는 변경하지 않았다.

사용자 승인 후 카카오 API로 **84건의 운영 표본 dry-run**을 수행했다. 69건 역지오코딩 성공, 주소 일치 67건, 불일치 1건, 주소 검증 불충분 1건, 좌표 없는 미확정 15건이었다. [표본 상세 결과·전체 검토 목록](region-normalization-sample-2026-09-04.md)에 기록했다. 운영 전수 처리는 아직 하지 않았으므로 아래 전체 미측정을 0건으로 해석하면 안 된다.

## 요청 항목별 보고

### 1. 기존 DB 구조

`toilet` PK는 toilet_id BIGINT, mng_no는 비유일 VARCHAR(50) 인덱스다. 주소는 VARCHAR(255), 위경도는 DECIMAL(10,7), 시설 수는 INT다. 원본 좌표 출처·주소 hash·지오코딩 시각이 있다. 별도 행정구역은 없다. 운영 Flyway는 V7까지 적용되어 있다.

### 2. 기존 지오코딩

배치에서 Kakao 주소 검색→도로명/지번 fallback→upsert를 수행한다. API의 제보 승인·관리자 보정은 ADMIN_CONFIRMED 좌표와 수정 이력을 관리한다. 관리자 서버에도 주소 검색 서비스가 있으나 현재 호출자는 검색에서 발견되지 않았다. 상세 경로는 설계서 1절에 정리했다.

### 3. 사용한 역지오코딩

기존 Kakao `coord2regioncode`의 B 법정동 문서가 기준이며 H 행정동 코드는 별도로 보관한다. 지역 대표 좌표를 화장실 좌표로 덮어쓰지 않는다. 자동 테스트에 더해 운영 표본에서 실제 Kakao 응답을 확인했다.

### 4~5. 최종 설계와 이유

원본과 분리된 1:1 `toilet_region` 및 최신 좌표와 일치하는 결과만 노출하는 `current_toilet_region` view다. 시도·시군구 코드와 이름을 저장하고, 도→시→구는 city_name/district_name을 추가 보관한다. 부모 시 코드를 추측하거나 지역 master/slug를 미리 구축하지 않는다.

### 6. 추가 DB 구조

API `V8__create_toilet_region.sql`: 테이블 1개, view 1개. 원본 toilet 컬럼 추가/삭제 없음. 컬럼별 한글 사전 및 [분리 DDL](../database/ddl/v1.8-toilet-region.sql)을 제공한다.

### 7. 인덱스

시도·시군구·도시별 keyset 조회를 위한 복합 인덱스 3개. 별도 MySQL에서 시도·시군구 인덱스 사용과 원본 PK 조인을 확인했다. 도시 조회의 운영 분포별 최적 인덱스 선택은 대량 적재 후 재검증해야 한다.

### 8. Migration 방식

V8 additive DDL → dry-run 결과 검토 → 제한 apply → 좌표 없는 검증 성공 후보에 한해 별도 `--fill-missing` → 자동 reconciler 활성화 순서다. 기본 실행은 DB 쓰기가 없다. 파일 체크포인트와 DB fingerprint를 모두 확인해 재개한다. 원본 NULL 좌표를 채우는 작업의 rollback은 자동 일괄 삭제가 아니라 이후 보정 여부를 확인한 개별 복구 대상이다.

### 9~15. 실제 데이터 수치

| 보고 항목 | 결과 |
|---|---|
| 전체 대상 | **53,576건**, 운영 DB 읽기 전용 실측 |
| 기존 좌표 있음 | 52,288건 |
| 기존 고유 좌표쌍 | 42,642개 |
| 역지오코딩 성공 | **운영 미측정** |
| 주소·좌표 지역 일치 | **운영 미측정** |
| 불일치 | **운영 미측정** |
| 역지오코딩/지오코딩 실패 | **운영 미측정** |
| 기존 좌표 없음 | 1,288건, 모두 위경도 둘 다 NULL |
| fallback 성공/실패 | **운영 미측정**, 테스트에서 분기 검증 |
| 최종 수동 확인 대상 | **운영 미측정** |
| 운영 UPDATE 건수 | **0건 — 적용하지 않음** |

사용자가 승인한 표본 상한은 100건이며 84건을 처리했다. 이는 편의 표본이며 전체 정확도 추정용 통계표본이 아니다. 전체 수치와 별도로 표본은 역지오코딩 성공 69, 지역 일치 67, 불일치 1, 주소 비교 불충분 1, 좌표 없음+유일 후보 없음 15, HTTP/역지오코딩 실패 0, 총 검토 대상 17건이다. 실제 API 호출은 86회였고 재실행은 84건을 건너뛰어 추가 호출이 없었다.

### 16. 위치 수정 시 자동 갱신

공통 RegionNormalizer를 초기 이관과 지속적 reconciliation이 재사용한다. 좌표가 달라지면 다음 회차에 역지오코딩하며, 원본이 처리 중 바뀌면 행 잠금 아래 재확인해 낡은 결과 적용을 거절한다. view가 즉시 이전 지역을 숨긴다. 주소 오타만으로 좌표를 재생성하지 않는다. 현재 자동 worker는 기본 비활성화이며 운영에 배포되지 않았다.

### 17. API 제한·재시도

기본 초당 1회·일 1,000회 예산·100건/회. 네트워크·5xx 최대 3회 backoff, 401/403/429 중단, 일시 실패 항목은 다음 날 재처리. 호출 예약과 성공 캐시/결과를 영속 JSONL에 저장한다. 운영 앱의 잔여 무료 쿼터를 아직 확인하지 않았으며 유료 설정은 변경하지 않았다.

### 18. 변경 파일

모두 `feature/administrative-region-normalization`에서 작업했다. 원격 push/merge는 하지 않았다. 기존 docs `.idea/` 미추적 파일은 건드리지 않았다.

**toilet-api**

- `src/main/resources/db/migration/V8__create_toilet_region.sql`

**toilet-batch**

- `src/main/java/com/example/toiletbatch/region/RegionModel.java`
- `src/main/java/com/example/toiletbatch/region/RegionProvider.java`
- `src/main/java/com/example/toiletbatch/region/AddressRegionCheck.java`
- `src/main/java/com/example/toiletbatch/region/RegionNormalizer.java`
- `src/main/java/com/example/toiletbatch/region/KakaoRegionProvider.java`
- `src/main/java/com/example/toiletbatch/region/RegionJournal.java`
- `src/main/java/com/example/toiletbatch/region/RegionRepository.java`
- `src/main/java/com/example/toiletbatch/region/RegionJob.java`
- `src/main/java/com/example/toiletbatch/region/RegionNormalizationCli.java`
- `src/main/java/com/example/toiletbatch/region/RegionReconciliationScheduler.java`
- `src/main/java/com/example/toiletbatch/geocoding/KakaoAddressGeocodingClient.java`
- `src/main/java/com/example/toiletbatch/batch/IncrementalGeocodingService.java`
- `src/main/java/com/example/toiletbatch/batch/ToiletSyncWriter.java`
- `src/test/java/com/example/toiletbatch/region/{RegionNormalizerTest,RegionJournalTest,RegionRepositoryTest,RegionJobTest,KakaoRegionProviderTest,KakaoRegionHttpTest}.java`
- `src/test/java/com/example/toiletbatch/batch/{IncrementalGeocodingServiceTest,ToiletSyncWriterTest}.java`
- `.github/workflows/deploy.yml`（기본 OFF, 영속 journal 볼륨·호출 예산 환경변수）
- `.gitignore`, `build.gradle`

**docs**

- `database/administrative-region-normalization-v1.8.md`
- `database/ddl/v1.8-toilet-region.sql`
- `database/tests/region-v1.8-mysql.sql`
- `operations/region-normalization-review-2026-09-04.md`
- `operations/region-normalization-sample-2026-09-04.md`
- `README.md`, `changelog/CHANGELOG.md`

### 19. 실제 실행한 테스트

- batch: `gradlew test bootJar --no-daemon` — **52 tests, 실패 0, skip 0**, jar 빌드 성공.
- API: `gradlew test --no-daemon` — **55 tests 중 51 통과, 4 skip, 실패 0**. 로컬 Docker가 없어 기존 Docker 의존 테스트는 실행되지 않았다.
- 미니 PC의 별도 MySQL 8.0 컨테이너: 네트워크 none, 독립 익명 볼륨, CPU 1·메모리 512MiB 제한. V8 DDL, 특수 구조 NULL 처리, 현재 view의 좌표/주소 변경 감지, 상태 필터, EXPLAIN, view/table 제거 후 원본 3건 보존을 확인했다. 운영 DB와 분리된 검증이다.
- `git diff --check` 확인. 저장소 LF/CRLF 경고는 있으나 공백 오류 없음.
- 승인된 운영 표본 dry-run 84건 및 checkpoint 재실행 완료. 종료 후 원본 주소·좌표 84건 재비교 결과 변경 0건.

| 사용자 요청 테스트 | 검증 |
|---|---|
| 정상 도로명+지번+좌표 | 일치 판정 및 원본 보존 |
| 도로명만 | 일치 판정 |
| 지번만 | 일치 판정 |
| 좌표 있고 일부 주소 누락 | 알려진 주소만 비교, 정보 부족은 UNKNOWN |
| 지역 일치 | VERIFIED |
| 지역 불일치 | MISMATCH, 정상 view 제외 |
| 좌표 없음+도로명 성공 | ROAD 후보, 원본 미수정 |
| 도로명 실패+지번 성공 | JIBUN 후보, 도로명 공급자 실패도 사유 보존 |
| 모두 처리 불가 | NO_COORDINATE / 실패 사유 명시 |
| 특별시·광역시 | 서울/대전 구조 |
| 도의 일반 시 | 공주시 |
| 도→시→구 | 천안시 서북구, 수원시 영통구 |
| 군 | 함평군 |
| 세종 | sigungu_name NULL 허용, 코드 보존 |

추가 검증: 범위 밖/부분 좌표 보존, 후보 다건 거부, B/H 충돌 거부, 오류 재시도·인증/쿼터 중단, 동일 좌표 캐시, daily budget 재시작 보존, journal 미완성 마지막 줄 복구, dry-run DB 무쓰기, source 변경 재처리, DB 동시 수정 충돌, 두 NULL 좌표만 명시적 채움, 관리자 보정의 배치 재덮어쓰기 방지.

### 20. 남은 위험·승인 사항

1. 운영 실 API 84건 표본은 검증했다. 전체 데이터 품질 수치는 여전히 미측정이며, 표본의 검토 대상 17건을 조용히 무시하지 않고 별도 목록으로 남겼다.
2. 카카오 앱 실제 무료 쿼터·다른 기능의 공유 사용량 확인이 필요하다. 일 100,000이라는 문서상 수치가 곧 현재 앱 잔여량은 아니다.
3. 같은 시군구 안의 잘못된 좌표는 주소 상위 지역 비교로 잡지 못한다.
4. 코드마스터 독립 대조와 공급자 행정경계 최신성은 별도 과제다. 알 수 없는 명칭은 임의 추측하지 않고 검토 대상으로 남긴다.
5. 자동 worker는 비활성 상태다. V8 배포·영속 볼륨·예산 검토 및 승인 없이는 운영 자동 갱신이 되지 않는다.
6. 원본 변경량이 호출 예산을 넘으면 처리 지연이 생긴다. 장기 journal 파일 크기/보관 정책과 실제 MySQL 조회 성능도 운영 관측이 필요하다.
7. 초기 전수 호출은 고유 좌표만으로 초당 1회에서 약 11.8시간 이상이다. 53,576건 전체의 성공률은 현재 주장할 수 없다.
