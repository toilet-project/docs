### `toilet` 테이블 명세서 (v1.1)

| 컬럼명 | 데이터 타입 | Null 허용 | 기본값 | 설명 |
| :--- | :--- | :---: | :---: | :--- |
| **`toilet_id`** | `BIGINT` | **PK** | `AUTO_INCREMENT` | 식별자 (기본키) |
| **`mng_no`** | `VARCHAR(50)` | YES | `NULL` | 공공데이터 관리번호. 배치 적재 시 기존 데이터 식별 및 upsert 기준으로 사용 |
| **`name`** | `VARCHAR(100)` | YES | `NULL` | 화장실명 |
| **`toilet_type`** | `VARCHAR(20)` | YES | `NULL` | 구분명 (개방/공중/간이화장실 등) |
| **`road_address`** | `VARCHAR(255)` | YES | `NULL` | 소재지도로명주소 |
| **`jibun_address`** | `VARCHAR(255)` | YES | `NULL` | 소재지지번주소 |
| **`latitude`** | `DECIMAL(10, 7)` | YES | `NULL` | 위도 |
| **`longitude`** | `DECIMAL(10, 7)` | YES | `NULL` | 경도 |
| **`coordinate_source`** | `VARCHAR(30)` | NO | `'LEGACY'` | 최종 좌표의 출처·상태. `GEOCODED_ROAD`, `GEOCODED_JIBUN`, `GEOCODE_FAILED`, `GEOCODED_LEGACY`, `ADMIN_CONFIRMED`, `LEGACY` 중 하나 |
| **`geocoded_address_hash`** | `CHAR(64)` | YES | `NULL` | 마지막 자동 지오코딩에 사용한 주소의 SHA-256 해시. 주소 변경 여부 판별에 사용 |
| **`geocoded_at`** | `DATETIME` | YES | `NULL` | 자동 지오코딩 처리 시각. 과거 적재 데이터처럼 정확한 시각을 알 수 없는 경우 비움 |
| **`male_toilet_count`** | `INT` | NO | `0` | 남성용-대변기수 |
| **`male_urinal_count`** | `INT` | NO | `0` | 남성용-소변기수 |
| **`male_disabled_toilet_count`** | `INT` | NO | `0` | 남성용-장애인용대변기수 |
| **`male_disabled_urinal_count`** | `INT` | NO | `0` | 남성용-장애인용소변기수 |
| **`male_child_toilet_count`** | `INT` | NO | `0` | 남성용-어린이용대변기수 |
| **`male_child_urinal_count`** | `INT` | NO | `0` | 남성용-어린이용소변기수 |
| **`female_toilet_count`** | `INT` | NO | `0` | 여성용-대변기수 |
| **`female_disabled_toilet_count`** | `INT` | NO | `0` | 여성용-장애인용대변기수 |
| **`female_child_toilet_count`** | `INT` | NO | `0` | 여성용-어린이용대변기수 |
| **`agency_name`** | `VARCHAR(100)` | YES | `NULL` | 관리기관명 |
| **`phone_number`** | `VARCHAR(20)` | YES | `NULL` | 전화번호 |
| **`open_time`** | `VARCHAR(50)` | YES | `NULL` | 개방시간 |
| **`open_time_detail`** | `VARCHAR(255)` | YES | `NULL` | 개방시간상세 |
| **`installation_date`** | `VARCHAR(20)` | YES | `NULL` | 설치연월 |
| **`ownership_type`** | `VARCHAR(50)` | YES | `NULL` | 화장실소유구분 |
| **`has_emergency_bell`** | `VARCHAR(10)` | YES | `NULL` | 비상벨설치여부 |
| **`emergency_bell_location`** | `VARCHAR(100)` | YES | `NULL` | 비상벨설치장소 |
| **`has_cctv`** | `VARCHAR(10)` | YES | `NULL` | 화장실입구CCTV설치여부 |
| **`has_diaper_table`** | `VARCHAR(10)` | YES | `NULL` | 기저귀교환대설치여부 |
| **`diaper_table_location`** | `VARCHAR(100)` | YES | `NULL` | 기저귀교환대장소 |
| **`data_base_date`** | `VARCHAR(20)` | YES | `NULL` | 데이터기준일자 |
| **`data_source`** | `VARCHAR(20)` | NO | `'PUBLIC_DATA'` | 데이터 출처 |
| **`created_at`** | `DATETIME` | NO | `CURRENT_TIMESTAMP` | 내 DB 등록일시 |
| **`updated_at`** | `DATETIME` | NO | `CURRENT_TIMESTAMP` | 내 DB 수정일시 (`ON UPDATE`) |

### 인덱스

| 인덱스명 | 컬럼 | 유형 | 용도 |
| :--- | :--- | :--- | :--- |
| `PRIMARY` | `toilet_id` | Primary Key | 내부 식별자 조회 |
| `idx_toilet_mng_no` | `mng_no` | Non-unique BTREE | 공공데이터 관리번호 기반 조회 및 배치 적재 시 기존 데이터 탐색 |

### 좌표 관리 정책

- 지도에 사용하는 최종 위치는 `latitude`, `longitude`다.
- 배치는 공공데이터 API가 직접 좌표를 제공하지 않으므로, 도로명 주소를 우선하고 실패 시 지번 주소로 카카오 지오코딩을 시도한다.
- 최근 3일 갱신분 중 신규·주소 변경·좌표 미보유·과거 지오코딩 실패 데이터만 다시 지오코딩한다. 기존 전체 데이터는 매일 재처리하지 않는다.
- `ADMIN_CONFIRMED`는 향후 관리자 검증 또는 사용자 제보 승인으로 확정한 좌표다. 배치는 이 상태의 좌표를 덮어쓰지 않는다.
- `GEOCODED_LEGACY`는 기존 어드민 적재 과정에서 생성된 카카오 지오코딩 좌표다. 정확한 처리 시각을 알 수 없어 `geocoded_at`은 비어 있을 수 있다.

### 변경 이력

| 버전 | 일자 | 변경 내용 |
| --- | --- | --- |
| v1.1 | 2026-08-26 | 증분 지오코딩과 관리자 확정 좌표 보호를 위한 좌표 메타데이터 3개 컬럼 및 정책 추가 |
| v1.0 | 2026-08-22 | 공중화장실 기본 테이블·인덱스 명세 작성 |
