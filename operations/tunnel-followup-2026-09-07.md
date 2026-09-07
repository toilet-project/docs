# Tunnel 전환 후속 점검 · 2026-09-07

## 오늘 확인한 결과

| 항목 | 결과 | 경계 |
| --- | --- | --- |
| 운영 API/Admin/Batch 배포 | 세 제품 실제 Tunnel 배포 성공 | 구버전 rollback 실행은 별도 |
| 공유기 교체 | DHCP 전환·내부 SSH·Tunnel4연결·서비스 유지 | 재부팅 인수와 다름 |
| 개인 외부 SSH | 사용자 Access 후 명령 실행 성공 | 본인 계정/개인 키 사용 |
| MySQL 포워드 | 내부·외부 경로 protocol10 응답 | MySQL 공개 포트 추가 없음 |
| 포워딩 제한 | MySQL 외 목적지와 remote forwarding 거부 | 관리자 셸 권한의 sandbox 아님 |
| DB 인증 | 현재 운영 API 자격증명으로 인증·계정 읽기 성공 | Workbench GUI Test Connection 별도 |
| 공개 회귀 | health/상세/401/CORS/OAuth 시작 9건 통과 | 공급자별 로그인 완료·만료는 별도 |
| 건강 점검 | 최근 실행 정상 | Tunnel 준비 상태 보완은 승인 대기 |
| 당일 정기 백업·복원 | 종료 코드0 | 공유기 교체 이후 다음 정기 실행은 미래 |
| 보관 점검 | HOLD_LEGACY_METADATA, 종료2 | 이전 백업 메타데이터 부족으로 삭제 보류 |
| 감시 보완안 | 격리 통합9건 + 검사기4건 통과 | 실제 설치·Discord 송신은 미실행 |
| 문서 | v4 아키텍처·SSH/Workbench·마감 보고서 | [PR #79](https://github.com/toilet-project/docs/pull/79)에서 반영 상태 확인 |

## 보완안의 범위

기존 건강 점검의 5분 주기와 Discord 채널을 유지하면서 Tunnel 프로세스·Nginx·ready 상태를 기존 장애 목록에 넣는 안이다. 같은 장애는 중복 억제하고 복구 시 알린다. 실제 송신 실패/웹훅 미설정 때는 전송 완료 상태를 갱신하지 않아 다음 점검에서 재시도한다. 응답이 불명확하거나 전송 직후 상태 저장에 실패하면 중복 알림 가능성은 남는다.

OAuth 오류가 없는 초기 상태에서 처음 발생한 callback5xx와, 송신 실패 후 같은 오류의 재시도도 검사했다. 가짜 systemctl/Docker/HTTP/Discord와 임시 상태 폴더만 사용했다. 실제 서비스 중단이나 실제 장애 알림 전송으로 검사한 것이 아니다.

## 앞으로의 실행 순서

1. Workbench GUI 연결 여부 확인 — 서버 측 인증과 구분.
2. API 인증서 한 개의 Certbot staging dry-run — 승인 후 설정 백업/임시 reload/원상태 대조.
3. 건강 점검 스크립트 보완 설치와 개인정보 없는 시험 알림1건 — 승인 후 적용, API/DB/Tunnel 재시작 없음.
4. Google/Kakao 및 관리자 세션·권한 세부 인수 — 사용자 로그인 참여, 실제 제보/탈퇴 실행 없음.
5. 다음 정기 실행 확인 — 02:00 배치, 03:15 백업, 03:35 복원 점검, 04:15 이후 보관 점검, 09:00 이후 만료 점검(KST, 일부 jitter).
6. 정확한 시험 자원 목록을 대조한 뒤 대상별 정리 승인 — 현재 운영 Tunnel/배포 토큰/개인 키/복구 자료는 삭제 대상 아님.
7. 실제 재부팅·구버전 복구·호스트 전체 장애의 독립 감시는 현장 복구 수단과 운영 영향을 확인한 별도 실행으로 진행.

미래의 정기 실행·사용자 확인·별도 승인 항목을 완료 체크하지 않는다. 기존 토큰/키가 만료돼도 자동으로 Secrets나 로컬 파일이 삭제되는 것은 아니다.

[총괄 #73](https://github.com/toilet-project/docs/issues/73) · [배포 #77](https://github.com/toilet-project/docs/issues/77) · [복구·감시 #78](https://github.com/toilet-project/docs/issues/78) · [현재 구조](../architecture/architecture-v4.md).
