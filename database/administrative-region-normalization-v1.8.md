# 화장실 행정구역 정규화 v1.8 — 구현·배포 검토안

작성일: 2026-09-04 · 운영 V8 적용: 2026-09-05. 최신 배포·적재 상태는 [운영 반영 보고서](../operations/region-production-result-2026-09-05.md)를 따른다. 아래 현황 수치는 최초 분석 시점의 기록이다.

- WBS: [toilet-batch #35](https://github.com/toilet-project/toilet-batch/issues/35)
- 범위: DB·백엔드 행정구역 파생 데이터. React/Next.js, SEO 페이지, 공개 라우트, 지도 UX는 변경하지 않는다.
- 원칙: 기존 도로명·지번주소와 기존 좌표 보존. 코드 검토와 운영 적용 승인 전에는 분석만 수행한다.

## 1. 운영 데이터와 기존 쓰기 경로

2026-09-04 운영 DB를 읽기 전용으로 조회한 결과다. 역지오코딩 전의 현황이며 정확도 결과가 아니다.

| 항목 | 건수/구조 |
|---|---|
| 화장실 전체 | 53,576 |
| 좌표 둘 다 없음 | 1,288 |
| 좌표 한쪽만 없음 | 0 |
| 기존 좌표 있는 건 | 52,288 |
| 서로 다른 기존 좌표쌍 | 42,642 |
| 도로명주소 없음 | 5,384 |
| 지번주소 없음 | 14,670 |
| 0 또는 지구상 좌표 범위 초과 | 0 — 국내 위치 정확성을 의미하지 않음 |

`toilet_id BIGINT`가 PK이며 `mng_no VARCHAR(50)`는 **비유일** 인덱스다. 주소는 `VARCHAR(255)`, 위·경도는 `DECIMAL(10,7)`이다. 시설 수는 INT이고, 운영시간·편의시설 여부 등은 VARCHAR다. 행정구역 컬럼은 없었다. `created_at`, `updated_at`은 DATETIME이며 애플리케이션 시간 기준은 KST다. Flyway V1~V7이 운영에 적용되어 있다.

좌표 출처는 GEOCODED_LEGACY 52,213 / LEGACY 1,287 / ADMIN_CONFIRMED 36 / GEOCODED_ROAD 38 / GEOCODE_FAILED 1 / GEOCODED_JIBUN 1이다.

### 기존 서비스

- **배치** `KakaoAddressGeocodingClient`: 기존 Kakao 주소 검색 API로 좌표 생성. `IncrementalGeocodingService`가 도로명→지번 fallback 후 `ToiletSyncWriter`로 공공데이터를 upsert한다.
- **사용자 API** `ToiletReportService.approve`, `CoordinateQualityService.correctToilet`: 관리자 확인 좌표·주소를 `Toilet.applyAdminConfirmedCoordinates`로 반영하고 수정 이력을 기록한다.
- **관리자 서버** `GeocodingService`: 도로명 원문/괄호 정리→지번 원문/괄호 정리 순으로 같은 Kakao 주소 검색 API를 사용한다. 현재 관리자 서비스 코드에서 이 서비스의 호출자는 발견하지 못했다.
- 기존 배치의 주소 문자열 변경 시 자동 재지오코딩은 수정했다. 이미 좌표가 있으면 주소 오타만으로 이동하지 않는다. 실제 이전은 후보 좌표 확인→관리자 확정이라는 기존 흐름으로 처리한다.
- 배치 메타데이터 조회 뒤 관리자 보정이 일어나는 경합도 보호한다. 기존 행의 좌표는 공공데이터 UPDATE에서 제외하고 **둘 다 NULL인 행만** 별도 조건부 UPDATE로 채운다. 부분 좌표나 관리자 확정 상태는 자동 덮어쓰지 않는다.

## 2. 역지오코딩과 코드 체계

기존 `KAKAO_REST_API_KEY`를 재사용한다. 새 외부 사업자나 지도 라이브러리를 추가하지 않는다.

`GET https://dapi.kakao.com/v2/local/geo/coord2regioncode.json?x={경도}&y={위도}&input_coord=WGS84`

- **B(법정동) 문서의 10자리 코드**를 정규화 코드 기준으로 사용한다. 시도 앞 2자리, 시군구 앞 5자리를 별도 저장한다.
- H(행정동) 코드는 별도 보관한다. B와 H를 한 코드 칸에 섞지 않는다. 문서가 여러 개이거나 코드 형식이 이상하거나 상위 코드가 서로 다르면 실패·확인 대상으로 분류한다.
- 응답의 x/y는 행정구역 대표 좌표다. **요청 화장실 좌표 대신 저장하지 않는다.**
- 주소 반환 API `coord2address`에는 필요한 행정구역 코드가 없으므로, 행정구역 판정에는 `coord2regioncode`를 사용한다.
- 코드 형태·상위 코드 일관성은 검증하지만, 전국 최신 코드마스터를 내려받아 독립 대조하는 기능은 이번에 추가하지 않는다. 공급자 오류·경계 변경 가능성은 남아 있다.

출처: [Kakao REST API](https://developers.kakao.com/docs/ko/kakaomap/rest-api), [행정표준코드관리시스템](https://www.code.go.kr/stdcode/regCodeL.do).

## 3. 계층 설계 — 원본과 분리된 1:1 파생 테이블

`toilet_region.toilet_id`를 PK/FK로 사용한다. 지역 master나 slug 테이블은 만들지 않는다. 지금 필요한 것은 화장실별 안정적인 지역 필터이며, 코드마스터 수집·명칭 변경·slug 중복/이전까지 운영할 필요는 아직 없다.

다만 두 개의 이름만 저장하면 천안시 전체를 조회하기 불편하다. API의 **구조화된 region_2depth_name**에 `천안시 서북구`가 들어오는 경우에 한해 `city_name=천안시`, `district_name=서북구`를 함께 저장한다. 원본 주소를 쪼개 지역을 결정하는 방식이 아니다.

| 예 | sido_name | sigungu_name | 추가 계층 |
|---|---|---|---|
| 서울 → 강남 | 서울특별시 | 강남구 | 없음 |
| 대전 → 유성 | 대전광역시 | 유성구 | 없음 |
| 충남 → 공주 | 충청남도 | 공주시 | 없음 |
| 전남 → 함평 | 전라남도 | 함평군 | 없음 |
| 충남 → 천안 → 서북 | 충청남도 | 천안시 서북구 | city=천안시 / district=서북구 |
| 경기 → 수원 → 영통 | 경기도 | 수원시 영통구 | city=수원시 / district=영통구 |
| 세종 | 세종특별자치시 | API가 빈 값이면 NULL | 제공 코드 앞 5자리는 보존, 가상의 시군구명을 만들지 않음 |

시→구 구조의 부모 시 코드는 응답에 별도로 없으므로 계산으로 만들어내지 않는다. 향후 부모 도시의 코드 기반 URL까지 요구되면 그때 공식 코드마스터와 연결한다. 이번에는 시도 코드+city_name으로 도시 전체를 조회한다.

### 컬럼 사전

| 컬럼 | 타입 | 한글 속성·의미 |
|---|---|---|
| toilet_id | BIGINT PK/FK | 화장실 식별자 |
| sido_name / sido_code | VARCHAR(50) / CHAR(2) | 시·도 이름 / 법정코드 상위 2자리 |
| sigungu_name / sigungu_code | VARCHAR(100) / CHAR(5) | 시·군·구 전체 이름 / 상위 5자리 |
| city_name / district_name | VARCHAR(50) / VARCHAR(50) | 시→구 구조의 도시·구 이름, 해당할 때만 |
| legal_dong_code | CHAR(10) | 원본 법정동 코드 |
| administrative_dong_code | CHAR(10) | 원본 행정동 코드, 있을 때만 |
| region_source | VARCHAR(40) | KAKAO_COORD2REGIONCODE_B |
| status / reason | VARCHAR(30) / VARCHAR(100) | 판정 상태 / 기계 판독 가능한 사유 코드 |
| source_hash | CHAR(64) | 알고리즘 버전·원본 주소·좌표 fingerprint |
| source_latitude / source_longitude | DECIMAL(10,7) | 판정 당시 원본 좌표 |
| source_road_address / source_jibun_address | VARCHAR(255) | 판정 당시 주소 스냅샷 |
| evaluated_latitude / evaluated_longitude | DECIMAL(10,7) | 실제 역지오코딩에 사용한 좌표(없던 좌표의 후보 포함) |
| result_json | JSON | 화장실 ID, 원본, 판정, 도로명·지번 각각의 비교 결과, fallback, 버전·시각 |
| checked_at | DATETIME | 판정 시각 KST |

`toilet`에 새 컬럼을 추가하지 않는다. API V8 migration이 `toilet_region`과 `current_toilet_region` view를 생성한다.

검토용 전체 DDL은 [v1.8-toilet-region.sql](ddl/v1.8-toilet-region.sql)로 분리했다. 실행 소스는 API 저장소의 Flyway `V8__create_toilet_region.sql`이며 두 파일은 같은 내용이다. 운영에 둘 다 실행하지 않는다.

### 판정 상태

- VERIFIED: 역지오코딩 성공, 비교 가능한 주소 중 최소 하나 일치, 다른 주소에 명백한 충돌 없음.
- MISMATCH: 도로명 또는 지번 중 하나라도 지역 충돌. 결과는 후보로 보관하고 정상 조회에서 제외.
- ADDRESS_UNVERIFIED: 코드는 받았지만 두 주소 모두 불충분해 비교하지 못함.
- NO_COORDINATE: 좌표 없음 + 사용 가능한 유일한 주소 검색 결과 없음(다중 후보 포함).
- INVALID_COORDINATE: 부분 좌표·범위 밖·0 좌표. 원본 보존.
- REVERSE_FAILED: 역지오코딩 실패 또는 주소 지오코딩의 일시적 공급자 실패. reason으로 세부 구분.

지역 일치는 좌표의 정밀한 정확성 보장이 아니다. 같은 구 안에서 수백 미터 잘못된 좌표까지 이 검증으로 찾아낼 수는 없다.

## 4. 원본 보존과 좌표 없는 데이터

기존 좌표는 재생성하거나 덮어쓰지 않는다. 도로명·지번주소는 정규화 실행기에서 UPDATE하지 않는다.

좌표가 둘 다 없으면:

1. 원래 도로명주소로 기존 주소 검색 클라이언트의 `geocodeUnique`를 호출한다.
2. 결과가 없거나 단일 후보가 아니거나 해당 요청이 실패하면 지번주소를 시도한다. 인증·쿼터 오류는 전체 실행을 멈춘다.
3. 유일한 후보 좌표를 DB 정밀도 7자리로 맞추고 역지오코딩한다.
4. dry-run 또는 일반 `--apply`는 후보만 기록한다.
5. 별도 승인 후 `--apply --fill-missing`일 때만 **VERIFIED + 현재도 좌표 둘 다 NULL**인 행에 좌표를 저장한다. source는 GEOCODED_ROAD/JIBUN으로 기록한다.
6. 원본이 조회 이후 바뀌면 행 잠금 아래 fingerprint를 재확인해 적용을 거절한다. 다음 회차에서 새 원본으로 처리한다.

부분 좌표는 남아 있는 정보를 파괴하지 않도록 수동 검토한다. 주소 검색 다중 후보에서 임의의 첫 결과를 택하지 않는다.

## 5. 지속적 갱신과 조회 안전성

위치 승인·직접 수정·공공데이터 등록 이후 공통 `RegionReconciliationScheduler`가 변경을 감지한다. HTTP API를 새로 개방하지 않는다.

- 기본 비활성화. V8/검토 완료 후 `BATCH_REGION_ENABLED=true`로 활성화한다.
- 기본 5분 간격으로 PK keyset 100개씩 읽으며, 원본 fingerprint가 같은 결과는 건너뛴다. 쿼리는 LEFT JOIN으로 묶어 N+1 조회를 피한다.
- 실제 좌표가 바뀌면 다음 회차에 새 좌표로 역지오코딩한다. 승인 트랜잭션 안에서 외부 API를 기다리지 않는다.
- 원본 주소만 바뀌면 기존 좌표로 재비교한다. 동일 좌표 캐시가 유효하면 역지오코딩 재호출도 없다. 원본 좌표를 이동시키지 않는다.
- 별도 스케줄러 스레드를 사용해 정상화 작업이 매일 02:00 증분 배치를 가로막지 않게 한다.
- 정상/검토 결과 및 좌표 캐시는 30일 후 재확인 대상, 일시 실패는 24시간 후 재시도 대상이다. 이 기간에도 수동 검토 결과를 정상으로 간주하지 않는다.
- 작업량·쿼터에 따라 갱신은 다음 회차 이후로 지연될 수 있다. 즉시 완료를 보장하는 동기 방식은 아니다.

미래 조회는 **`current_toilet_region`**을 사용한다. 이 view는 VERIFIED이고 판정 당시 주소·좌표가 현재 원본과 같으며, 평가 좌표까지 같을 때만 노출한다. 위치가 바뀐 순간부터 이전 지역 결과는 제외되므로 새 판정 전까지 잘못된 지역에 계속 노출되지 않는다. 후보만 저장된 좌표 없는 건도 제외된다.

## 6. 조회와 인덱스

요청된 세 패턴을 기준으로 설계했다. 공개 지역 페이지나 조회 API는 만들지 않는다.

```sql
-- 시도 전체 / 시군구 / 시→구 중 도시 전체. 마지막 ID 조건은 다음 페이지용.
SELECT toilet_id FROM current_toilet_region
WHERE sido_code='30' AND toilet_id > 0 ORDER BY toilet_id LIMIT 50;
SELECT toilet_id FROM current_toilet_region
WHERE sigungu_code='30200' AND toilet_id > 0 ORDER BY toilet_id LIMIT 50;
SELECT toilet_id FROM current_toilet_region
WHERE sido_code='44' AND city_name='천안시' AND toilet_id > 0 ORDER BY toilet_id LIMIT 50;
```

- `idx_toilet_region_sido(sido_code,status,toilet_id)`
- `idx_toilet_region_sigungu(sigungu_code,status,toilet_id)`
- `idx_toilet_region_city(sido_code,city_name,status,toilet_id)`

별도 MySQL 8.0에서 앞의 두 패턴은 해당 인덱스, 원본 조인은 PK eq_ref 사용을 확인했다. 3건 테스트 데이터에서는 도시 조회에 시도 인덱스를 선택했다. 실제 데이터 적재 후 `EXPLAIN ANALYZE`로 분포와 지연을 재확인해야 한다. 작은 fixture로 운영 성능을 확정하지 않는다.

## 7. 실행·resume·API 제한

`RegionNormalizationCli`는 Spring 컨텍스트를 시작하지 않는다. 서버·Hibernate·SQL 초기화·일일 배치가 같이 실행되지 않는다. 인자가 없으면 dry-run이며 DDL/DML 경로를 호출하지 않는다.

환경변수:

| 이름 | 기본/요건 |
|---|---|
| SPRING_DB_URL / USERNAME / PASSWORD | 기존 DB 연결, 비밀값은 저장소/명령 인자에 쓰지 않음 |
| KAKAO_REST_API_KEY | 기존 Kakao 키 |
| REGION_JOURNAL_PATH | 필수. 영속 볼륨의 단일 JSONL 경로 |
| REGION_MAX_ITEMS | 100건/회 |
| REGION_DAILY_CALL_BUDGET | 1,000회/일. 이 작업 전용 보수적 상한, 앱 전체 잔여량이 아님 |
| REGION_DELAY_MS | 1,000ms. 최소 200ms 허용 |
| REGION_SAMPLE_IDS | dry-run 표본 한정, 양의 ID 최대 100개. 운영 자동 작업에는 사용하지 않음 |

```sh
# 이미 환경변수가 안전하게 주입된 환경에서 실행
./gradlew regionNormalize
# 또는 bootJar를 별도 main으로 실행: 일반 애플리케이션이 시작되지 않음
java -Dloader.main=com.example.toiletbatch.region.RegionNormalizationCli \
  -cp toilet-batch-0.0.1-SNAPSHOT.jar org.springframework.boot.loader.launch.PropertiesLauncher
# 검토·승인한 뒤에만 같은 명령 끝에 --apply 또는 --apply --fill-missing 추가
```

- 단일 호출 경로에서 순차 처리, 연결 5초/응답 10초 timeout.
- 네트워크 오류·5xx는 최대 3회, 1초→2초 지수 backoff+작은 jitter. 재시도도 호출 예산에 포함.
- 401/403은 인증/권한 확인을 위해 즉시 중단. 429는 일일 쿼터 소진일 수도 있으므로 즉시 중단하고 쿼터 확인 후 resume. 무한 재시도하지 않는다.
- JSONL 파일 잠금으로 같은 journal 동시 실행 방지. apply는 MySQL GET_LOCK도 사용한다.
- 호출 전 journal에 예산 예약을 fsync한다. 장애 시 과다계산은 가능하지만 호출량을 과소계산하지 않는다.
- 성공한 역지오코딩은 정확히 같은 좌표쌍으로 캐시한다. 인접 좌표를 반올림해 합치지 않는다.
- 결과를 화장실 ID·fingerprint별로 남긴다. 재시작해도 완료 항목은 건너뛰며, 이미 지나간 ID의 위치가 바뀐 것도 재발견한다. 마지막 ID 하나만 기록하고 앞쪽 변경을 놓치는 구조가 아니다.
- DB commit 전에 journal 체크포인트를 남긴다. commit 전/후 어느 때 중단돼도 DB 상태를 다시 비교해 재적용할 수 있다.
- 마지막 줄이 쓰이다 끊긴 경우 그 미완성 줄만 버리고 복구한다. 중간 줄의 손상은 중단하고 보고한다.
- journal에는 공중화장실 원본 주소/좌표가 들어간다. git 제외, 권한 제한, 비공개 백업 필요. 실행 중 삭제/초기화/임의 경로 변경은 호출 예산과 체크포인트를 초기화하므로 금지한다.

공식 문서상 좌표→행정구역과 주소→좌표는 각각 일 100,000건의 무료 쿼터가 표시된다. **카카오맵 최초 활성화 앱 등 조건이 있으며 실제 앱 쿼터 확인이 필요하다.** 추가 쿼터 적용 시 두 API는 각 0.5원/건으로 안내된다. 유료 설정을 추가/변경하지 않는다. [Kakao 쿼터·요금](https://developers.kakao.com/docs/ko/getting-started/quota)

기존 고유 좌표 42,642개를 초당 1건으로 처음 처리하면 외부 호출 간격만 약 11.8시간이다. 추가 지오코딩·재시도·처리 시간은 별도이며, 일 예산 1,000이면 한 날에 전수 처리되지 않는다. 실제 앱 잔여 쿼터 확인 후 분할 실행 계획을 정해야 한다.

## 8. 배포·migration·rollback 순서

1. feature 코드와 이번 보고서 검토. batch main push는 사용자 승인 후.
2. 기존 DB 백업 및 복구 가용성 확인. 자동 DDL 실행은 아직 하지 않았다.
3. API V8 additive migration 배포: 새 테이블/view만 생성. 기존 주소·좌표·원본 건수 불변 확인.
4. 제한된 dry-run → 결과/쿼터 확인 → 승인한 분량만 `--apply`.
5. 좌표 없는 검증 성공 후보는 별도로 검토한 뒤 `--fill-missing`을 명시한 실행으로만 채운다.
6. 시도/시군구 분포·현재 view·수동 검토 목록·실제 조회 계획 확인.
7. 배치 기능 배포 후 영속 journal 볼륨과 환경변수 검증, 마지막에 자동 작업 활성화.

가장 안전한 앱 rollback은 worker 비활성화 + 이전 앱 버전 복귀다. additive 테이블은 남겨도 기존 앱과 호환된다. 운영에서 Flyway history를 지우거나 V8을 편집하지 않는다. 구조 제거가 필요하면 백업 후 **새 forward migration**으로 view→table 순으로 제거한다.

`--fill-missing`으로 채운 좌표는 파생 테이블 삭제만으로 돌아가지 않는다. 원본 NULL snapshot과 후보를 journal에서 대조하고, 그 이후 사용자/관리자 수정이 없는 행만 개별 검토해야 한다. 자동 일괄 좌표 rollback은 제공하지 않는다.

별도 테스트 DB에서 [migration/rollback 검증 SQL](tests/region-v1.8-mysql.sql)을 실행해 파생 테이블을 제거한 후 원본 3건이 남는 것을 확인했다.

## 9. 실패·불일치 확인

```sql
SELECT status, reason, COUNT(*) FROM toilet_region GROUP BY status, reason;
SELECT r.toilet_id, t.name, r.status, r.reason,
       r.source_road_address, r.source_jibun_address,
       r.source_latitude, r.source_longitude, r.evaluated_latitude, r.evaluated_longitude,
       r.sido_name, r.sigungu_name, r.result_json
FROM toilet_region r JOIN toilet t ON t.toilet_id=r.toilet_id
WHERE r.status <> 'VERIFIED' ORDER BY r.toilet_id;
```

dry-run은 DB에 이 테이블이 없어도 실행 가능하며, JSONL의 `kind=result`에 동일한 상세 결과를 남긴다. 정상화된 지역만 보고 원래 주소가 변경됐다고 오해하지 않도록 source와 evaluated를 구분한다. 실행 보고서의 counts는 **이번에 처리한 건** 기준이고 `checkpointSkipped`는 재개 때 건너뛴 건이다. 전체 결과 집계는 journal 최신 ID별 결과 또는 DB에서 별도로 확인한다.

## 10. 검증 결과 및 남은 작업

현재 검증 결과·운영 표본 수치는 [실행 결과 보고서](../operations/region-normalization-review-2026-09-04.md)에 기록한다. 운영 대량 처리 전까지 전체 역지오코딩 성공·불일치·실패 건수는 미측정이다. 이를 0건 또는 전체 성공으로 표기하지 않는다.

남은 위험: 원좌표 오류가 같은 시군구 안에 있을 경우 미검출, provider 최신성/행정경계 변경, 주소 약칭·구 명칭 생략으로 인한 수동 검토, 앱 공유 쿼터, 단일 journal의 크기 증가, 비활성 배포 상태의 자동 갱신 미작동, 변경량이 예산보다 많을 때의 처리 지연. 운영 성능·전체 분포 검증은 실제 승인된 대량 실행 이후에 확정한다.
