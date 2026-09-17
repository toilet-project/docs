# Google Analytics 수집·운영 대시보드

> **과거 설계 / 현재 사용하지 않음.** 2026-09-17 기준 GA와 Google Data API를 제거하고 [자체 서비스 이용 분석](service-analytics.md)으로 전환했습니다. 아래 “구현 중”과 설정 절차는 9/15 당시 기록이며 재설치 지침이 아닙니다.

> WBS: [DOCS #102](https://github.com/toilet-project/docs/issues/102) · 기준일: 2026-09-15 KST · 단계: 구현 중

## 1. 목적과 운영 질문

관리자 홈은 사이트가 현재 정상적으로 사용되는지 빠르게 판단하는 곳이다. Google Analytics 영역은 다음 질문에 바로 답해야 한다.

- 지금 사용자가 들어오고 있는가?
- 오늘 사용자·조회·주요 행동은 어제 같은 시점과 비교해 어떤가?
- 최근 7일 또는 30일 추세가 급격히 변했는가?
- 어느 페이지와 유입 경로가 변화를 만들었는가?
- 어떤 기기·브라우저·지역에서 문제가 나타나는가?
- 수집 태그와 Data API가 마지막으로 언제 정상 동작했는가?

홈에는 판단에 필요한 최소 정보만 놓고, 원인 분석은 서비스 운영의 `Google Analytics` 상세 페이지에서 한다.

## 2. 외부 자원과 권한

기존 GA4 속성은 없는 것으로 보고 아래 자원을 새로 만든다.

1. Google Analytics 계정의 GA4 속성 및 `https://geupddong.com` 웹 데이터 스트림
2. Google Cloud 프로젝트의 Google Analytics Data API v1
3. Data API 전용 서비스 계정
4. GA4 속성에 부여하는 서비스 계정 `뷰어` 권한

공개 웹에는 Measurement ID만 배포 설정으로 전달한다. 서비스 계정 JSON은 관리자 서버의 비밀 파일로만 마운트하고 저장소·이미지·로그·화면에 포함하지 않는다. 관리자 서버는 `analytics.readonly` 범위로만 조회한다.

## 3. 수집 동의와 개인정보 경계

분석 동의 상태는 공개 웹 브라우저의 로컬 저장소에 `미정 / 동의 / 거부`로 보관한다. 미정 또는 거부 상태에서는 `gtag.js`를 다운로드하지 않고 요청도 전송하지 않는다. 사용자는 개인정보 처리방침과 동의 설정에서 언제든 선택을 바꿀 수 있다.

전송 금지 항목:

- 이메일, 소셜 계정 ID, 내부 회원 ID, 관리번호
- 원문 검색어와 화장실명·도로명·지번 주소
- GPS 또는 화장실의 정확한 위도·경도
- 제보·리뷰 자유 입력 내용
- 관리자 화면의 URL·업무 내역

검색 이벤트는 `query_kind`, `success`, `result_count_bucket`만 보낸다. URL의 쿼리 문자열과 해시를 제거한 경로만 페이지 경로로 사용한다.

## 4. 이벤트 사전

| 이벤트 | 발생 시점 | 허용 파라미터 |
| --- | --- | --- |
| `page_view` | 공개 경로 표시 | `page_path`, `page_title` |
| `toilet_search` | 주소·장소 검색 결과 수신 | `query_kind`, `success`, `result_count_bucket` |
| `search_result_select` | 검색 결과 선택 | `rank_bucket` |
| `toilet_marker_select` | 지도 화장실 마커 선택 | `zoom_bucket`, `source` |
| `toilet_detail_open` | 화장실 요약/상세 열기 | `source` |
| `nearby_search` | 현재 위치 기반 주변 검색 완료 | `permission_state`, `success`, `result_count_bucket` |
| `directions_click` | 길찾기 실행 | `provider` |
| `report_start` | 정보 제보 화면 열기 | `source` |
| `report_submit` | 정보 제보 제출 결과 | `report_kind`, `success` |
| `login_result` | 소셜 로그인 결과 | `provider`, `success` |
| `review_submit` | 리뷰 제출 결과 | `success` |
| `scroll_depth` | 50%·90% 최초 도달 | `percent` |

이벤트 이름과 파라미터는 소문자 영문·밑줄로 고정한다. 페이지마다 같은 의미의 이름을 재사용하며 원문 값은 넣지 않는다. 운영 핵심 행동으로 합의한 이벤트만 GA4의 주요 이벤트로 표시한다. 주요 이벤트 지정 시점 이전 데이터는 소급되지 않는다.

## 5. 관리자 지표와 화면 계약

### 운영 홈 카드

- 최근 30분 활성 사용자
- 오늘 활성 사용자와 어제 같은 기간 대비 증감률
- 오늘 조회수와 주요 이벤트 수
- 최근 7일 활성 사용자 미니 추이
- 오늘 인기 페이지 1개와 유입 채널 1개
- 마지막 성공 수집 시각과 `정상 / 지연 / 미연결 / 오류` 상태

### 상세 페이지

- 기간: 오늘, 7일, 30일, 직접 날짜 범위
- 요약: 활성 사용자, 신규 사용자, 세션, 조회수, 사용자당 조회, 참여율, 평균 참여 시간, 주요 이벤트
- 추이: 날짜별 활성/신규 사용자, 세션, 조회수, 주요 이벤트
- 콘텐츠: 경로·제목별 조회수, 사용자, 평균 참여 시간, 주요 이벤트
- 유입: 기본 채널 그룹, 소스/매체별 세션·사용자·주요 이벤트
- 환경: 기기 유형, 운영체제, 브라우저
- 지역: 국가·도시 단위. 공개 화면에는 세부 좌표가 존재하지 않는다.
- 행동: 이벤트 수, 이벤트 사용자, 주요 이벤트와 스크롤 50%·90%
- 수집 상태: 설정 여부, 마지막 시도·성공, 다음 예정, 데이터 최신성, 마지막 오류의 안전한 요약, 잔여 할당량

평균 참여 시간은 `userEngagementDuration / activeUsers`로 계산한다. 비율·증감률은 분모가 0이면 `null`로 반환해 화면에서 `비교 없음`으로 표시한다.

## 6. Data API 조회와 캐시

관리자 화면 요청이 Google API 호출을 직접 유발하지 않도록 다음 두 단계 캐시를 사용한다.

| 보고서 키 | Data API | 기본 갱신 | DB 만료 | 용도 |
| --- | --- | ---: | ---: | --- |
| `REALTIME` | `runRealtimeReport` | 요청 시 최소 60초 간격 | 2분 | 최근 30분 활성 사용자·이벤트 |
| `OVERVIEW_TODAY` | `batchRunReports` | 15분 | 30분 | 오늘/어제 비교와 홈 요약 |
| `DETAIL_7D` | `batchRunReports` | 15분 | 30분 | 기본 상세 화면 |
| `DETAIL_30D` | `batchRunReports` | 30분 | 60분 | 장기 추이·분포 |

직접 날짜 범위는 메모리에서 5분간 보관하고 운영 DB의 고정 키 스냅샷에는 적재하지 않는다. 모든 호출은 `returnPropertyQuota`를 요청해 상태 화면에 잔여량을 남긴다. 표준 보고서는 처리 지연이 있을 수 있으므로 화면에 조회 완료 시각을 함께 표시한다.

DB의 `admin_analytics_snapshot`은 보고서 키당 한 행만 유지한다. JSON에는 카드·차트용 집계 결과만 넣고 방문자·세션 단위 원본은 저장하지 않는다. 갱신 실패 시 마지막 성공 JSON은 유지하고 실패 시각·횟수·안전한 오류 코드를 별도 필드에 덮어쓴다.

## 7. 내부 API

모든 경로는 관리자 인증과 기존 권한 검사를 통과해야 한다.

| 메서드·경로 | 반환 |
| --- | --- |
| `GET /api/admin/v1/google-analytics/overview` | 홈 요약·7일 미니 추이·상위 페이지/채널 |
| `GET /api/admin/v1/google-analytics/realtime` | 최근 30분 활성 사용자·이벤트 |
| `GET /api/admin/v1/google-analytics/trend?range=7d` | 일별 추이 |
| `GET /api/admin/v1/google-analytics/content?range=7d` | 인기 페이지 |
| `GET /api/admin/v1/google-analytics/acquisition?range=7d` | 채널·소스/매체 |
| `GET /api/admin/v1/google-analytics/audience?range=7d` | 기기·OS·브라우저·국가·도시 |
| `GET /api/admin/v1/google-analytics/events?range=7d` | 이벤트·스크롤·주요 이벤트 |
| `GET /api/admin/v1/google-analytics/collection-status` | 설정·갱신·오류·할당량 상태 |
| `POST /api/admin/v1/google-analytics/refresh` | 만료·동시 실행 제한을 적용한 수동 갱신 |

응답 공통 필드는 `available`, `status`, `range`, `fetchedAt`, `lastSuccessAt`, `stale`, `data`다. 비밀값과 Google 원문 오류는 반환하지 않는다.

## 8. 실패와 복구

- 설정 없음: 서버는 시작하며 `NOT_CONFIGURED`를 반환한다.
- 권한·인증 실패: 마지막 성공 스냅샷을 반환하고 `AUTH_ERROR`를 표시한다.
- 할당량 제한: 재시도를 즉시 반복하지 않고 만료 시간을 늘려 `QUOTA_LIMITED`를 표시한다.
- 빈 결과: 정상적인 `NO_DATA`로 처리해 연결 실패와 구분한다.
- DB 읽기 실패: 관리자 GA 영역만 오류 상태가 되고 공개 서비스와 다른 관리자 기능은 유지된다.
- 동시 갱신: 보고서 키별 한 실행만 허용하고 나머지는 현재 스냅샷을 반환한다.

## 9. 구현·검증·배포 순서

1. 이 문서와 WBS로 지표·이벤트·개인정보 경계를 고정한다.
2. API Flyway에 스냅샷 테이블을 추가한다.
3. 관리자 서버에 Data API 클라이언트, 캐시, 스케줄러, 관리자 API와 합성 응답 시험을 추가한다.
4. 관리자 홈 카드·상세 페이지·메뉴를 만들고 합성 응답 프리뷰로 화면을 확인한다.
5. 공개 웹에 분석 동의·정책·비식별 이벤트 수집을 추가하고 동의 전 네트워크 무전송을 시험한다.
6. GA4 속성·웹 스트림·서비스 계정·Data API를 만들고 배포 비밀값을 연결한다.
7. DB/API → 관리자 → 공개 웹 순서로 배포한다.
8. 공개 웹에서 동의/거부·DebugView·Realtime을 확인하고, 표준 보고서가 반영되면 Data API·관리자 화면을 최종 확인한다.

GA4는 연결 전 과거 이용 데이터를 복원하지 못한다. 실데이터 운영 확인은 태그 활성화 이후 발생한 동의 사용자 이벤트로 수행한다.

## 10. 운영 반영 기록

2026-09-16 KST에 아래 순서로 운영 반영했다.

- API `775c025902866bd624e3198e6506a28eab6dfa5e`: 계정 설정을 유지하는 이미지 보존 배포로 적용했다. 새 스냅샷 테이블은 추가형 Flyway migration이며 기존 테이블을 변경하거나 삭제하지 않는다.
- 관리자 `dbea9c2da067e755d07cdbb06ef077af5d39643c`: GA4 속성 ID와 읽기 전용 서비스 계정 파일을 검증한 뒤 배포했고 애플리케이션 health `UP`을 확인했다.
- 공개 웹 `a2b6793199852589a2fe94638b9d4ef98afdddab`: Linux CI 운영 산출물에서 측정 ID 포함과 전체 검증을 확인한 후 Worker 버전 `95e49ccf-ec43-4d17-9db4-5cbde64ef320`을 100% 트래픽에 적용했다. root/www Route는 유지했고 두 도메인의 `version.json`이 같은 배포 ID를 반환한다.

동의 이전 무전송과 배포 회귀 검증은 완료했다. 속성은 새로 생성되어 과거 데이터가 없으므로, 최초 동의 사용자의 이벤트가 들어온 뒤 Realtime·표준 보고서·관리자 Data API 화면을 함께 확인하는 인수 항목은 남아 있다.
