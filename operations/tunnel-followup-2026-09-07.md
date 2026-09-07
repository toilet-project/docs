# Tunnel 전환 후속 점검 · 2026-09-07

> 후속 갱신: 아래는 9월7일 인수 당시 기록이다. 9월8일에는 운영 인증12건·격리29건과 독립 외부 감시 설치·Discord 저장 확인까지 추가 완료했다. 독립 감시 미설치 문구의 최신 상태는 [9월8일 보고서](tunnel-safe-acceptance-2026-09-08.md)를 따른다. 실제 장애 주입과 미래 정기 실행은 별도 미완료다.

## 오늘 확인한 결과

| 항목 | 결과 | 경계 |
| --- | --- | --- |
| 운영 API/Admin/Batch 배포 | 세 제품 실제 Tunnel 배포 성공 | 구버전 rollback 실행은 별도 |
| 공유기 교체·재부팅 | DHCP 유지·서비스 자동 복귀, 수정 후 배포 SSH 재시도0 | 첫 부팅 오류와 수정 후 성공을 구분 |
| 개인 외부 SSH | 사용자 Access 후 명령 실행 성공 | 본인 계정/개인 키 사용 |
| MySQL 포워드 | 내부·외부 경로 protocol10 응답 | MySQL 공개 포트 추가 없음 |
| 포워딩 제한 | MySQL 외 목적지와 remote forwarding 거부 | 관리자 셸 권한의 sandbox 아님 |
| DB 인증 | 서버 읽기 인증 성공 및 사용자 Workbench Test Connection 성공 확인 | 비밀번호 변경 없음 |
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

1. Workbench GUI 연결 — **완료**, 사용자 성공 확인.
2. API 인증서 staging dry-run — **완료**, 운영 인증서·설정 불변 확인.
3. 건강 점검 설치와 시험 알림1건 — **완료**, 다음 5분 정기 실행까지 확인.
4. Google 관리자 새 앱 로그인과 대시보드·배치 이력·제보 검토 조회 — **완료**. Kakao·쿠키/만료·비허용 계정 세부 인수는 별도이며 실제 제보/탈퇴 실행 없음.
5. 다음 정기 실행 확인 — 02:00 배치, 03:15 백업, 03:35 복원 점검, 04:15 이후 보관 점검, 09:00 이후 만료 점검(KST, 일부 jitter).
6. **시험 자원 정리 완료.** docs 시험 Secrets4개·서버 시험키1줄 제거 및 시험 workflow/listener 비활성화에 이어, 재연결 후 별도 최종 승인을 받아 Cloudflare 시험 경로4개·DNS4개·Access 앱3개·전용 CI 정책1개·시험 토큰1개를 제거했다. 운영 Tunnel/공용 본인 허용 정책/배포 토큰/개인 키/복구 자료는 보존했다.
7. 22:53 KST 첫 재부팅에서 배포 SSH의 런타임 디렉터리 생성 순서 오류를 발견했다. 수정 후 추가 승인한 23:07 KST 두 번째 재부팅에서 배포 SSH 자동 시작·재시도0·실패 유닛0을 확인했다. 실제 구버전 복구·호스트 전체 장애 독립 감시는 별도로 남아 있다.

## 재부팅·정리의 검증 경계

첫 재부팅 후 배포 SSH만 복구했고 개인 Access SSH·내부 포워드 배포 SSH 인증과 23:00 KST 정기 감시 종료0을 확인했다. 첫 부팅의 API 준비 초기에는 연결 reset이 있어 무중단이 아니다.

두 번째 재부팅은 새 부팅 ID, 동일 DHCP 예약 주소, 컨테이너6개, Tunnel4연결과 배포 SSH 자동 기동을 확인했다. 배포 SSH NRestarts=0·ExecMainStatus=0, 개인 Access SSH/내부 포워드 배포 SSH 인증, 관리자 health UP·DB 읽기 인증·공개 회귀9건 통과다. MySQL·전용 SSH의 loopback 수신과 native Docker masked도 유지했다. 이는 GitHub runner의 새 Service Auth 인수·사용자 로그인 완료를 대신하지 않는다.

두 번째 재부팅 후 첫 정기 건강 점검은 23:09:20 KST 종료0/Result=success로 완료됐고 실패 유닛0을 다시 확인했다.

시험 키는 원본을 비공개 백업하고 정확히1줄만 제거했다. 나머지 키의 바이트·권한·소유자는 보존했다. 삭제된 GitHub 시험 Secrets는 복원이 아닌 재발급이 필요하다. 시험 workflow 실행 기록과 운영 자격증명은 보존했다.

### Cloudflare 시험 자원 정리 결과

시험 route 삭제 후 DNS 목록에서도 해당4개가 사라진 것을 확인했다. Access 앱3개를 먼저 제거한 뒤 시험 CI 정책의 연결 앱0개를 확인하고 정책·시험 토큰을 삭제했다. 공유 정책과 운영 자격증명은 변경하지 않았다.

최종 목록은 운영 Tunnel 경로4개, DNS 전체13개(웹·메일 포함), Access 앱3개, 정책2개, 배포 토큰3개다. 배포 토큰은 모두 Enabled·5년 설정을 유지했다. 삭제한 시험 토큰은 복원이 아닌 재발급 대상이다. 로컬 시험 파일·서버의 비공개 복구 자료는 이번에 삭제하지 않았다.

삭제 직후 공개 회귀9건, 개인 외부 Access SSH 접속, 운영 Tunnel·개인/배포 SSH 활성 상태, 컨테이너6개 및 실패 유닛0개를 확인했다. 이후의 인증 재인수는 아래와 구분한다.

### 정리 후 Google 관리자 로그인·정기 감시 재확인

사용자가 Google로 새 관리자 로그인을 완료했다고 명시했다. 브라우저에서 로그인 전 관리자 로그인 화면, 로그인 후 대시보드·배치 이력·제보 검토의 인증된 읽기 조회를 확인했다. Google 공급자 SSO 세션 자체를 강제로 종료한 시험은 아니며, 로그인 완료 쿠키 전체·Kakao·로그아웃/만료·비허용 계정의 동작까지 검증한 것은 아니다. 업무 데이터는 변경하지 않았다.

23:50:25 KST 건강 감시와 Workers 감시의 실행 종료0/Result=success를 확인했다. 다음 백업은 9월8일03:15, 격리 복원 점검03:35, 보관 점검04:15:10 KST로 활성 예약돼 있다. 미래 실행 결과와 보관 보류 해소는 아직 완료 처리하지 않는다. GitHub의 감시 관련 workflow는 테스트용이며 독립 외부 상시 감시 설치로 해석하지 않는다.

### 정리 후 저장소별 CI 인증 재인수 — 모두 성공

기존 검토된 읽기 전용 workflow를 attempt2로 재실행했다. 서비스 토큰·SSH 키·고정 호스트 키 인증, 원격 종료코드23 전달, 600초 client timeout(124), 새 연결 재접속과 runner 임시 인증 파일 정리가 세 저장소 모두 성공했다. 공유 Tunnel 자체를 중단하거나 실제 배포를 실행하지 않았다.

| 저장소 | 실행 근거 | 완료 시각(KST) |
| --- | --- | --- |
| API | [attempt2](https://github.com/toilet-project/toilet-api/actions/runs/34117093613/attempts/2) | 9월7일23:59:28 |
| Batch | [attempt2](https://github.com/toilet-project/toilet-batch/actions/runs/34117092137/attempts/2) | 9월7일23:59:28 |
| Admin | [attempt2](https://github.com/toilet-project/toilet-admin-api/actions/runs/34117091310/attempts/2) | 9월8일00:00:05 |

새 관리자 Google 로그인과 runner 재인수는 완료다. Kakao·세션/권한 세부 시험, 다음 정기 실행, 실제 장애/rollback·독립 외부 감시는 여전히 남아 있다.

미래의 정기 실행·사용자 확인·별도 승인 항목을 완료 체크하지 않는다. 기존 토큰/키가 만료돼도 자동으로 Secrets나 로컬 파일이 삭제되는 것은 아니다.

[총괄 #73](https://github.com/toilet-project/docs/issues/73) · [배포 #77](https://github.com/toilet-project/docs/issues/77) · [복구·감시 #78](https://github.com/toilet-project/docs/issues/78) · [현재 구조](../architecture/architecture-v4.md).
