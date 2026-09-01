# 운영 안정화 Runbook v1.1

## 운영 목표

| 항목 | 기준 |
|---|---|
| DB 백업 | 매일 03:15 KST, AES-256 암호화, 14일 보관 |
| 복구 검증 | 월 1회 이상 임시 MySQL 컨테이너로 전체 복구 |
| 배치 실행 | 매일 02:00 KST, 외부 API 요청 최대 3회 재시도 |
| 장애 알림 | 최종 재시도 실패 후 운영 Webhook 전송 |
| 컨테이너 로그 | 컨테이너별 10MB × 5개 순환 |
| 관측 | health, Prometheus 지표, 관리자 상태 요약 |
| 자동 점검 | 부팅 90초 후 및 5분마다 API·DB·OAuth·컨테이너 확인 |

## 백업 정책

- 운영 스크립트: `operations/scripts/mysql-backup.sh`
- 기본 저장 위치: `/home/luha/backups/geupddong/mysql`
- 암호화 키: `/home/luha/.config/geupddong/backup.key` (`600` 권한)
- 백업·체크섬 파일도 소유자만 읽도록 `600`으로 제한한다.
- DB 비밀번호와 암호화 키는 로그·문서·Git에 기록하지 않는다.
- 현재 백업은 운영 DB와 같은 물리 디스크에 있으므로 실수·논리 장애 복구에는 유효하지만 디스크 고장에는 취약하다. 외부 저장소가 확정되면 암호화된 결과만 2차 복제한다.

### 자동 실행

Mini PC에는 사용자 `cron` 명령이 없어 systemd timer를 사용한다. `geupddong-mysql-backup.timer`는 재부팅 후에도 자동 복구되며, 전원이 꺼져 예약 시각을 놓치면 `Persistent=true` 설정으로 다음 부팅 시 실행한다.

백업 서비스는 운영 런타임인 `snap.docker.dockerd.service`만 의존한다. 일반 `docker.service`를 의존성에 추가하면 Snap Docker와 이중 실행될 수 있으므로 금지하며, 일반 Docker service/socket은 `masked` 상태를 유지한다.

```text
매일 03:15 Asia/Seoul → geupddong-mysql-backup.service
```

### 복구 리허설

`mysql-restore-verify.sh`는 운영 DB를 변경하지 않는다. 임시 `mysql:8.0` 컨테이너에 최신 백업을 복구하고 테이블 수와 화장실 데이터 수를 검사한 뒤 컨테이너를 삭제한다.

## 배치 실패 대응

1. 관리자 화면의 정기 배치 상태와 배치 실행 이력을 확인한다.
2. 실패 이력의 오류 유형과 발생 시각을 확인한다. 알림에는 비밀값·원문 API 응답을 넣지 않는다.
3. 공공데이터 API·카카오 API 상태와 일일 한도를 확인한다.
4. 원인을 해결한 뒤 수동 동기화를 실행하고 성공 이력·데이터 건수를 검증한다.
5. 장애 원인과 재발 방지 조치를 WBS 실행 결과에 기록한다.

## 서비스 장애 대응

1. 관리자 운영 현황의 API·DB·배치·디스크 상태를 확인한다.
2. `docker ps`와 해당 컨테이너의 최근 순환 로그를 확인한다.
3. health가 실패하면 `docker compose up -d`로 해당 서비스만 정상화한다.
4. DB 장애 시 최근 백업의 체크섬과 복구 리허설 결과를 먼저 확인한다.
5. 운영 DB 복구는 별도 보존본 생성 후, 점검 시간을 공지하고 수행한다.

## 재부팅 후 자동 점검과 장애 알림

`geupddong-health-monitor.timer`는 부팅 90초 후 처음 실행되고 이후 5분마다 다음 항목을 검사한다.

- Snap Docker 활성 및 일반 systemd Docker 비활성
- API·Admin·Batch·MySQL·Redis·Portainer 실행 상태
- Redis health 상태
- 내부·외부 API health의 DB 연결 결과
- Google·Kakao OAuth 시작 경로의 302 및 제공자 도메인
- Nginx 접근 로그에 새로 발생한 OAuth callback 5xx

실패 내용이 바뀐 경우에만 기존 `BATCH_FAILURE_WEBHOOK_URL` Discord Webhook으로 알리고, 정상 복구 시 한 번 복구 메시지를 보낸다. 비밀번호, OAuth code, 전체 요청 URL과 사용자 정보는 알림에 포함하지 않는다.

운영 파일은 다음과 같이 설치한다.

```text
operations/scripts/service-health-monitor.sh
  → /home/luha/.local/bin/service-health-monitor.sh
operations/systemd/geupddong-health-monitor.service
  → /etc/systemd/system/geupddong-health-monitor.service
operations/systemd/geupddong-health-monitor.timer
  → /etc/systemd/system/geupddong-health-monitor.timer
```

점검 명령은 다음과 같다.

```bash
systemctl status geupddong-health-monitor.timer
systemctl status geupddong-health-monitor.service
journalctl -u geupddong-health-monitor.service --since today
```

## 지표 및 보관

- `/actuator/health`만 공개 상태 확인에 사용한다.
- `/actuator/prometheus`는 Mini PC 내부 또는 관리자 접근 경계 안에서만 수집한다.
- HTTP 응답 시간은 100ms·250ms·500ms·1s·2s 구간으로 관측한다.
- 운영 애플리케이션의 SQL 출력은 비활성화하여 개인정보와 쿼리 인자 노출을 줄인다.
- Docker `json-file` 로그는 서비스별 50MB 이내로 순환한다.
- MySQL compose에는 비밀번호 값을 직접 쓰지 않고 소유자 전용 `.env`를 연결한다.

## 비밀정보 점검

- GitHub Secret과 Mini PC `.env`만 런타임 비밀값 저장소로 사용한다.
- Webhook 본문에는 작업명, 시간, 재시도 횟수, 오류 클래스만 포함한다.
- DB 비밀번호, OAuth/JWT 키, 공공데이터 키, 이메일과 제보 원문은 운영 로그에 남기지 않는다.
