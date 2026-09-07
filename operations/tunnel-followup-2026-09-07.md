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
| 건강 점검 | Tunnel·Nginx·ready 연동 설치, 22:34 KST 정기 실행 종료0 | 호스트 전체 장애의 독립 감시는 별도 |
| 당일 정기 백업·복원 | 종료 코드0 | 공유기 교체 이후 다음 정기 실행은 미래 |
| 보관 점검 | HOLD_LEGACY_METADATA, 종료2 | 이전 백업 메타데이터 부족으로 삭제 보류 |
| 감시 검증 | 격리 통합9건 + 검사기4건 통과, Discord 시험1건 HTTP204 | 실제 운영 장애 주입 없음 |
| TLS 갱신 | API 인증서 staging dry-run 종료0, 11초 | 운영 인증서·Nginx·갱신 설정 불변, nginx 문법 검사 통과 |
| 문서 | v4 아키텍처·SSH/Workbench·마감 보고서 | [PR #79](https://github.com/toilet-project/docs/pull/79)에서 반영 상태 확인 |

## 설치한 감시의 범위

기존 건강 점검의 5분 주기와 Discord 채널을 유지하면서 Tunnel 프로세스·Nginx·ready 상태를 기존 장애 목록에 추가했다. 원본을 백업하고 해시를 대조한 후 스크립트를 교체했으며 API·DB·Tunnel을 재시작하지 않았다. 같은 장애는 중복 억제하고 복구 시 알린다. 실제 송신 실패/웹훅 미설정 때는 전송 완료 상태를 갱신하지 않아 다음 점검에서 재시도한다. 응답이 불명확하거나 전송 직후 상태 저장에 실패하면 중복 알림 가능성은 남는다.

OAuth 오류가 없는 초기 상태에서 처음 발생한 callback5xx와, 송신 실패 후 같은 오류의 재시도도 격리 검사했다. 가짜 systemctl/Docker/HTTP/Discord와 임시 상태 폴더를 사용했다. 이후 개인정보 없는 실제 시험 알림을 승인 범위인 1건만 전송해 HTTP204를 확인했다. 22:28 수동 정상 점검과 22:34 정기 정상 점검도 성공했다. 실제 서비스 중단으로 검사한 것은 아니다.

## TLS 실제 인수

기존 실행 프로세스·갱신 hook 부재를 확인하고 설정을 백업한 뒤 API 인증서 한 개에 `certbot renew --dry-run`을 실행했다. staging 발급 검증은 11초 만에 종료0으로 통과했다. 실행 전후 운영 인증서·Nginx 파일·갱신 설정의 해시가 같고 `nginx -t`도 통과했다. 운영 인증서는 교체하지 않았으며 Certbot 내부의 임시 Nginx reload 가능성과 다른 서비스 재시작은 구분한다. 설치 후 공개 회귀 9건을 다시 통과했다.

## 앞으로의 실행 순서

1. Workbench GUI 연결 여부 확인 — 서버 측 인증과 구분.
2. API 인증서 staging dry-run — **완료**, 운영 인증서·설정 불변 확인.
3. 건강 점검 설치와 시험 알림1건 — **완료**, 다음 5분 정기 실행까지 확인.
4. Google/Kakao 및 관리자 세션·권한 세부 인수 — 사용자 로그인 참여, 실제 제보/탈퇴 실행 없음.
5. 다음 정기 실행 확인 — 02:00 배치, 03:15 백업, 03:35 복원 점검, 04:15 이후 보관 점검, 09:00 이후 만료 점검(KST, 일부 jitter).
6. 시험 경로4개·앱3개·전용 CI 정책/토큰·시험 Secrets4개의 종속 관계 대조 완료, 대상별 정리 승인 대기 — 현재 운영 Tunnel/공용 본인 허용 정책/배포 토큰/개인 키/복구 자료는 삭제 대상 아님.
7. 실제 재부팅·구버전 복구·호스트 전체 장애의 독립 감시는 현장 복구 수단과 운영 영향을 확인한 별도 실행으로 진행.

미래의 정기 실행·사용자 확인·별도 승인 항목을 완료 체크하지 않는다. 기존 토큰/키가 만료돼도 자동으로 Secrets나 로컬 파일이 삭제되는 것은 아니다.

[총괄 #73](https://github.com/toilet-project/docs/issues/73) · [배포 #77](https://github.com/toilet-project/docs/issues/77) · [복구·감시 #78](https://github.com/toilet-project/docs/issues/78) · [현재 구조](../architecture/architecture-v4.md).
