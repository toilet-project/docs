# 📚 급똥 프로젝트 문서

급똥 서비스의 요구사항, API·DB 명세, 아키텍처, 운영 가이드를 관리하는 문서 저장소입니다. 문서는 도메인별 폴더로 관리하며, 새 문서는 아래 분류에 맞춰 추가합니다.

| 운영 서비스 | Public API | 프로젝트 관리 |
| --- | --- | --- |
| [geupddong.com](https://geupddong.com) | [api.geupddong.com](https://api.geupddong.com) | [WBS](https://github.com/orgs/toilet-project/projects/2/views/2) |

## 문서 목록

| 구분 | 문서 | 설명 |
| --- | --- | --- |
| 아키텍처 | [아키텍처 v3.0](architecture/architecture-v3.md) | Cloudflare·Mini PC·인증·배치까지 반영한 현재 운영 구조 |
| 운영 | [배포·운영 가이드](operations/deployment.md) | 도메인, HTTPS, 배포 및 비밀정보 원칙 |
| 운영 | [운영 안정화 Runbook v1.1](operations/reliability-runbook.md) | 암호화 백업·복구, 재부팅 자동 점검, DB·OAuth 장애 알림 절차 |
| 운영 | [DB 백업·복구 리허설](operations/backup-restore-rehearsal-2026-08-31.md) | 실제 운영 백업과 임시 복구 검증 결과 |
| API | [Toilet API 명세](api/toilet-api.md) | 공개 지도·인증·제보·관리자 API 계약 |
| DB | [운영 데이터 모델 v1.7](database/database-schema-v1.7.md) | 정책 버전·사용자 동의·탈퇴까지 포함한 최신 운영 모델 |
| DB | [Toilet 테이블 명세](database/toilet-table.md) | 공공데이터·좌표 정책을 포함한 화장실 원천 데이터 |
| DB | [사용자 제보·좌표·개방시간 승인 모델 v1.4](database/user-report-coordinate-model.md) | 제보 상태 전이, 확정 좌표·주소 이력 및 적용 DDL |
| DB | [중복 좌표 데이터 품질 관리](database/duplicate-coordinate-quality.md) | 동일 좌표 그룹 확인, 직접 보정, 이력·배치 보호 정책 |
| 변경 이력 | [문서 변경 이력](changelog/CHANGELOG.md) | 스키마·아키텍처 등 주요 문서 변경 기록 |
| 기획 | [요구사항 정의서](planning/requirements.md) | 서비스 목표와 향후 확장 범위 |
| 기획 | [인증·권한 정책 및 데이터 모델 설계 v1.5](planning/authentication-authorization-design.md) | Google·Kakao 로그인, 정책 동의, USER/ADMIN 권한, JWT·Redis 세션·감사 로그 구현 기준 |
| 기획 | [개인정보·서비스 약관 및 회원 동의 정책 v1.0](planning/privacy-policy-consent-v1.md) | 만 14세 이상, 정책 버전 동의, GPS 고지, 보유·파기·탈퇴 기준 |

## 최신 아키텍처

![급똥 아키텍처 v3](architecture/assets/architecture-v3.svg)

## 문서 추가 규칙

- 아키텍처 자료와 원본 다이어그램은 `architecture/`에 둡니다.
- 스키마·DDL·데이터 정책은 `database/`에 둡니다.
- 외부·내부 API 계약은 `api/`에 둡니다.
- 배포·보안·장애 대응은 `operations/`에 둡니다.
- 요구사항·의사결정 기록은 `planning/`에 둡니다.
- 서비스 동작에 영향을 주는 확정 변경은 `changelog/CHANGELOG.md`에 최신순으로 추가합니다.
