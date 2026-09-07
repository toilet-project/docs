# Cloudflare Tunnel 운영 접속 인수 · 2026-09-07

## 현재 상태

운영 API·관리자 트래픽과 API/Batch/Admin의 실제 배포 연결을 Tunnel로 전환했습니다. 이후 공유기 교체로 내부망 대역이 변경되어도 Tunnel이 재연결되는 것을 확인했습니다. **개인 외부 SSH·Workbench는 앱/경로 설치와 최종 사용자 접속 검증을 구분합니다.**

| 경로 | 연결 / 보호 | 확인 범위 |
| --- | --- | --- |
| 공개 API | Cloudflare → Tunnel → 로컬 Nginx → API | 공개 회귀 9건·사용자 로그인 복귀 |
| 관리자 | 사용자 Access → Tunnel 원본 JWT 검증 → Nginx → 관리자 | 사용자 대시보드 진입; 앱 ADMIN 권한 검증 유지 |
| 제품 배포 | 저장소별 Service Auth → Tunnel → 전용 SSH → 기존 배포 작업 | Admin → API → Batch 실제 배포 성공 |
| 개인 SSH | 본인 이메일 Access → 원본 JWT 검증 → 별도 SSH → 기존 개인 키 | 외부 명령 실행 성공, 금지 목적지·원격 포워딩 차단 확인 |
| Workbench | 로컬 SSH 포워드 → MySQL loopback | 내부·외부 SSH 포워드의 MySQL handshake 확인; DB 계정 인증 대기 |

API와 관리자의 사용자 로그인 확인은 공급자 미지정 사용자 인수입니다. Google·Kakao 각각의 신규 인증/만료/권한 실패 시험이 모두 끝났다는 뜻은 아닙니다.

## 실제 배포 근거

- [Admin PR #76](https://github.com/toilet-project/toilet-admin-api/pull/76) · [운영 배포 성공](https://github.com/toilet-project/toilet-admin-api/actions/runs/34118030141)
- [API PR #92](https://github.com/toilet-project/toilet-api/pull/92) · [운영 배포 성공](https://github.com/toilet-project/toilet-api/actions/runs/34118250722)
- [Batch PR #42](https://github.com/toilet-project/toilet-batch/pull/42) · [운영 배포 성공](https://github.com/toilet-project/toilet-batch/actions/runs/34118468073)

이전 이미지와 배포 전 설정 복구 자료를 보존했습니다. 시간 제한 종료·재연결 시험과 격리 잠금 시험은 통과했지만 운영 장애 주입·실제 구버전 복구 시험과는 구분합니다. 이 전환에서 DB 스키마·업무 데이터는 수정하지 않았습니다.

## 내부망 변경과 복구 기준

- 고정 주소·gateway 의존을 DHCP로 전환한 뒤 공유기를 교체했습니다. 같은 물리 서버임을 SSH 호스트 키로 확인했습니다.
- 교체 후 내부 SSH, Tunnel 연결 4개, 공개 회귀 9건, 사용자 관리자 대시보드 진입을 확인했습니다. 서버 재부팅·컨테이너 재시작 없이 재연결했습니다.
- DHCP 고정 할당은 사용자 등록 확인입니다. 이후 재부팅·lease 갱신을 일부러 실행한 시험은 아닙니다.
- 전환 단계별 원복 타이머는 확정 후 비활성화했습니다. 상시 네트워크 장애 감시 장치가 아닙니다.
- 이전 네트워크 설정 백업은 이전 공유기용입니다. 새 공유기에 무조건 복원하지 않습니다. 내부망 IP/MAC·접속 계정·원본 설정은 비공개 인수 자료에 보관합니다.

## 개인 SSH와 Workbench

개인 Access 정책은 기존 본인 이메일 1개, 세션 6시간입니다. Tunnel 원본에서도 해당 앱의 JWT를 검증하며 SSH는 기존 개인 키로 별도 인증합니다. CI 서비스 토큰과 개인 Access 로그인을 공유하지 않습니다.

외부 Workbench는 먼저 OpenSSH로 로컬 포워드를 만든 뒤 **Standard TCP/IP**로 로컬 포트에 연결하는 방식을 사용합니다. 실제 호스트·키 경로를 포함한 실행 명령은 운영자 전용 인수 문서로 제공합니다.

| Workbench 항목 | 설정 |
| --- | --- |
| Connection Method | Standard TCP/IP |
| Hostname | 127.0.0.1 |
| Port | 운영자가 만든 로컬 포워드 포트 |
| Username / Password | 기존 MySQL 계정 / 해당 DB 비밀번호 |

SSH 포워드 터미널은 DB 작업 중 유지하고 종료 시 해당 터널만 닫습니다. DB 계정 비밀번호를 SSH 비밀번호나 Access 인증코드와 혼동하지 않습니다. 외부 MySQL 공개 포트를 만들지 않습니다.

개인 SSH 서비스의 포워딩은 서버 `127.0.0.1:3306` 목적지로 한정하며 원격·에이전트 포워딩은 금지합니다. **이는 SSH 포워딩 채널 제한이며, 권한 있는 관리자 셸의 명령 실행을 격리하는 샌드박스는 아닙니다.** 기존 내부망 SSH의 포워딩 설정은 이 전용 서비스와 다릅니다.

호스트 키 검사를 끄지 않습니다. Access 인증 중 위험 사이트 경고가 발생하면 우회하지 않고 중단합니다. 과거 재인증 성공을 Google 검토 완료나 오탐 확정으로 간주하지 않습니다.

공식 참고: [Workbench SSH](https://dev.mysql.com/doc/workbench/en/wb-mysql-connections-methods-ssh.html), [Standard TCP/IP](https://dev.mysql.com/doc/workbench/en/wb-mysql-connections-methods-standard.html), [Cloudflare 클라이언트 인증](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/non-http/cloudflared-authentication/arbitrary-tcp/).

## 남은 인수 · 운영 전환과 구분

- [x] 개인 Access 인증 후 외부 SSH 명령 실행·MySQL 포워드·금지 포워드 차단 확인
- [ ] 운영자 Workbench Test Connection으로 DB 인증 확인
- [ ] 공급자별 OAuth·권한/만료 세부 인수
- [ ] 실제 대상 인증서의 staging 갱신 승인 및 검증
- [ ] 다음 정기 배치 결과와 정기 타이머 결과 확인
- [ ] Tunnel 장애 감시·Discord 경로의 운영 적용/알림 인수 범위 확정
- [ ] 재부팅·실제 복구 시험의 실행 범위와 현장 복구 수단 확정
- [ ] 시험 토큰·키·앱·route·workflow의 대상별 보존/삭제 승인과 재검증
- [ ] 최신 전체 서비스 아키텍처 문서와 그림의 통합 갱신

기존 테스트 경로·복구 자료는 아직 삭제하지 않았습니다. 현재 커넥터 이름에 `test`가 포함돼 있어도 운영 경로를 함께 처리하므로 이름만 보고 삭제해서는 안 됩니다. 토큰 만료 알림 타이머가 존재하는 것과 Tunnel 전체 장애의 독립 외부 감시는 다른 항목입니다.

[전체 WBS #73](https://github.com/toilet-project/docs/issues/73) · [복구·감시·정리 #78](https://github.com/toilet-project/docs/issues/78).
