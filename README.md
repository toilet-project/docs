# 급똥 (Geupddong) 프로젝트 문서

공공데이터 기반으로 주변 공중화장실을 지도에서 빠르게 찾는 서비스입니다.

## 운영 주소

| 구분 | 주소 |
| --- | --- |
| 서비스 | [https://geupddong.com](https://geupddong.com) |
| Public API | [https://api.geupddong.com](https://api.geupddong.com) |
| API 상태 확인 | [https://api.geupddong.com/api/health](https://api.geupddong.com/api/health) |

모든 외부 트래픽은 Cloudflare를 통해 HTTPS로 제공됩니다.

## 문서 목록

- [아키텍처 v2](architecture-v2.md): 현재 운영 구조와 배포 흐름
- [운영 가이드](operations.md): 도메인, HTTPS, 배포 및 비밀정보 원칙
- [API 명세](api_spec.md): 지도 영역 조회와 화장실 상세 조회
- [DB 테이블 명세](db_table.md)
- [요구사항 정의서](requirements.md)
- [WBS](https://github.com/orgs/toilet-project/projects/2/views/2): 일정과 작업 관리

## 저장소

| 역할 | 저장소 |
| --- | --- |
| 웹 클라이언트 | [toilet-web](https://github.com/toilet-project/toilet-web) |
| Public API | [toilet-api](https://github.com/toilet-project/toilet-api) |
| 배치 | [toilet-batch](https://github.com/toilet-project/toilet-batch) |
| 관리자 API | [toilet-admin-api](https://github.com/toilet-project/toilet-admin-api) |
| 프로젝트 문서 | [docs](https://github.com/toilet-project/docs) |
