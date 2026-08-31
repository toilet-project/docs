# 사용자 제보·좌표·개방시간 승인 모델 v1.4

## 목적

로그인 사용자가 위치 오류 또는 개방 시간 오류를 제보하고 관리자가 승인한 값만 지도에 반영한다. 공공데이터·자동 지오코딩 결과와 관리자 확정 좌표는 서로 덮어쓰지 않는다.

## 선택한 구조

`toilet_report`는 사용자 요청과 처리 상태를, `coordinate_revision`은 실제 적용된 좌표 변경 이력을 담당한다. 반려·취소된 제보와 지도 반영 이력을 분리해 추적한다.

```text
app_user 1 ── N toilet_report N ── 1 toilet
                         │ 승인 시 1 ── 1 coordinate_revision
app_user (관리자) ────────┘
```

## 상태 전이

```text
PENDING ──관리자 승인──> APPROVED
   │  └─관리자 반려───> REJECTED
   └──작성자 취소────> CANCELLED
```

- `PENDING` 상태만 승인·반려·취소할 수 있다.
- 작성자는 자기 제보만 취소하고, 관리자는 승인·반려한다.
- 승인·반려된 제보는 수정하지 않는다. 새 내용은 새 제보로 남긴다.

## 테이블 설계

### `toilet_report`

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `report_id` | `BIGINT PK` | 제보 식별자 |
| `toilet_id` | `BIGINT FK` | 대상 화장실 |
| `reporter_user_id` | `BIGINT FK` | 제보 작성자 |
| `report_type` | `VARCHAR(30)` | `COORDINATE_CORRECTION`, `OPEN_TIME_CORRECTION` |
| `proposed_latitude`, `proposed_longitude` | `DECIMAL(10,7) NULL` | 위치 제보의 제안 좌표 |
| `proposed_road_address` | `VARCHAR(255) NULL` | 좌표에서 역지오코딩해 사용자에게 확인받은 도로명 주소 |
| `proposed_open_time` | `VARCHAR(50) NULL` | 개방 시간 제보값 |
| `reason` | `VARCHAR(500)` | 제보 사유 |
| `status` | `VARCHAR(20)` | `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED` |
| `active_request_key` | `CHAR(64) NULL UNIQUE` | 진행 중 중복 제보 방지 키 |
| `reviewed_by_user_id`, `reviewed_at`, `review_note` | `BIGINT FK`, `DATETIME`, `VARCHAR(500)` | 관리자 처리 정보 |
| `created_at`, `updated_at` | `DATETIME` | 생성·갱신 시각 |

`active_request_key`는 `PENDING`일 때 `SHA-256(toiletId:userId:reportType)`을 저장하고 처리·취소 시 `NULL`로 비운다. MySQL 부분 유니크 인덱스 부재를 보완한다.

### `coordinate_revision`

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `coordinate_revision_id` | `BIGINT PK` | 좌표 적용 이력 식별자 |
| `toilet_id`, `report_id` | `BIGINT FK` | 대상 화장실·승인 근거 제보 (`report_id` UNIQUE) |
| `previous_latitude`, `previous_longitude` | `DECIMAL(10,7)` | 적용 전 좌표 스냅샷 |
| `applied_latitude`, `applied_longitude` | `DECIMAL(10,7)` | 관리자 확정 좌표 |
| `previous_road_address`, `applied_road_address` | `VARCHAR(255)` | 적용 전·후 도로명 주소 |
| `applied_by_user_id`, `applied_at` | `BIGINT FK`, `DATETIME` | 적용 관리자·시각 |
| `source` | `VARCHAR(30)` | `USER_REPORT_APPROVED` |

## 승인 처리 규칙

위치 제보는 지도 중앙 고정 핀의 좌표를 바탕으로 도로명 주소를 역지오코딩해 사용자에게 보여주고, 주소 확인 후에만 제출한다. 승인 시 하나의 트랜잭션에서 PENDING 제보와 좌표 범위를 검증한 뒤 기존 좌표·도로명 주소를 이력에 보존한다. 이어 `toilet.latitude`, `longitude`, `road_address`를 함께 갱신하고 `coordinate_source = 'ADMIN_CONFIRMED'`로 설정한다. 제보 상태를 `APPROVED`로 바꾸고 `coordinate_revision`과 `audit_log(REPORT_APPROVED)`를 저장한다.

개방 시간 제보는 `proposed_open_time`만 저장한다. 승인 시 `toilet.open_time`만 변경하며 좌표 이력은 만들지 않는다.

반려·취소는 `toilet`과 `coordinate_revision`을 바꾸지 않고 상태·메모와 감사 로그만 남긴다.

## 배치와의 충돌 방지

- `ADMIN_CONFIRMED` 좌표는 3일 증분 배치와 자동 지오코딩이 덮어쓰지 않는다.
- 주소·운영시간·편의시설 등 공공데이터 속성은 계속 갱신한다.
- 관리자가 확정 좌표를 해제하는 미래 기능은 새 이력을 남기고 자동 지오코딩 좌표로 되돌린다. 기존 이력은 삭제하지 않는다.

## Flyway DDL (운영 적용)

```sql
-- V2__create_toilet_report_and_coordinate_revision.sql
CREATE TABLE toilet_report (
  report_id BIGINT NOT NULL AUTO_INCREMENT,
  toilet_id BIGINT NOT NULL, reporter_user_id BIGINT NOT NULL,
  report_type VARCHAR(30) NOT NULL,
  proposed_latitude DECIMAL(10,7) NULL, proposed_longitude DECIMAL(10,7) NULL,
  proposed_road_address VARCHAR(255) NULL, proposed_open_time VARCHAR(50) NULL,
  reason VARCHAR(500) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  active_request_key CHAR(64) NULL,
  reviewed_by_user_id BIGINT NULL, reviewed_at DATETIME NULL, review_note VARCHAR(500) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (report_id), UNIQUE KEY uk_report_active_request (active_request_key),
  KEY idx_report_status_created (status, created_at), KEY idx_report_toilet_created (toilet_id, created_at),
  CONSTRAINT fk_report_toilet FOREIGN KEY (toilet_id) REFERENCES toilet (toilet_id),
  CONSTRAINT fk_reporter_user FOREIGN KEY (reporter_user_id) REFERENCES app_user (user_id),
  CONSTRAINT fk_report_reviewer FOREIGN KEY (reviewed_by_user_id) REFERENCES app_user (user_id)
);
CREATE TABLE coordinate_revision (
  coordinate_revision_id BIGINT NOT NULL AUTO_INCREMENT,
  toilet_id BIGINT NOT NULL, report_id BIGINT NOT NULL,
  previous_latitude DECIMAL(10,7) NULL, previous_longitude DECIMAL(10,7) NULL,
  applied_latitude DECIMAL(10,7) NOT NULL, applied_longitude DECIMAL(10,7) NOT NULL,
  previous_road_address VARCHAR(255) NULL, applied_road_address VARCHAR(255) NOT NULL,
  applied_by_user_id BIGINT NOT NULL, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source VARCHAR(30) NOT NULL DEFAULT 'USER_REPORT_APPROVED',
  PRIMARY KEY (coordinate_revision_id), UNIQUE KEY uk_revision_report (report_id),
  KEY idx_revision_toilet_applied (toilet_id, applied_at),
  CONSTRAINT fk_revision_toilet FOREIGN KEY (toilet_id) REFERENCES toilet (toilet_id),
  CONSTRAINT fk_revision_report FOREIGN KEY (report_id) REFERENCES toilet_report (report_id),
  CONSTRAINT fk_revision_admin FOREIGN KEY (applied_by_user_id) REFERENCES app_user (user_id)
);
```

> 위 DDL은 `toilet-api`의 `V2__create_toilet_report_and_coordinate_revision.sql`로 운영 반영되었다. 이 문서만으로 운영 DB를 수동 변경하지 않는다. 전체 테이블 관계와 적용 순서는 [운영 데이터 모델 v1.4](database-schema-v1.4.md)를 참조한다.

## 변경 이력

| 버전 | 일자 | 변경 내용 |
| --- | --- | --- |
| v1.4 | 2026-08-31 | Flyway V2 실제 운영 적용 상태와 전체 운영 데이터 모델 문서 연결 |
| v1.3 | 2026-08-30 | 제보·좌표·개방시간 승인 모델과 DDL 기준 작성 |
