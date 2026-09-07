# 독립 외부 접속 감시

미니 PC와 다른 실행 환경인 GitHub-hosted runner에서 공개 웹과 API를 점검한다. 미니 PC가 꺼져도 실행할 수 있지만 GitHub·Discord까지 독립적인 다중 공급자 감시를 보장하지는 않는다. 서비스 재시작·SSH·DB 쓰기·유료 전환은 하지 않는다.

## 흐름

```text
GitHub 예약 실행 (매시 07·17·27·37·47·57분 UTC)
  → 웹 HEAD / API·DB health GET (인증 없이, 고정 HTTPS URL)
  → 실패만 5초 후 재확인 (Access 차단은 재요청·우회하지 않음)
  → 분류 + 이전 알림 상태 비교
  → 신규/변경 장애 또는 1시간 지속: Discord
  → 정상 복귀: Discord
  → 상태 cache / 비밀값 없는 결과 artifact
```

| 대상 | 기준 / 한계 |
| --- | --- |
| 공개 웹 | HEAD 200 + HTML Content-Type. 실제 화면 렌더링·지도·로그인은 검증하지 않음 |
| API·DB | GET 200 + 고정 health 본문 + no-store; HIT/STALE/양의 Age는 정상으로 인정하지 않음 |
| Access/403/challenge | ACCESS_BLOCKED로 알림. UA 변경·보안 해제·인증 우회 없음 |
| 일시 실패 후 성공 | FLAPPING. 완전 복구로 오인하지 않음 |
| DNS/TLS/시간 초과 | 안전한 분류만 기록. 원본 응답·토큰·쿠키·내부 주소는 기록하지 않음 |

## 실행과 권한

- `probe`: 두 공개 URL 검사만 한다. Discord 비밀값을 전달하지 않고 incident 상태를 저장하지 않는다.
- `monitor`: `toilet-project/docs`의 `main` + `EXTERNAL_MONITOR_ENABLED=true`일 때만 알림 가능.
- `notification-test`: 위 활성 조건에서 승인된 연결 테스트 메시지 한 건. incident 상태에 영향 없음. 임의 재실행은 추가 알림이므로 별도 승인.
- Secret: `DISCORD_EXTERNAL_MONITOR_WEBHOOK`; 저장소 전용이고 fork/PR 테스트에는 전달하지 않는다.
- repository variable: `EXTERNAL_MONITOR_ENABLED`; 누락/false이면 예약 작업은 건너뛴다.
- GitHub 토큰은 contents:read. 체크아웃 자격증명 저장 안 함. 공식 Actions 커밋 고정, 작업 timeout4분.
- 비밀값 없는 summary artifact7일 보관. cache에는 알림 분류·시각만 저장한다.

동일 main 감시는 concurrency로 직렬화한다. 전송 성공 후에만 알림 상태를 확인 처리하므로 전송 실패는 다음 실행에서 재시도한다. 전송은 성공했으나 후속 저장이 실패하면 중복 알림이 가능하다. 정확히 한 번 전송을 보장하지 않는다.

cache는 영구 저장소가 아니다. 유실·손상·3일 이상 오래된 상태는 초기화하며 결과에 표시한다. 장애 중 cache가 없어지면 새 장애 알림이 중복될 수 있고, 정상 복귀 시 이전 장애 알림 상태가 없으면 복구 알림을 놓칠 수 있다. 알림 상태 유실이 공개 서비스 정상 판정을 바꾸지는 않는다. cache 복원 실패도 실제 probe를 건너뛰지 않는다.

**workflow success는 검사/알림 처리 성공이지 서비스 정상이라는 뜻이 아니다.** 결과 artifact의 `healthy`·`checks`와 Discord를 함께 본다. 웹훅 전송 실패는 job 실패로 표시한다. 서비스가 비정상이어도 Discord 전달이 성공했다면 감시 job 자체는 성공할 수 있다.

## 운영 인수·중지

Discord 요청은 공식 규격의 `DiscordBot` 클라이언트 식별 헤더를 사용하며, `wait=true`의 HTTP 200 및 저장된 메시지 응답을 확인한 후에만 성공으로 기록한다. 로그에는 HTTP 상태와 확인 여부만 남기고 웹훅 URL·응답 원문·메시지 ID는 출력하지 않는다. [Discord API 규격](https://docs.discord.com/developers/reference), [웹훅 저장 확인](https://docs.discord.com/developers/resources/webhook).

1. 격리 테스트 → 무알림 로컬 공개 probe → PR CI.
2. 승인 범위에서 main 병합 → 전용 Secret 등록 → 활성 변수 true.
3. `probe`의 GitHub 외부 실접속 확인 → 승인된 테스트 알림1건 → 수동 `monitor` → 첫 정기 실행 확인.
4. 중지할 때 변수 false 또는 해당 workflow만 disable. 기존 미니 PC 감시·배포 workflow는 유지한다.

GitHub 예약은 부하에 따라 지연되거나 누락될 수 있고, 공개 저장소는 60일 비활성 시 예약이 자동 비활성화된다. 10분 SLA나 호스트 장애를 정확히10분 이내 탐지한다고 보장하지 않는다. GitHub Actions 알림도 켜 두고 실행 시각·설정 상태를 정기 점검해야 한다. 더 강한 보장이 필요하면 별도 uptime 공급자를 추가하는 작업이다. 현재 구현은 유료 서비스 가입을 하지 않는다.

근거: [GitHub 예약 제약](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [예약 비활성화](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow), [cache 보존 제약](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows), [artifact 보관](https://docs.github.com/en/actions/tutorials/store-and-share-data).

## 테스트

`python -m unittest discover -s operations/external-monitor -p 'test_*.py' -v`

API cache·본문·상태, 웹 HEAD, 차단 비우회, TLS/timeout, bounded 재시도, cache 손상/시간, 알림 중복/변경/복구/실패 재시도, webhook 목적지 제한·redirect 금지·mentions 비활성·비밀값 비출력을 격리 검증한다. 실제 서버 장애 주입 시험은 별도다.
