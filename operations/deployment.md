# 운영 가이드 v2.0

## 도메인과 HTTPS

- 도메인: `geupddong.com`
- 웹: `https://geupddong.com`
- API: `https://api.geupddong.com`
- 관리자: `https://admin.geupddong.com` (Cloudflare Access 승인 운영자만 접근)
- Cloudflare DNS/프록시를 사용하며, 외부 통신은 HTTPS를 기본값으로 합니다.

## Mini PC 배포 구조

Mini PC(Ubuntu)에서 Docker로 `toilet-api`, `toilet-admin-api`, `toilet-batch`, MySQL, Redis를 실행합니다. Nginx는 외부 요청을 받고 API·관리자 컨테이너로 프록시합니다. MySQL·Redis·Batch는 외부 포트를 열지 않으며, Spring Boot 컨테이너 포트도 로컬/내부 네트워크 범위로 제한합니다.

관리자는 Cloudflare Access 통과와 API의 `ADMIN` 역할 검증을 모두 만족해야 합니다. Access는 외부 진입 경계이고, 역할 검증은 애플리케이션의 최종 권한 판단입니다.

## CI/CD

1. 기능 브랜치 → `develop` → `main` 병합
2. GitHub Actions에서 Java 21 빌드·테스트·정적 분석
3. Docker 이미지 빌드 후 Docker Hub 푸시
4. SSH로 Mini PC에 접속하여 Docker Compose pull/up
5. `/api/health`, 관리자 화면, 최근 `batch_sync_history`를 기준으로 배포 결과 점검

## 비밀정보 원칙

- `.env`, DB 비밀번호, 카카오 REST/JavaScript 키, SSH 키는 커밋하지 않습니다.
- GitHub Actions에는 Repository Secrets를 사용합니다.
- 문서에는 키 값·내부 IP·계정 비밀번호를 적지 않습니다.

## 정기 점검

- 배포 후 `https://api.geupddong.com/api/health`로 API와 DB 연결 상태를 확인합니다.
- 배치는 매일 02:00(Asia/Seoul)에 최근 3일 공공데이터 갱신분을 처리합니다. 실패·수신·신규·수정 건수는 관리자 배치 이력에서 확인합니다.
- 관리자 제보 검토는 대기 상태, 승인/반려 이력, 감사 로그를 함께 확인합니다.
- 장애 시 컨테이너 재시작 정책과 GitHub Actions 배포 로그를 먼저 확인하고, DB·Redis 포트를 외부로 열어 진단하지 않습니다.

## 변경 이력

| 버전 | 일자 | 변경 |
| --- | --- | --- |
| v2.0 | 2026-08-31 | 관리자 Access, Redis, 배치 이력·정기 점검 기준 반영 |
