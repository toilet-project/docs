# 위치 제보·관리자 확정 주소 분리 저장 v1.9

작성: 2026-09-04 · API/V9 운영 적용: 2026-09-05. [운영 반영 보고서](../operations/region-production-result-2026-09-05.md). 별도 Web/Admin feature의 표시 보완과 실제 운영 승인 흐름 확인은 구분해 추적한다.

- WBS: [toilet-api #75](https://github.com/toilet-project/toilet-api/issues/75)
- 선행 검토: [행정구역 정규화 v1.8](administrative-region-normalization-v1.8.md)
- DDL: [v1.9-coordinate-address-fields.sql](ddl/v1.9-coordinate-address-fields.sql)
- 검증: [검증 보고서](../operations/coordinate-address-fields-review-2026-09-04.md)

## 변경 이유와 범위

기존 지도 코드는 `road_address.address_name`이 없으면 `address.address_name`을 선택해 단일 `roadAddress` 문자열로 전송했다. API는 이 값을 도로명주소로 저장했고, 관리자 좌표 확정 때 `toilet.jibun_address`는 갱신하지 않았다. 따라서 주소 유형 혼동과 이전 위치 지번주소가 남는 문제가 있었다.

이번 변경은 위치 제보 접수·승인·관리자 직접 보정의 주소 저장 계약을 정리한다. 기존 데이터 일괄 수정, 행정구역 전수 실행, 지도 UX 변경, SEO 페이지 생성은 하지 않는다. 화면은 새 지번주소 응답의 fallback과 오류 안내만 호환한다.

## 확정 규칙

서버의 공통 `CoordinateAddressResolver`가 입력 좌표를 DB와 동일한 DECIMAL(10,7)로 반올림한 뒤 Kakao 좌표→주소 API를 호출한다. `x=경도`, `y=위도`, `input_coord=WGS84`이다.

| API 필드 | 저장 의미 | 반환되지 않을 때 |
| --- | --- | --- |
| `documents[0].road_address.address_name` | 도로명주소 | NULL |
| `documents[0].address.address_name` | 지번주소 | NULL |

둘 다 있으면 둘 다 저장한다. 한쪽만 있으면 해당 필드만 저장하고, 없는 쪽은 NULL로 둔다. **위치 확정 시 기존 위치의 반대쪽 주소를 유지하지 않는다.** 둘 다 없거나 0건/복수 결과, 비정상 응답, 255자 초과 주소는 저장하지 않는다. 주소를 잘라 저장하지 않는다.

도로명주소로 지번주소를 대신 채우지 않으며, 문자열을 잘라 주소 유형을 추정하지 않는다. 이 API의 주소와 `coord2regioncode` 행정구역 결과는 다른 데이터이므로 서로를 덮어쓰지 않는다. 지역 경계에서 공급자 결과가 다르면 별도 검증 대상으로 유지한다.

공식 계약: [Kakao 좌표로 주소 변환](https://developers.kakao.com/docs/ko/local/dev-guide#coord-to-address).

## 저장 경로

1. 사용자 위치 제보 접수: 제보 좌표를 역지오코딩 → `toilet_report`의 제안 좌표·두 주소 저장. 이 시점에 `toilet`은 수정하지 않는다.
2. 관리자 승인: 보정 좌표가 있으면 두 좌표를 함께 사용하고, 없으면 원본 제보 좌표를 사용한다. 최종 좌표로 다시 조회한 뒤 `toilet`의 좌표·두 주소·`ADMIN_CONFIRMED` 출처를 같은 트랜잭션으로 반영한다.
3. 관리자 직접 보정: 같은 공통 서비스로 조회하고 화장실 행 잠금을 얻어 반영한다.
4. 두 확정 경로 모두 변경 전·후 좌표와 두 주소를 `coordinate_revision`에 남긴다. 원본 제보의 좌표·주소는 승인 시 변경하지 않는다.
5. 공공데이터 배치: `ADMIN_CONFIRMED` 행은 도로명·지번주소를 NULL까지 포함해 보존한다. 그 외 행의 기존 주소 수집 방식은 유지한다.

조회 실패는 `503 ADDRESS_LOOKUP_UNAVAILABLE`로 반환한다. 예외로 트랜잭션이 롤백되어 부분 좌표 변경·승인·알림 저장이 되지 않는다. 공급자 오류 본문, 인증키는 응답에 포함하지 않는다. 무조건 재시도하지 않고 사용자가 위치 확인 후 다시 요청하도록 한다.

## 스키마

| 테이블 | 컬럼 | 변경 | 의미 |
| --- | --- | --- | --- |
| toilet | road_address / jibun_address | 기존 VARCHAR(255) NULL 유지 | 확정 좌표에 대응하는 두 주소 |
| toilet_report | proposed_jibun_address | VARCHAR(255) NULL 추가 | 제보 접수 좌표의 지번주소 |
| coordinate_revision | previous_jibun_address | VARCHAR(255) NULL 추가 | 변경 전 지번주소 |
| coordinate_revision | applied_jibun_address | VARCHAR(255) NULL 추가 | 확정 지번주소 |
| coordinate_revision | applied_road_address | NOT NULL → NULL 허용 | 지번주소만 반환되는 위치 지원 |

새 테이블·인덱스는 없다. 기존 제보/화장실 ID 조회를 재사용하며, 주소에 대한 새로운 검색 패턴은 추가하지 않는다. 기존 이력·제보의 신규 컬럼은 NULL로 유지한다. 기존 `road_address`가 실제 지번이었는지 추측해서 옮기지 않는다.

## API 호환

- 제보 응답에 nullable `jibunAddress` 추가. `roadAddress`도 nullable로 읽어야 한다.
- 품질 관리 좌표 이력 응답에 nullable `appliedJibunAddress` 추가.
- 요청의 `roadAddress`, `confirmedRoadAddress`는 이전 클라이언트 호환을 위해 남기지만 **저장의 권위값으로 사용하지 않는다**. 서버의 좌표 조회 결과가 기준이다.
- 확정 좌표를 한쪽만 보내면 400. 둘 다 생략하면 제보 원래 좌표를 다시 조회한다.
- 개방시간 제보·반려는 역지오코딩하지 않는다.
- 관리자 직접 보정 화면 주소 입력은 읽기 전용으로 표시한다. 임의 입력을 받아놓고 무시하는 혼동을 피한다.

## 호출·동시성

접수 1회, 승인/직접 보정 1회당 서버 외부 호출 1회다. 브라우저 지도 SDK의 미리보기 호출은 별도다. 기존 `KAKAO_REST_API_KEY`를 재사용한다. 접속 제한 3초, 응답 제한 5초, 애플리케이션 자동 재시도 0회다. 실제 잔여 쿼터는 배포 전 확인해야 한다.

승인은 같은 제보의 중복 처리를 막기 위해 제보 행 잠금 상태에서 주소를 조회하며, 주소 확인 후 화장실 행도 잠근다. 외부 조회 중 최대 타임아웃만큼 제보 잠금이 유지될 수 있다. 직접 보정은 외부 조회 후 화장실을 잠근다. 공급자 장애나 높은 동시 요청에 대비한 추가 circuit breaker/요청 제한은 이번에 추가하지 않았다.

## 행정구역 연계

v1.8의 `current_toilet_region`은 주소·좌표 스냅샷과 현재 값이 다르면 과거 행정구역 결과를 제외한다. 지역 정규화 워커가 활성화된 배포에서는 변경분을 재평가한다. **이번 변경만으로 그 워커나 운영 전수 정규화가 활성화되지는 않는다.** 도로명·지번주소 수정과 행정구역 API의 불일치를 자동 정상 판정하지 않는다.

## 적용·복구 순서

1. 코드 검토 및 운영 적용 승인 후 `toilet`, `toilet_report`, `coordinate_revision`, Flyway 이력을 백업하고 복구 가능 여부를 확인한다. 운영 정보 원문을 공개 문서나 Git에 올리지 않는다.
2. 복제 MySQL에서 V9 원문 DDL 및 JPA 스키마 검증을 실행한다. 메모리 DB 테스트는 이 단계를 대체하지 않는다.
3. V8이 같은 feature에 포함되어 있다. 현재 운영이 V7이면 API 배포 시 V8과 V9가 순서대로 실행될 수 있으므로 **V8 승인 없이 이 브랜치를 그대로 배포하지 않는다**. 독립 배포가 필요하면 migration 번호와 feature 의존성을 별도로 정리한다.
4. Flyway를 운영 migration의 단일 실행 주체로 삼는다. docs DDL을 수동 적용하고 동일 Flyway를 중복 실행하지 않는다.
5. 관리자 주소 보호 배치를 먼저 반영하거나 동기화를 일시 제한한 뒤, V9/API 및 최소 화면 호환 변경을 반영한다. 배치 main 반영은 사용자 코드 검토·별도 승인 후 진행한다.
6. 승인된 테스트 데이터로 양쪽 주소 반환·지번만 반환·조회 실패·배치 보존을 확인한다. 이번 작업에서는 운영 화장실을 수정하지 않았다.

복구는 먼저 위치 쓰기와 배치 동기화를 중단하고 백업을 확보한다. 신규 컬럼은 바로 DROP하지 말고 보존한다. 구버전은 지번만 있는 제보와 nullable 적용 도로명주소를 처리하지 못할 수 있어 무조건적인 앱 롤백은 안전하지 않다. 가능하면 forward fix를 우선한다. `applied_road_address`의 NULL을 임의 주소로 채워 NOT NULL로 되돌리지 않는다. 데이터 복원은 백업 및 변경 이력으로 대상별 검토하고, 출처 등 이전 상태는 추정하지 않는다.
