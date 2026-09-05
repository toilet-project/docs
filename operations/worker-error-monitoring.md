# Workers 외부 오류 감시와 Discord 알림

2026-09-06 · 무료 플랜 유지 · 자동 유료 전환 없음

## 범위

Worker의 CPU/메모리 한도 초과는 실행 자체를 중단할 수 있으므로 Worker 내부 catch에만 의존하지 않는다. 미니 PC의 별도 systemd timer가 5분마다 preview 홈과 상세 표본을 외부 HTTPS GET으로 확인한다. 기존 API/DB/OAuth 감시와는 별도의 서비스·상태다.

- 현재 대상: `https://preview.geupddong.com`. 본 도메인 전환 전 운영 감시 완료라고 표시하지 않는다.
- 운영 전환 시 `GEUPDDONG_WORKER_ORIGIN`을 승인된 본 도메인으로 변경하고 다시 검증한다. 두 origin만 코드에서 허용한다.
- 외부 요청은 회당 2건, 요청별 timeout 10초, redirect 따라가지 않음. 상태 판별용 본문은 최대 64KiB만 읽고 폐기한다.
- 표본의 지속적 오류를 탐지하는 감시다. 모든 사용자·모든 상세의 순간적인 오류를 수집하지 못하며, 감시 PC/네트워크가 함께 멈추면 알림도 불가능하다. Cloudflare 로그와 오류 지표도 함께 확인해야 한다.

## 분류와 알림

| 감지 | 처리 |
| --- | --- |
| 오류 응답의 Cloudflare 1102 | CPU 또는 메모리 리소스 한도로 분류, 첫 감지 즉시 알림 |
| 오류 응답의 Cloudflare 1027 | 요청 한도로 분류, 첫 감지 즉시 알림 |
| 429 | 별도 rate limit으로 분류; Workers 요금제 한도라고 단정하지 않음 |
| 401/403 | 접근 정책 차단으로 분류 |
| 5xx, 통신 실패, 비정상 HTTP/내용 | 연속 2회 실패 후 알림 |
| 알림 이후 연속 2회 정상 | 복구 알림 |

‘즉시’는 **다음 5분 주기 점검에서 첫 감지 즉시**라는 의미다. 동일 장애는 30분 간격으로 재알림하고 분류가 바뀌면 다시 알린다. Discord 수락 성공 후에만 전송 완료 상태를 저장하므로 전송 실패 시 다음 주기에 재시도한다. 원인 해결 없이 무조건 Paid로 전환하지 않는다. 특히 1102는 CPU뿐 아니라 메모리도 포함한다.

## 로그·보안

- 상태/로그는 감시 사용자 전용 디렉터리, 디렉터리 700·파일 600 기준으로 관리한다.
- 매 점검 시 KST 시각, 공개 대상 경로, HTTP 상태, 오류 분류, 응답 시간, 알림 수락/재시도 여부를 JSONL로 저장한다.
- 현재 로그 약 1MiB와 순환본 2개로 제한한다. 가장 오래된 순환 로그는 교체된다. 장기 보관 시스템은 아니다.
- 응답 본문, OAuth 코드/쿠키, webhook 값은 로그에 남기지 않는다. Discord mention도 비활성화한다.
- 기존 Discord webhook 설정 파일의 한 값을 데이터로 읽으며 `.env`를 source/실행하지 않는다. 별도 외부 서비스나 Cloudflare 토큰을 추가하지 않는다.
- 중복 실행은 파일 lock, 상태 저장은 임시 파일 후 원자적 교체를 사용한다. 재부팅 후에도 기존 전송 상태를 유지한다.

## 파일·운영 명령

- `scripts/worker-health-monitor.py`
- `systemd/geupddong-worker-monitor.service`
- `systemd/geupddong-worker-monitor.timer`
- `tests/test_worker_health_monitor.py`

검증: `python3 -m unittest discover -s operations/tests -v` (Linux Python 표준 라이브러리만 필요).

설치된 스크립트에 `--dry-run`을 주면 공개 요청만 확인하며 상태/Discord는 변경하지 않는다. `--test-notification`은 실제 장애가 아님을 명시한 테스트 메시지 한 건을 보내고 장애 상태는 바꾸지 않는다.

상태 확인: `systemctl status geupddong-worker-monitor.timer`, 최근 실행 확인: `journalctl -u geupddong-worker-monitor.service -n 20 --no-pager`.

해제: `sudo systemctl disable --now geupddong-worker-monitor.timer`. 이미 실행 중인 단발 점검은 완료될 수 있으며, 즉시 중단해야 하면 service도 중지한다. 기존 운영 감시와 캐시 전송기, 업무 DB는 변경하지 않는다. 로그/상태/설치 파일은 자동 삭제하지 않는다.

## 검증 기록

격리 임시 디렉터리에서 16개 테스트 통과: 정상/1102/1027/429/403/5xx 분류, 일반 시설 번호 오인 방지, 연속 실패·복구, 중복 억제·30분 재알림, Discord 실패 재시도, 상태 저장/재시작, 로그 순환, webhook 목적지 검증, 예외 비밀값 미출력.

미니 PC의 실제 preview 홈·상세 표본 dry-run은 모두 200이었다. 운영 장애를 인위적으로 만들거나 업무 데이터를 수정하지 않았다. 실제 설치와 테스트 알림 결과는 설치 후 별도 기록한다.

### 설치 결과

2026-09-06 KST에 독립 service/timer를 설치·활성화했다. systemd 설정 검증과 첫 실행이 성공했고, 실제 두 경로는 모두 200/OK였다. 재부팅 후 시작과 5분 주기 다음 실행 예약을 확인했다. 기존 API/DB/OAuth 감시 타이머도 계속 active다.

실제 Discord 테스트 전송은 성공 응답을 받았다. 이는 webhook 수락 확인이며 사용자의 Discord 앱 열람 확인과는 구분한다. 실제 장애를 발생시키는 테스트는 하지 않았다. 플랜/본 도메인/업무 DB·컨테이너 재시작은 변경하지 않았다.
