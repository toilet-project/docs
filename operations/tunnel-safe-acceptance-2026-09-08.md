# Tunnel 후속 인증·독립 외부 감시 인수 · 2026-09-08

## 확인한 결과

운영 데이터 변경 없이 인증 회귀 12건과 격리 인증 테스트 29건을 통과했다. 미니 PC 밖의 GitHub-hosted runner에 외부 접속 감시를 설치했으며, Discord 메시지 저장 확인과 정상 무알림 점검·상태 저장을 검증했다. 실제 장애 주입·서비스 재시작·계정 변경·유료 전환은 하지 않았다.

| 검증 | 결과 | 범위와 한계 |
| --- | --- | --- |
| 운영 인증 회귀 | 12 PASS | 익명/잘못된 토큰 401, 허용 CORS 200, 비허용 CORS 403, 토큰 없는 refresh 401, 쿠키 없는 logout 204 및 삭제 속성 |
| 격리 인증 | 29 PASS, 실패·오류·건너뜀 0 | 운영과 동일한 인증 소스. 실제 DB·Redis·소셜 공급자 사용 안 함 |
| 외부 감시 격리 시험 | 45 PASS | 실패·복구·중복 억제·상태 유실·차단 비우회·비밀값 비출력·Discord 저장 확인 |
| 추가 승인한 Discord 시험 | HTTP 200, 저장 확인 true | [실행 34139491297](https://github.com/toilet-project/docs/actions/runs/34139491297), 테스트 메시지 1건 |
| 정상 monitor | 웹/API 200·OK, healthy=true, notification=none | [실행 34139568956](https://github.com/toilet-project/docs/actions/runs/34139568956), 최초 상태 cache 저장 성공 |

쿠키 없는 logout 검사는 실제 사용자의 세션을 폐기하지 않는다. 격리 ADMIN/토큰 시험은 실제 비관리자 계정·브라우저 만료 인수를 대체하지 않는다.

## 감시 흐름

```text
GitHub-hosted runner (10분 간격 예약, 지연 가능)
  ├─ 공개 웹 HEAD ────────────────┐
  └─ API·DB health GET (no-store) ┤
                                ↓
                    상태 분류 · 실패만 재확인
                                ↓
           이전 전달 상태 cache와 비교 (영구 저장소 아님)
                ├─ 정상 유지 → 알림 없음
                ├─ 신규/변경 장애·1시간 지속 → Discord
                └─ 장애 후 정상 복귀 → Discord
                                ↓
                저장 확인 후 알림 상태 갱신
                    + 비밀값 없는 결과 artifact
```

미니 PC가 꺼져도 실행 위치는 별개지만, 웹/API 실패만으로 호스트 고장인지 네트워크·Cloudflare 문제인지 단정하지 않는다. 원인 자동 판정·자동 복구는 하지 않는다. GitHub/Discord 장애까지 독립적인 다중 공급자 감시는 아니다.

## 전송 보완과 실행 근거

- [PR #85](https://github.com/toilet-project/docs/pull/85): 고정 공개 URL·무인증 probe, cache 기반 알림 상태, 제한 권한 workflow.
- [PR #86](https://github.com/toilet-project/docs/pull/86): main/활성화 조건 검증과 Secret 입력 공백 정리.
- 첫 [시험 34138560460](https://github.com/toilet-project/docs/actions/runs/34138560460)은 전달 성공을 확인하지 못해 감시를 중지했다. 당시 HTTP 상태를 수집하지 않아 첫 실패 원인을 확정할 수 없다.
- [PR #87](https://github.com/toilet-project/docs/pull/87): 공식 Discord 클라이언트 식별 헤더, `wait=true` 저장 확인, HTTP 상태만 기록. 추가 승인한 테스트가 성공한 뒤 정상 감시를 확인했다. 웹/API probe의 신원을 바꾸거나 접근 차단을 우회하지 않았다.
- 전용 Secret과 활성 변수로 분리하고 fork/PR에 Secret을 전달하지 않는다. 실제 값·응답 원문·메시지 ID는 로그에 남기지 않는다.

## 완료하지 않은 항목

- 첫 예약 실행 및 다음 정기 배치·백업·격리 복원·보관 점검 결과: 실제 실행 후 확인한다.
- Kakao 새 로그인, 실제 비허용/비관리자 계정, 로그인된 세션의 만료·로그아웃 브라우저 전환: 사용자 참여 필요.
- 운영 호스트 장애 주입·실제 구버전 rollback·배포 중 연결 단절/토큰 만료 재현: 별도 승인 필요.
- `HOLD_LEGACY_METADATA`는 기존 백업 삭제 보류이며 이번 감시 설치로 해소되지 않는다.

예약 지연/누락·60일 비활성 중단, cache 유실에 따른 중복/복구 알림 누락 가능성을 [운영 가이드](external-monitor/README.md)에 기록했다. workflow 성공과 서비스 정상은 다르므로 artifact의 `healthy`·`checks`도 확인한다. 정지하려면 `EXTERNAL_MONITOR_ENABLED=false`로 바꾸며 기존 서버 감시와 배포는 유지한다.

[총괄 WBS #73](https://github.com/toilet-project/docs/issues/73) · [운영 감시 WBS #78](https://github.com/toilet-project/docs/issues/78)
