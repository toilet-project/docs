# 📄 REST API Specification

> 운영 Base URL: `https://api.geupddong.com`
> 지도 영역 조회는 2026-08부터 줌 레벨에 따라 개별 마커 또는 서버 클러스터를 반환하는 v2 응답을 사용합니다.

## 1. 지도 영역 내 화장실 목록 조회

사용자가 지도를 이동하거나 확대/축소했을 때, 현재 화면 사각형 영역(Bounding Box)에 존재하는 화장실 목록을 가볍게 조회합니다.

- **URL**: `/api/v1/toilets`
- **Method**: `GET`
- **Description**: 현재 지도 화면 범위 내의 화장실 위치 및 기본 정보 조회

---

### 📥 Request Parameters (Query String)

| Parameter | Type | Required | Description | Example |
| :--- | :--- | :---: | :--- | :--- |
| **`southLat`** | Double | 필수 | 화면 최남단(아래) 위도 | `37.4900` |
| **`northLat`** | Double | 필수 | 화면 최북단(위) 위도 | `37.5100` |
| **`westLng`** | Double | 필수 | 화면 최서단(왼쪽) 경도 | `127.0100` |
| **`eastLng`** | Double | 필수 | 화면 최동단(오른쪽) 경도 | `127.0300` |
| **`zoom`** | Integer | 선택 | 현재 카카오맵 Zoom Level | `3` |

---

### 📤 Response Body (v2 JSON Object)

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `meta.map_level` | Integer | 요청에 사용한 카카오맵 레벨 |
| `meta.display_type` | String | `MARKER` 또는 `CLUSTER` |
| `meta.total_count` | Long | 화면 범위의 전체 화장실 수 |
| `meta.result_count` | Integer | 반환된 마커 또는 클러스터 수 |
| `toilets` | Array | `MARKER`일 때만 반환되는 개별 마커 목록 |
| `clusters` | Array | `CLUSTER`일 때만 반환되는 묶음 목록 (`latitude`, `longitude`, `count`) |

개별 마커의 필드는 아래와 같습니다.

| Field Name | Type | Nullable | Description | Example |
| :--- | :--- | :---: | :--- | :--- |
| **`id`** | Long | N | 화장실 고유 식별자 (PK) | `101` |
| **`name`** | String | N | 화장실 명칭 | `"강남역 공중화장실"` |
| **`latitude`** | Double | N | 위도 (Latitude) | `37.4979` |
| **`longitude`** | Double | N | 경도 (Longitude) | `127.0276` |

<br/>

* **Response Example (`200 OK`, MARKER)**

```json
{
  "meta": { "map_level": 3, "display_type": "MARKER", "total_count": 2, "result_count": 2 },
  "toilets": [
    { "id": 101, "name": "강남역 공중화장실", "latitude": 37.4979, "longitude": 127.0276 },
    { "id": 102, "name": "역삼공원 화장실", "latitude": 37.5002, "longitude": 127.0365 }
  ]
}
```

## 3. 인증 API

| API | 인증 | 설명 |
| --- | --- | --- |
| `GET /api/v1/auth/login/{google|kakao}` | 공개 | OAuth 로그인 시작 |
| `GET /api/v1/auth/me` | USER 이상 | 현재 로그인 사용자·역할 조회 |
| `GET /api/v1/policies` | 공개 | 현재 적용 중인 정책 버전·공개 경로 조회 |
| `GET /api/v1/auth/consents/status` | 로그인 | 최신 필수 정책의 미동의 상태와 내 정책별 동의 버전·시각 조회 |
| `POST /api/v1/auth/consents` | 로그인 | 필수 정책 key·version 동의 이력 저장 |
| `POST /api/v1/auth/refresh` | refresh cookie | access/refresh 토큰 회전 |
| `POST /api/v1/auth/logout` | 공개 | refresh 세션 폐기 및 인증 쿠키 만료 |
| `DELETE /api/v1/auth/me` | 로그인 | 회원 탈퇴·소셜 연결/역할/전체 refresh 세션 폐기 |

성공 로그인 후 API는 URL에 토큰을 넣지 않고 HttpOnly·Secure 쿠키(`geupddong_access`, `geupddong_refresh`)를 설정한 뒤 웹의 인증 완료 화면으로 이동한다. access JWT는 15분, refresh 세션은 Redis에서 14일 TTL로 관리한다. 신규 사용자는 `PENDING_CONSENT`로 생성하며 최신 필수 정책에 모두 동의하면 `ACTIVE`가 된다. 기존 사용자에게도 최신 필수 동의가 없으면 `GET /auth/me`의 `consentRequired`가 `true`로 반환된다.

## 4. 사용자 제보 API

| API | 인증 | 설명 |
| --- | --- | --- |
| `POST /api/v1/reports` | ACTIVE + 최신 필수 동의 | 위치 또는 개방시간 제보 접수 |
| `GET /api/v1/reports/me` | ACTIVE + 최신 필수 동의 | 내 제보 목록 조회 |

제보 유형은 `COORDINATE_CORRECTION`, `OPEN_TIME_CORRECTION`이다. 위치 제보에는 제안 좌표와 사용자 확인 도로명 주소를 함께 저장한다. 응답의 상태는 `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED` 중 하나다.

## 5. 관리자 API

관리자 API는 `ADMIN` 역할이 필요하며, 운영 웹 진입 시 Cloudflare Access도 함께 적용된다.

| API | 설명 |
| --- | --- |
| `GET /api/admin/v1/reports/summary` | 제보 상태 요약 |
| `GET /api/admin/v1/reports/search` | 상태·기간·검색어·정렬·페이지 기준 제보 목록 |
| `GET /api/admin/v1/reports/{reportId}` | 제보와 현재 화장실 정보 상세 |
| `POST /api/admin/v1/reports/{reportId}/approve` | 좌표/개방시간 제보 승인 |
| `POST /api/admin/v1/reports/{reportId}/reject` | 제보 반려 |
| `GET /api/admin/v1/batch-syncs/search` | 배치 이력 페이지 조회 |
| `GET /api/admin/v1/batch-syncs/daily` | 일별 배치 집계 |

관리자 상세 조회와 목록은 서버 페이지네이션을 사용한다. 제보 승인·반려는 감사 로그를 남기며, 위치 승인 시 `coordinate_revision`에 전후 좌표·주소를 기록한다.

## 2. 화장실 상세 정보 조회

지도 위의 특정 마커를 클릭하거나 마우스를 올렸을 때, 해당 화장실의 부가 상세 정보를 조회합니다.

- **URL**: `/api/v1/toilets/{toiletId}`
- **Method**: `GET`
- **Description**: 특정 화장실의 세부 정보(개방시간, 남녀공용 여부, 편의시설 등) 조회

---

### 📥 Request Parameters (Path Variable)

| Parameter | Type | Required | Description | Example |
| :--- | :--- | :---: | :--- | :--- |
| **`toiletId`** | Long | 필수 | 화장실 고유 PK | `101` |

---

### 📤 Response Body (JSON Object)

| Field Name | Type | Nullable | Description | Example |
| :--- | :--- | :---: | :--- | :--- |
| **`id`** | Long | N | 화장실 고유 식별자 (PK) | `101` |
| **`name`** | String | N | 화장실명 (지도 마커 및 상세 팝업) | `"강남역 공중화장실"` |
| **`toiletType`** | String | Y | 구분명 (개방/공중/간이화장실) | `"공중화장실"` |
| **`roadAddress`** | String | Y | 소재지도로명주소 (기본 표시 주소) | `"서울특별시 강남구 강남대로 396"` |
| **`jibunAddress`** | String | Y | 소재지지번주소 (도로명 주소 부재 시 대체 주소) | `"서울특별시 강남구 역삼동 858"` |
| **`maleToiletCount`** | Integer | Y | 남성용-대변기수 | `3` |
| **`maleUrinalCount`** | Integer | Y | 남성용-소변기수 | `4` |
| **`maleDisabledToiletCount`** | Integer | Y | 남성용-장애인용대변기수 | `1` |
| **`maleDisabledUrinalCount`** | Integer | Y | 남성용-장애인용소변기수 | `1` |
| **`maleChildToiletCount`** | Integer | Y | 남성용-어린이용대변기수 | `0` |
| **`maleChildUrinalCount`** | Integer | Y | 남성용-어린이용소변기수 | `1` |
| **`femaleToiletCount`** | Integer | Y | 여성용-대변기수 | `6` |
| **`femaleDisabledToiletCount`** | Integer | Y | 여성용-장애인용대변기수 | `1` |
| **`femaleChildToiletCount`** | Integer | Y | 여성용-어린이용대변기수 | `1` |
| **`agencyName`** | String | Y | 관리기관명 (담당 관리기관/부서명) | `"강남구청 도시선진화담당관"` |
| **`phoneNumber`** | String | Y | 전화번호 (전화 걸기 링크 연동) | `"02-3423-5900"` |
| **`openTime`** | String | Y | 개방시간 | `"24시간"` |
| **`openTimeDetail`** | String | Y | 개방시간상세 (상세 개방 및 휴무 설명) | `"연중무휴"` |
| **`installationDate`** | String | Y | 설치연월 (YYYY-MM) | `"2018-05"` |
| **`hasEmergencyBell`** | String | Y | 비상벨설치여부 (`Y` / `N`) | `"Y"` |
| **`emergencyBellLocation`** | String | Y | 비상벨설치장소 (상세 위치) | `"화장실 내부 및 장애인용 대변기"` |
| **`hasCctv`** | String | Y | 화장실입구CCTV설치여부 (`Y` / `N`) | `"Y"` |
| **`hasDiaperTable`** | String | Y | 기저귀교환대설치여부 (`Y` / `N`) | `"Y"` |
| **`diaperTableLocation`** | String | Y | 기저귀교환대장소 (상세 위치) | `"여자화장실 입구"` |
| **`dataBaseDate`** | String | Y | 데이터기준일자 | `"2024-01-01"` |
| **`dataSource`** | String | Y | 데이터 출처 | `"공공데이터포털"` |

<br/>

* **Response Example (`200 OK`)**

```json
{
  "id": 101,
  "name": "강남역 공중화장실",
  "toiletType": "공중화장실",
  "roadAddress": "서울특별시 강남구 강남대로 396",
  "jibunAddress": "서울특별시 강남구 역삼동 858",
  "maleToiletCount": 3,
  "maleUrinalCount": 4,
  "maleDisabledToiletCount": 1,
  "maleDisabledUrinalCount": 1,
  "maleChildToiletCount": 0,
  "maleChildUrinalCount": 1,
  "femaleToiletCount": 6,
  "femaleDisabledToiletCount": 1,
  "femaleChildToiletCount": 1,
  "agencyName": "강남구청 도시선진화담당관",
  "phoneNumber": "02-3423-5900",
  "openTime": "24시간",
  "openTimeDetail": "연중무휴",
  "installationDate": "2018-05",
  "hasEmergencyBell": "Y",
  "emergencyBellLocation": "화장실 내부 및 장애인용 대변기",
  "hasCctv": "Y",
  "hasDiaperTable": "Y",
  "diaperTableLocation": "여자화장실 입구",
  "dataBaseDate": "2024-01-01",
  "dataSource": "공공데이터포털"
}
```

## 관리자 역할·감사 로그 API

아래 API는 모두 로그인과 `ADMIN` 역할이 필요하며, 관리자 웹은 서버 페이지네이션 결과만 표시한다.

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/api/admin/v1/security/users` | 이름·이메일 키워드, 계정 상태, 역할별 사용자 검색 |
| `POST` | `/api/admin/v1/security/users/{userId}/admin-role` | 관리자 역할 부여 |
| `DELETE` | `/api/admin/v1/security/users/{userId}/admin-role` | 관리자 역할 회수 |
| `GET` | `/api/admin/v1/security/audit-logs` | 기간·행위·수행자·대상별 감사 로그 검색 |

사용자 검색은 `keyword`, `status`, `role`, `page`, `size`를 받는다. 감사 검색은 `from`, `to`, `action`, `actorUserId`, `targetType`, `targetId`, `sort`, `page`, `size`를 받는다. `size`는 1~50이며 날짜 범위가 역전되면 `400 Bad Request`를 반환한다.

자기 자신의 관리자 권한과 마지막 남은 관리자 권한은 회수할 수 없다. 감사 응답에는 수행자의 표시명과 내부 ID만 제공하며 이메일·토큰·시크릿은 포함하지 않는다.

## 사용자 알림 API

사이트 내 알림은 로그인한 사용자 본인의 제보 처리 결과만 제공한다. 승인·반려 처리와 같은 트랜잭션에서 생성되며 `(user_id, report_id, type)` 유니크 제약으로 재처리에 따른 중복 알림을 막는다.

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/notifications?unreadOnly={boolean}&page={n}&size={n}` | 내 알림을 최신순 페이지로 조회 |
| `GET` | `/api/v1/notifications/unread-count` | 읽지 않은 내 알림 수 조회 |
| `PATCH` | `/api/v1/notifications/{notificationId}/read` | 내 알림 1건 읽음 처리 |
| `POST` | `/api/v1/notifications/read-all` | 읽지 않은 내 알림 전체 읽음 처리 |

다른 사용자의 알림 ID는 조회·변경할 수 없다. 웹은 알림을 선택하면 연결된 `reportId`의 내 제보 상세를 펼친다. 현재 채널은 사이트 내 알림만 사용하며 이메일 알림은 별도 수신 동의·발송 제공자·반송 및 수신 거부 정책을 확정한 뒤 추가한다.

## 중복 좌표 데이터 품질 API

> 2026-09-05 API 운영 적용: [주소 분리 저장 v1.9](../database/coordinate-address-fields-v1.9.md).
> 위치 제보 접수·승인·직접 보정의 저장 주소는 서버가 최종 좌표로 조회한다. 기존 요청 주소 필드는 호환용이며 임의 입력으로 덮어쓰지 않는다.
> 제보 응답에 nullable `jibunAddress`, 품질 이력에 nullable `appliedJibunAddress`가 추가된다. `roadAddress` 없이 지번만 반환될 수 있다. 조회 실패 시 `503 ADDRESS_LOOKUP_UNAVAILABLE`로 변경 없이 종료한다.

모든 API는 `ADMIN` 역할이 필요하다. 이름만 보고 좌표를 자동 추정하지 않으며, 관리자가 직접 저장한 좌표만 `ADMIN_CONFIRMED`로 반영한다.

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/api/admin/v1/data-quality/duplicate-coordinates` | 검색어·확인 상태·페이지 기준 중복 좌표 그룹 조회 |
| `GET` | `/api/admin/v1/data-quality/duplicate-coordinates/{groupKey}` | 그룹의 전체 화장실·대기 위치 제보·수정 이력 조회 |
| `PATCH` | `/api/admin/v1/data-quality/duplicate-coordinates/{groupKey}/review` | `PENDING`, `NEEDS_CORRECTION`, `CONFIRMED_SHARED` 상태와 메모 저장 |
| `POST` | `/api/admin/v1/data-quality/toilets/{toiletId}/coordinates` | 카카오맵에서 확인한 개별 화장실 좌표 확정·서버 역지오코딩으로 도로명/지번 주소 분리 저장 |

관리자 직접 보정은 `coordinate_revision.source=ADMIN_DIRECT`로 기록하고, 사용자 위치 제보 승인은 `USER_REPORT_APPROVED`로 구분한다. 모든 상태 변경과 좌표 변경은 감사 로그에도 남는다.

## 관리자 행정구역 검토 API (2026-09-05 배포)

모든 경로는 ADMIN 권한이 필요합니다. 비로그인 401, 일반 사용자 403입니다.

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| GET | `/api/admin/v1/regions` | 상태·검색·페이지네이션, 기본 REVIEW·20건, 최대 100건 |
| GET | `/api/admin/v1/regions/{id}` | 현재 원본·이전 판정·근거 상세 |
| GET | `/api/admin/v1/regions/{id}/history` | 개별 판정 이력, 별도 페이지네이션 |
| POST | `/api/admin/v1/regions/{id}/coordinates` | 사유·expectedLocation 필수, 동시 변경 409, 서버 역지오코딩 |

목록은 대용량 근거 JSON이나 전체 이력을 함께 받지 않습니다. 좌표 확정 시 도로명·지번을 구분하여 저장하며, 사용자 화면은 도로명 우선 → 없으면 지번 한 가지를 표시합니다. 지역 판정은 워커가 비동기로 갱신합니다.

[필터·안전 정책·배포 및 검증 결과](../operations/region-admin-review-release-2026-09-05.md)
