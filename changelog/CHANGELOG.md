# 문서 변경 이력

## 2026-08-31 — 운영 아키텍처·데이터 모델·DDL 문서 v3.0

- Cloudflare Pages/Access, Mini PC Docker, Nginx, API·관리자·배치, MySQL·Redis의 현재 운영 경계를 아키텍처 v3.0으로 정리했다.
- `toilet`, 인증, 제보·좌표 이력, 배치 실행 이력을 하나의 운영 데이터 모델 v1.4로 연결하고 실제 DDL 출처·적용 순서를 명시했다.
- OAuth 쿠키 기반 JWT, Redis refresh session, 공개/사용자/관리자 API와 정기 운영 점검 기준을 현재 구현 상태로 갱신했다.

## 2026-08-30 — 사용자 제보·좌표 승인 모델 v1.2

- `toilet_report`와 `coordinate_revision`의 책임과 상태 전이를 정의했다.
- 승인된 제보만 `toilet` 최종 좌표와 `ADMIN_CONFIRMED` 출처를 변경하도록 정했다.
- 중복 제보 방지 키, 적용 이력·감사 로그 연계, Flyway DDL 초안을 추가했다.

## 2026-08-30 — 인증·권한 정책 및 데이터 모델 설계 v1.1

- 별도 인증 서버 없이 `toilet-api` 안에서 Spring Security OAuth2 Client로 Google·Kakao 로그인을 처리하는 방향을 확정했다.
- `app_user`, `user_social_account`, `user_role`, `audit_log`의 책임·제약·관계를 설계했다.
- JWT access token과 Redis refresh token의 역할을 분리하고, Redis TTL·회전·폐기·키 정책을 문서화했다.
- Spring Security, OAuth2 Client/Resource Server, JOSE, Redis 라이브러리와 Redis 내부망 운영 구성을 명시했다.
- USER/ADMIN 역할, Cloudflare Access와 애플리케이션 역할 검증의 이중 방어를 문서화했다.
- 이메일 컬럼은 유지하되 공개 API·로그 노출을 금지하고, BitLocker·이메일 필드 암호화는 현재 운영 범위에서 제외했다.
- 다음 WBS의 migration, OAuth 콘솔 설정, Security 구현, 제보 기능이 참조할 기준을 확정했다.

## 2026-08-26 — 좌표 메타데이터 및 증분 지오코딩

- `toilet` 테이블에 `coordinate_source`, `geocoded_address_hash`, `geocoded_at`을 추가했다.
- 최근 3일 공공데이터 갱신분만 처리하는 배치 지오코딩 정책을 문서화했다.
- 관리자 확정 좌표(`ADMIN_CONFIRMED`)를 자동 배치가 덮어쓰지 않는 원칙을 추가했다.
- 아키텍처 문서를 v2.1로 갱신했다.

## 문서 버전 원칙

- 스키마·외부 API·운영 구조처럼 서비스 동작에 영향을 주는 변경은 해당 명세의 변경 이력과 이 문서에 함께 기록한다.
- 세부 변경은 Git 커밋과 Pull Request로 추적하며, 확정된 내용만 `main`에 반영한다.
