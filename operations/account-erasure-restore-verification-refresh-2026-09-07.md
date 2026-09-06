# 최근 복원 검증본 갱신 도구

2026-09-07. **feature 구현·합성 테스트 단계이며 운영 설치, 추가 복원, 예약 변경은 하지 않았다.** 기존 03:15 백업·04:15 삭제 없는 점검·04:20 일회성 상태 확인은 이번 변경 대상이 아니다.

## 목적과 범위

현재 점검 설정의 `GEUPDDONG_RESTORE_VERIFIED_BACKUP_SHA256`는 실제 복원했던 백업 하나를 가리킨다. 새 백업이 생성됐다는 이유로 이 값을 바꾸면 복원 가능성을 검증하지 않은 백업을 보호 기준으로 삼게 된다.

[갱신 도구](scripts/refresh-restore-verification.py)는 기존 [격리 복원 도구](scripts/verify-live-backup-isolated.py)가 생성한 private `result.json`을 검사한 뒤 이 설정 **한 항목만** 교체한다. 기본 실행은 dry-run이다. DB/R2/네트워크 접근과 백업 삭제는 없다. 이 도구 자체는 복원을 실행하거나 주기적으로 예약하지 않는다.

## 갱신 조건

- 독립적으로 지정한 결과 파일 SHA-256과 현재 보호 백업 SHA-256이 실제 파일/설정과 일치.
- 복원 성공, FK 고아 0건, 원본 백업/metadata 미변경, 임시 컨테이너 정리 완료.
- V11 가상 파기 모드라면 격리 네트워크 정리·원본 데이터 보존·가상 fixture 제거·충돌 원자성·미지 FK 롤백·멱등 검증까지 통과.
- metadata의 DB명·서버 UUID·복원 세대가 현재 비공개 운영 설정과 일치.
- 실제 암호화 백업의 크기·SHA-256, 동반 checksum, metadata hash, 복원 결과의 대상이 모두 일치.
- 백업 캡처 종료 후 **36시간 이내**, 복원 검증 종료 후 **1시간 이내**. 미래 시각·역전·timezone 없는 시각 거부.
- 현재 보호 백업이 실제로 남아 있고, 후보가 그 백업보다 오래된 캡처가 아님.
- 소유자 전용 디렉터리/파일, 심볼릭 링크 차단, 기존 `.backup.lock`의 실제 배타 잠금 확보.

36시간은 **복원 시험 시각이 아니라 백업의 캡처 종료 시각** 기준이다. 오래된 백업을 다시 시험해 이 신선도 조건을 연장할 수 없다. metadata 없는 legacy 백업의 보류도 이 도구로 해제되지 않는다.

## 운영 적용 시 절차 — 아직 미실행

1. 별도 승인된 실제 격리 복원을 실행하고 원래 생성된 `result.json`을 소유자 전용 폴더에 보존한다. 과거 요약 보고서를 결과 JSON으로 재구성하지 않는다.
2. 원본 결과 hash와 현재 보호 hash를 확인하고, 백업 폴더 밖에 소유자 전용 receipt 디렉터리를 준비한다. 결과에는 테이블별 건수가 있으므로 공개 저장소에 올리지 않는다.
3. 아래 예시의 `<...>`를 실제 확인한 값으로 치환해 기본 dry-run을 실행한다. 비밀번호·키는 인자로 받지 않는다.

```bash
python3 refresh-restore-verification.py \
  --result-file /absolute/private/rehearsal/result.json \
  --result-sha256 <original-result-sha256> \
  --previous-sha256 <current-protected-backup-sha256> \
  --receipt-dir /absolute/private/restore-receipts
```

4. `READY_DRY_RUN` 확인 후 승인된 적용 단계에서만 동일 명령에 `--apply`를 붙인다. 기본 백업/설정 경로는 스크립트에 명시되어 있으며 테스트에서는 임시 경로로 대체한다.
5. `PROMOTED` 결과와 설정 hash를 확인한다. 기존 hash를 읽어둔 다른 호출은 거부된다. 이미 같은 백업이 설정돼 있으면 재검증 후 `ALREADY_CURRENT`로 종료한다.
6. 다음 점검 service가 설정을 다시 읽는다. 정기 복원·실패 알림·결과 보관을 연결하는 작업은 별도 운영 검토 후 수행한다.

## 변경과 실패의 안전성

검증 receipt를 0600 파일로 독점 생성·fsync한 뒤 설정 파일을 같은 디렉터리의 임시 파일로 작성하고 atomic replace한다. 설정 원문이 중간에 달라지면 거부하며, 주석·다른 설정 항목은 보존한다. 이 잠금은 같은 잠금을 사용하는 백업/점검과의 협력적 배제를 제공한다. 관리자가 파일을 수동 수정할 때도 작업을 중지하거나 같은 잠금을 사용해야 한다.

receipt는 결과 hash·백업 hash·세대·검증 시각만 기록하며 테이블별 건수나 원본 데이터는 담지 않는다. **receipt 존재만으로 설정 교체까지 완료됐다고 판단하지 않는다.** 교체 직전 실패하면 receipt만 남을 수 있고, fsync 실패는 반영 여부가 불확실할 수 있다. 고정된 실패 코드가 나오면 현재 설정·receipt·파일 상태를 확인한 뒤 재시도한다. 오래된 hash로의 자동 롤백은 없다.

이 증빙은 소유자 전용 로컬 검증 결과이지 외부 서명/불변 감사 대장이 아니다. 같은 OS 계정이나 root가 침해되면 위조할 수 있다. receipt도 설정과 같은 서버에 있으므로 독립 재해복구 증빙을 대체하지 않는다.

`productionLedgerReplayVerified=false`, `retentionEligible=false`를 명시한다. 구조 복원 또는 가상 파기 성공은 실제 회원 파기 대장 재적용 완료나 백업 삭제 승인이 아니다.

## 테스트

[합성 테스트](scripts/tests/test_restore_verification_refresh.py)는 운영 파일·DB·Docker·R2를 사용하지 않는다.

- 정책: 성공/실패, 필수 증빙 누락, 잘못된 자료형, 오래된 캡처/결과, 미래/역전 시각, 세대 불일치, 중복 JSON/설정 거부.
- Linux 파일시스템: dry-run 무변경, 적용 시 한 설정만 교체, receipt 최소화, 재시도/동시 잠금, 파일 변조, checksum 오류, 기존 보호본 누락, 오래된 후보, 링크/권한, receipt 충돌, atomic replace 실패.
- 로컬 Windows 전체 41개 중 20개 통과, POSIX 전용 21개는 건너뜀. Linux 전체 실행은 [CI workflow](../.github/workflows/operations-script-tests.yml)에서 확인한다. 테스트 fixture만 사용하며 운영 인증 정보는 주입하지 않는다.

남은 작업: Linux CI 결과 확인, 설치 경로·자동 격리 복원 주기·리소스 제한·실패 알림·비공개 결과 보관 기간 검토, 운영 설치 승인 및 새 실제 복원 결과로 dry-run/적용 검증. 회원 자동 파기는 계속 비활성이다.
