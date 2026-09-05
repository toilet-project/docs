# Next.js Workers 운영 전환 결과

2026-09-06 · WBS toilet-web #186 · 사용자 운영 전환 승인 후 실행

## 반영

- `geupddong.com/*`, `www.geupddong.com/*` 웹 경로를 운영 Worker로 연결했다. Pages 프로젝트·기존 정상 배포·DNS는 보존하고 Pages 자동 배포 중지도 유지했다.
- API [PR #83](https://github.com/toilet-project/toilet-api/pull/83)을 main에 병합하고 [배포](https://github.com/toilet-project/toilet-api/actions/runs/33979517356)를 완료했다. origin은 본 주소로 바꾸고 준비된 전용 서명 키를 선택했다. 기존 preview 키는 보존했다.
- 웹 [PR #187](https://github.com/toilet-project/toilet-web/pull/187) → [main 릴리스 #188](https://github.com/toilet-project/toilet-web/pull/188)을 반영했다.
- 사후 검증에서 발견한 데스크탑 상세 직접 접속 카드 가림을 [PR #189](https://github.com/toilet-project/toilet-web/pull/189)로 수정·main 병합·운영 재배포했다. 지도 SDK 준비 전 위치 계산이 끝난 뒤 다시 실행되지 않는 것이 원인이었다. 지도 준비/레이아웃 변경 시 재계산하고 준비 중 CSS 위치도 지도 영역으로 제한했다.
- 현재 웹 main `8f7122c`, API main `20923b3`. 실제 웹 배포는 [검증된 Linux PR 산출물](https://github.com/toilet-project/toilet-web/actions/runs/33980547208)이며 테스트 대상 트리와 보완 커밋 `422f3ae`의 차이가 없음을 확인했다.
- 5분 주기 Discord 외부 감시 대상을 본 주소로 전환했다. 기존 API/DB/OAuth 감시는 유지했다. Workers Free 유지, 자동 유료 변경 없음.

## 검증 근거와 범위

| 항목 | 결과 |
| --- | --- |
| 최신 웹 자동 검사 | 54개 테스트, lint/typecheck, preview/운영 후보 빌드, CodeQL 통과 |
| 본 주소/www | Next.js HTTP 200 확인 |
| 상세 SEO | 화장실명·지역명 title, canonical, Place JSON-LD, 잘못된 ID 404 확인 |
| 사이트맵 | 6개 화장실 shard, 중복 없는 53,583개 URL 확인. 전국 상세 페이지를 강제 생성한 것은 아님 |
| 검색 정책 | 운영 robots 검색 허용·사이트맵 안내, preview noindex 및 Disallow 유지 |
| 운영 화면 자동 회귀 | Chromium 375×667, 390×844, 430×932, 1440×1000 모두 통과. 지도/상세/로그인 유도/닫기/뒤로·앞으로/지도 DOM 유지, pageerror 0 |
| 실제 브라우저 | 기존 로그인 유지, 목록 선택 후 상세 URL, 로그인 상태 제보 유형 화면 진입 확인. 접수하지 않음 |
| 신규 가입 복귀 | 전환 전 preview에서 사용자 확인. 제공자별 실제 가입 전체 조합을 검증한 것으로 확대하지 않음 |
| OAuth 경로 | Google/Kakao 시작 및 취소 복귀 302, provider callback 유지, 임의 외부 return 400. 새 실제 로그인 완료와 구분 |
| 캐시 자동 전송 | 원본 변경 없는 확인 이벤트가 Spring에서 전송되어 새 운영 빌드 D1 태그 저장·ACK 확인, 약 2.5초, 잔여 큐 0 |
| 캐시 재생성 | 갱신 후 상세가 MISS로 재생성됨. 원본 화장실·좌표 fingerprint 불변 |
| 외부 모니터 | 운영 홈/상세 200·OK, service 성공, timer active 확인 |

운영 UI 자동 점검은 별도 브라우저에서 모든 쓰기 요청을 차단했다. 테스트용 계정 생성·약관 동의·제보 접수·정상 화장실 수정은 하지 않았다. 확인 이벤트만 cache outbox에 넣었고 실제 사용자 이벤트를 삭제/대체하지 않았다.

## 재배포·복구

빌드 후보 설정에는 공개 경로가 없으므로 운영 중 일반 deploy로 덮어쓰지 않는다. 검증된 산출물에서 실제 수행한 경로 유지 명령은 다음과 같다.

```sh
opennextjs-cloudflare deploy --config wrangler.production.jsonc --cacheChunkSize 5 -- --routes 'geupddong.com/*' 'www.geupddong.com/*'
```

업로드 전에 대상·커밋·설정 해시·빌드 ID를 검증하고 운영 자원 및 키를 확인한다. 전국 상세 캐시는 미리 생성하지 않는다. 경로만 관리할 때는 웹 저장소의 `wrangler.production.routes.jsonc`를 triggers 전용으로 사용한다.

전환 철회 시 추가한 root/www Route만 해제하고 보존한 Pages 정상 배포로 복구되는지 확인한다. API cache origin/키 선택과 감시 대상도 함께 검토한다. 큐·원본 데이터·기존 키·다른 서비스 DNS는 삭제하지 않는다. 실제 장애를 유발하는 rollback 리허설은 하지 않았다.

## 남은 운영 관찰

- Free CPU/요청 한도와 R2/D1 사용량 관찰. 외부 2개 표본과 주기 알림은 모든 사용자 오류를 수집하지 못한다.
- 실제 iPhone의 최종 본 도메인 확인 및 제공자별 신규 로그인 실사용은 사용자 확인으로 보강할 수 있다. Chromium 결과를 Safari 전 기능 검증으로 표현하지 않는다.
- 후속 CI가 자동으로 운영 Worker를 배포하는 구조는 이번에 추가하지 않았다. Pages 자동 배포도 재활성화하지 않는다.
