# 자체 서비스 이용 분석

2026-09-17 · 운영 전환 완료 · [WBS·검증 근거](https://github.com/toilet-project/docs/issues/107)

## 무엇이 바뀌었나

Google Analytics 태그·쿠키·Data API·전용 설정과 저장 구조를 제거하고, 서비스 자체 수집 API와 관리자 집계 화면으로 전환했습니다. 과거 [GA 설계](google-analytics-admin-dashboard.md)는 현재 운영 지침이 아닙니다.

## 수집 경계

| 수집·집계 | 저장하지 않는 분석 정보 |
| --- | --- |
| 페이지·허용 이벤트·검색 성공과 결과 수 구간 | 검색 원문·자유 입력 본문 |
| 기기·OS·브라우저·유입 도메인·국가/도시 구간 | 원문 IP·원문 User-Agent·정확한 위치/주소 |
| 기간 한정 HMAC 기반 중복 제거 | 회원 ID·이메일·영구 사용자 추적 ID |
| 리뷰·제보·로그인 결과 이벤트 | 리뷰·제보 본문·OAuth 토큰 |

서버가 요청에서 계산하는 값과 DB에 저장하는 값은 구분합니다. **활성 방문자는 기간별 추정치**이며 실제 사람 수가 아닙니다. 네트워크·브라우저 변화나 공유 환경의 영향을 받으며, 일별 값을 합산해 월간 순 방문자로 간주하지 않습니다.

## 처리 흐름

허용 이벤트 → Origin·크기·빈도·필드 검사 → 원시 이벤트 → KST 기간 집계 → 관리자 화면

- 수집 API: POST /api/v1/analytics/events.
- 최근 30분과 오늘 집계, 일별 요약·차원별 지표를 구분합니다.
- 매일 02:30 KST에 최근 14개 완료일을 멱등 재계산합니다.
- 원시 이벤트는 35일 후 만료하고 장기 요약과 분리합니다.
- 분석 실패는 지도·검색·리뷰 등 사용자 기능의 실패로 전파하지 않습니다.

## 정책과 검증

공개 개인정보 안내를 실제 수집 범위로 수정했고, 운영 웹의 Google Analytics/Tag Manager 요청·스크립트 제거와 자체 집계 반영을 확인했습니다. 데이터 최소화 또는 동의 배너 제거만으로 법적 동의 의무가 없다고 단정하지 않습니다. 수집 목적·대상·항목이 바뀌면 정책과 필요 절차를 다시 검토합니다.

[API 구현](https://github.com/toilet-project/toilet-api/pull/142) · [관리자 전환](https://github.com/toilet-project/toilet-admin-api/pull/96) · [웹 전환](https://github.com/toilet-project/toilet-web/pull/253) · [레거시 제거](https://github.com/toilet-project/toilet-api/pull/145)
