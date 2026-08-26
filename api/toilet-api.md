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
