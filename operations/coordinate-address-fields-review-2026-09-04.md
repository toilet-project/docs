# 도로명·지번 분리 저장 검증 보고서

> 공개 요약본입니다. 작성 당시의 수치·검증 단계를 보존합니다. 최신 배포 및 남은 검증은 [관리자 검토 배포 보고서](region-admin-review-release-2026-09-05.md)를 참고하세요. 전체 JSON·시설별 검토 원문·운영 접속정보는 공개하지 않습니다.

2026-09-04 · WBS [toilet-api #75](https://github.com/toilet-project/toilet-api/issues/75)

## 결과

로컬 구현과 자동 검증을 완료했다. 운영 DB 업데이트, 운영 제보 접수·승인, 실 API 추가 호출, 컨테이너 교체, main push 및 배포는 하지 않았다.

| 검증 | 결과 |
| --- | --- |
| API 전체 Gradle test | 75건 중 71 통과, 기존 Docker 의존 통합 테스트 4 skip, 실패 0 |
| Batch 전체 Gradle test | 52 통과, 실패 0 |
| Web TypeScript + Vite build | 성공 |
| Web oxlint | 오류 0, 기존 React hook 경고 3개 |
| Admin reports.js / data-quality.js 구문 검사 | 성공 |
| V9 데이터 보존 | H2 MySQL 호환 모드에서 기존 원문 유지·NULL 도로명/지번 저장 확인 |
| 실제 MySQL V9 및 운영 승인 흐름 | 아직 미실행, 배포 전 필수 |

H2는 MySQL의 복수 절 ALTER를 지원하지 않아 테스트에서는 ALTER 절만 나눠 실행했다. 컬럼 정의는 원본 V9와 동일하다. 이 검사는 실제 MySQL DDL/잠금/운영 트랜잭션 검증을 대신하지 않는다.

## 확인한 사례

- 두 주소 반환: 각각 별도 필드에 저장.
- 도로명만/지번만 반환: 반대 필드는 NULL. 지번을 도로명에 복사하지 않음.
- 좌표 7자리 정밀도: 저장할 좌표와 같은 정밀도로 외부 조회.
- 결과 없음·둘 다 없음·공백·복수 결과·주소 255자 초과·파싱 실패: 저장 실패 처리.
- HTTP 429·네트워크 timeout: 민감한 공급자 오류를 노출하지 않고 실패, 자동 재시도 없음.
- 잘못된 좌표/관리자 한쪽 좌표만 지정: 외부 호출 전에 거절.
- 제보 접수: 서버 조회 주소 저장, 클라이언트 혼합 주소를 신뢰하지 않음.
- 관리자 좌표 보정 승인: 원본 제보 보존, 이전/확정 지번 포함 이력 저장.
- 보정 없이 레거시 제보 승인: 원본 좌표로 다시 조회, 기존 제보 원문 보존.
- 조회 실패: 제보 저장·화장실 변경·승인/알림 처리 경로로 진입하지 않음.
- 모델 재확정: 이전 위치의 반대 주소를 NULL로 제거.
- 배치 SQL: ADMIN_CONFIRMED 좌표와 도로명(NULL 포함)·지번 보존. 일반 행 주소 갱신 유지.

## 수정 위치

API / Batch / Docs는 기존 `feature/administrative-region-normalization` 작업 트리에 이어 작성했다. Web / Admin은 로컬 `origin/develop` 기준 `feature/coordinate-address-fields`를 만들었다. 아직 커밋·원격 push하지 않았다.

### toilet-api

- `build.gradle`: 테스트용 H2 runtime.
- `geocoding/CoordinateAddress`, `CoordinateAddressResolver`, `AddressLookupException`: 공통 좌표→유형별 주소 조회.
- `global/exception/GlobalExceptionHandler`: 안전한 503 오류 응답.
- `toilet/model/Toilet`: 확정 주소 2개 저장.
- `report/model/ToiletReport`, `CoordinateRevision`: 제안/변경 전후 지번 저장.
- `report/service/ToiletReportService`: 접수/승인 시 서버 조회, 확정 좌표 짝 검증 및 잠금.
- `report/dto/CreateToiletReportRequest`, `ReviewToiletReportRequest`, `ToiletReportResponse`: 호환 계약 및 응답.
- `quality/service/CoordinateQualityService`, `quality/dto/CorrectToiletCoordinateRequest`, `CoordinateQualityRevisionResponse`: 직접 보정/이력.
- `src/main/resources/db/migration/V9__separate_coordinate_report_addresses.sql`.
- `CoordinateAddressResolverTest`, `CoordinateAddressMigrationTest`, `ToiletCoordinateAddressTest`, `ToiletReportServiceTest`, `CoordinateQualityServiceTest`.

### toilet-batch

- `batch/ToiletSyncWriter.java`: 관리자 확정 주소 보존 조건.
- `batch/ToiletSyncWriterTest.java`: 실제 메모리 DB SQL 회귀 확인.
- 같은 파일에 있던 선행 행정구역 작업의 좌표 보존 변경은 그대로 유지했다.

### toilet-web / toilet-admin

- Web `src/api/reports.ts`, `src/components/MyReportsPanel.tsx`: nullable jibunAddress 및 표시 fallback.
- Admin `src/main/resources/static/reports.js`: 원본 제보 주소 fallback, 승인 오류 내용 표시.
- Admin `src/main/resources/static/data-quality.js`: 주소 읽기 전용·서버 검증 안내와 오류 표시.

### toilet-docs

- `database/coordinate-address-fields-v1.9.md`, `database/ddl/v1.9-coordinate-address-fields.sql`.
- 본 보고서, README/CHANGELOG/API 명세 연계, 기존 정규화 표본의 공급자 불일치 후속 설명.

## 남은 위험과 승인 사항

- 운영 MySQL migration 리허설과 배포 후 실제 제보 검증 미실행.
- API의 기존 Docker 기반 통합 테스트 4건 미실행.
- Kakao 앱 전체 잔여 쿼터 미확인. 접수/확정마다 서버 호출이 추가됨.
- 승인 중 제보 행 잠금이 외부 조회 제한 시간만큼 유지될 수 있음.
- 공급자 주소/행정구역 결과가 다를 수 있으며 정확한 건물 도로명주소 반환을 보장하지 않음.
- 구버전/새버전 혼재 배포에서 주소 NULL 처리와 배치 보호 순서를 준수해야 함.
- 기존 혼합 저장 주소를 일괄 복구하지 않았으며, 과거 제보의 신규 지번 컬럼은 NULL로 남음.
- V8과 V9의 배포 승인 및 배치 main 코드 리뷰가 필요함.
