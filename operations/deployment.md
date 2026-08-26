# 운영 가이드

## 도메인과 HTTPS

- 도메인: `geupddong.com`
- 웹: `https://geupddong.com`
- API: `https://api.geupddong.com`
- Cloudflare DNS/프록시를 사용하며, 외부 통신은 HTTPS를 기본값으로 합니다.

## Mini PC 배포 구조

Mini PC(Ubuntu)에서 Docker로 API, Batch, Admin, MySQL을 실행합니다. Nginx는 외부 요청을 받고 API 컨테이너로 프록시합니다. Spring Boot 컨테이너의 포트 바인딩은 로컬 호스트 범위로 제한합니다.

## CI/CD

1. `main` 병합
2. GitHub Actions에서 Java 21 빌드·테스트
3. Docker 이미지 빌드 후 Docker Hub 푸시
4. SSH로 Mini PC에 접속하여 Docker Compose pull/up

## 비밀정보 원칙

- `.env`, DB 비밀번호, 카카오 REST/JavaScript 키, SSH 키는 커밋하지 않습니다.
- GitHub Actions에는 Repository Secrets를 사용합니다.
- 문서에는 키 값·내부 IP·계정 비밀번호를 적지 않습니다.

## 점검 URL

배포 후 `https://api.geupddong.com/api/health`로 API와 DB 연결 상태를 확인합니다.
