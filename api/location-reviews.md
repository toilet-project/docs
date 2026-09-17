# 현장 리뷰 API와 관리 정책

2026-09-17 기준 · [API 운영 인수](https://github.com/toilet-project/toilet-api/issues/105) · [공개 정책 정비](https://github.com/toilet-project/docs/issues/96)

## 작성과 수정

| 항목 | 현재 계약 |
| --- | --- |
| 로그인 | 활성 계정·정책 동의 확인. 데스크탑에서도 로그인 안내 후 모바일 작성 안내 |
| 위치 | 시설 DB 좌표 기준 150m 이내, 정확도 50m 이하, 측정 후 5분 이내 |
| 필수 입력 | 만족도 1–5, 청결도 1–5, 화장지 유무 |
| 선택 입력 | 대기시간 0–60분 / 10분 단위, 자유글 최대 200자 |
| 재작성 | 동일 계정·동일 시설은 **작성 시각부터 24시간** 제한. 자정 초기화가 아님 |
| 수정·연결 해제 | 본인만, 최초 작성 후 7일 이내. 수정으로 기한을 연장하지 않음 |
| 중복 요청 | 제출 키와 작성 제한을 함께 검사. 작성자 연결 해제로 제한이 초기화되지 않음 |

모바일 UX와 서버 위치 검사는 별개입니다. 브라우저가 전달한 위치는 조작될 수 있으며, 실제 방문을 보증하는 장치로 표현하지 않습니다. 원본 위치 좌표·측정 시각을 리뷰 테이블에 보관하지 않습니다.

## 엔드포인트

Base URL: https://api.geupddong.com. 세부 JSON은 [ReviewModels](https://github.com/toilet-project/toilet-api/blob/main/src/main/java/com/example/toiletapi/review/ReviewModels.java)와 [ReviewController](https://github.com/toilet-project/toilet-api/blob/main/src/main/java/com/example/toiletapi/review/ReviewController.java)가 기준입니다.

| Method | 경로 | 용도 |
| --- | --- | --- |
| POST | /api/v1/reviews | 작성. Idempotency-Key 헤더 필요 |
| GET | /api/v1/reviews/creation-status?toiletId=… | 작성 가능 시각·기존 본인 리뷰 확인 |
| GET | /api/v1/reviews/me | 본인 목록. from, to, cursor, size(기본 10) |
| GET | /api/v1/reviews/{id} | 본인 리뷰 상세 |
| PATCH | /api/v1/reviews/{id} | 본인 리뷰 수정 |
| POST | /api/v1/reviews/{id}/detach-author | 작성자 연결 해제 |
| GET | /api/v1/toilets/{id}/reviews | 공개 리뷰 목록 API |
| GET | /api/v1/toilets/{id}/reviews/summary | 공개 요약 집계 |

본인 응답은 공개 캐시에 저장하지 않습니다. 숨김 시설에는 신규 리뷰를 접수하지 않으며 기존 리뷰는 보존합니다. 공개 목록 API의 존재를 공개 목록 UI 전체 구현 완료로 해석하지 않습니다.

## 작성자 연결 해제와 보존

휴지통은 **본문 삭제가 아닌 작성자 정보 지우기**입니다. 확인 후 계정 연결을 끊고 내 리뷰에서 제외하며 공개 API의 작성자 표시는 익명이 됩니다. 재수정·재연결은 불가합니다.

만족도·청결도·화장지·대기시간·자유글은 남습니다. 자유글에 개인정보가 들어갈 수 있으므로 완전한 익명화를 보장하지 않습니다. 정책에는 별도의 정정·삭제 요청 경로를 안내합니다. 실제 회원 탈퇴 표시·후속 파기는 별도 계정 정책을 따릅니다.

정책 시행: **2026-09-12 18:30 KST**. 이 문서는 구현 설명이며 새로운 이용약관을 제정하지 않습니다. 이용자 안내는 서비스 공개 정책을 기준으로 확인합니다.
