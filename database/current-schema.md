# 현재 데이터 모델 안내

2026-09-17 기준. 예전 문서의 v1.7은 전체 현재 스키마 버전이 아닙니다. API의 Flyway 이력은 **V25까지** 확장되었습니다.

실행 가능한 DDL의 기준은 [API migration 소스](https://github.com/toilet-project/toilet-api/tree/main/src/main/resources/db/migration)입니다. 기존 SQL을 복사해 실행하거나 적용된 migration 파일을 수정하지 않습니다.

| Migration | 다루는 기능 | 읽을 문서 |
| --- | --- | --- |
| V1–V7 | 인증·제보·감사·알림·좌표 검토·KST·정책 동의 | [기본 모델 v1.7](database-schema-v1.7.md) |
| V8–V10 | 행정구역 정규화·확정 주소·판정 이력 | [V8](administrative-region-normalization-v1.8.md) · [V9](coordinate-address-fields-v1.9.md) · [V10](region-assessment-history-v1.10.md) |
| V11 | 회원 탈퇴·선택 보관·복구·후속 파기 | [회원 모델](account-withdrawal-retention-v1.11.md) |
| V12 | 리뷰, 제출 멱등성, 작성 간격·시설별 24시간 보호 | [리뷰 계약](../api/location-reviews.md) |
| V13–V14 | 소셜 프로필 사진과 CDN purge 처리 구조 | migration 소스 기준; 스키마 존재만으로 모든 화면 인수를 뜻하지 않음 |
| V15 | 화장실 묶음 표시 | [좌표 품질 관리](duplicate-coordinate-quality.md) |
| V16–V18 | 지역 override·시군구 기준·지역 배정 정규화 | migration 소스와 [지역 전환 후속](https://github.com/toilet-project/toilet-api/issues/128) |
| V19 | 공공데이터 변경 후보·수신 증빙·관리자 결정 | [변경 검토](duplicate-facility-management.md) |
| V20 | 과거 GA 집계 스냅샷 | 이력만 보존; 현재 수집 경로 아님 |
| V21–V22 | 자체 분석 저장 구조 도입·기존 GA 스냅샷 제거 | [자체 통계](../planning/service-analytics.md) |
| V23 | 시설 공개 상태·대표 시설·숨김 이력, 변경 후보와 숨김 근거 연결 | [시설 숨김](duplicate-facility-management.md) |
| V24–V25 | 관리자별 중복 이름 작업 숨김·이름 비교 collation 정합성 | [작업 숨김](duplicate-facility-management.md) |

## 캐시 DDL은 별도 번호 체계

db/cache-revalidation의 V1–V3는 위 Flyway V1–V3와 다른 **캐시 outbox·트리거 관리 스크립트**입니다. 실행 순서·승인·기존 트리거 보존을 별도로 확인합니다. [캐시 설계](../architecture/toilet-detail-cache-platform.md)

## 혼동하기 쉬운 데이터 경계

- **시설 숨김:** 시설과 연관 리뷰·제보를 보존하면서 공개 조회에서 제외합니다.
- **작업 숨김:** 해당 관리자의 검토 목록 설정이며 시설 공개 상태를 바꾸지 않습니다.
- **리뷰 작성자 연결 해제:** 계정 연결을 끊고 자유글·평가를 남깁니다. 회원 탈퇴나 리뷰 본문 삭제가 아닙니다.
- **자체 통계:** 원시 이벤트와 장기 집계를 분리하며 원문 IP·정확한 위치·검색 원문·회원 ID를 분석 저장 항목으로 사용하지 않습니다.
- **보호 기록:** 과거 백업 복원 시 파기·연결 해제가 되돌아가지 않도록 하는 별도 경계이며, R2 웹 캐시와 같은 저장소가 아닙니다.
