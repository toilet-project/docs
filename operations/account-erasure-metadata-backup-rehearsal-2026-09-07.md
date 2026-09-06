# 메타데이터 백업 1건 생성·격리 복원 검증

2026-09-07 KST. 사용자 승인 범위: 별도 임시 도구 전송, 새 암호화 백업 1건 생성, 격리 MySQL 복원 및 가상 검증. **운영 DDL·정기 백업 교체·기존 백업 삭제·자동 파기 활성화는 하지 않았다.**

## 결과

| 항목 | 결과 |
| --- | --- |
| 새 백업 | `toilet-db-20260906-153502.sql.gz.enc` (파일명은 UTC) |
| 생성 시각 | 2026-09-07 00:35:02~00:35:09 KST |
| 암호화 덤프 크기 | 17,093,168 bytes (약 17.1 MB) |
| 생성 파일 | 암호화 덤프·`.sha256`·`.metadata.json` 3개 |
| metadata 대조 | 파일명·크기·hash·캡처 시각·사전에 읽은 DB UUID 및 후보 복원 세대 일치 |
| 격리 복원/검증 | 00:35:22~00:36:16 KST, 약 54초 |
| MySQL | 운영 컨테이너와 같은 로컬 이미지, 8.0.46 |
| 복원 구조 | 16개 테이블, 화장실 53,583건 |
| 외래키 검사 | 13개 관계, 참조 불일치 0 |
| V11 DDL | 격리 DB에만 적용 성공 |
| 가상 파기 | 가상 회원 2건, 실제 공유 Java 계약 사용 |
| 실패/반복 검증 | 식별 충돌 시 원자적 중단, 미지 FK 시 롤백, 반복 적용의 추가 변경 없음 |
| 원본 보존 | 복원 원본 컬럼 전체의 PK 정렬 hash 일치, 가상 fixture 제거 |
| 런타임 검증문 | 75개 assertion 통과 (독립 테스트 75건이라는 뜻이 아님) |
| 기존 보존 | 기존 백업 디렉터리 파일·설치된 백업 스크립트 hash 변경 없음 |
| 원본 신규 백업 보존 | 복원 전후 덤프와 metadata hash 변경 없음 |
| 임시 자원 정리 | 임시 컨테이너·익명 볼륨·내부 전용 네트워크 제거, 임시 도구/로그 약 166.3 MB 제거 |

신규 백업 3개 파일은 미니 PC의 기존 비공개 백업 경로 `/home/luha/backups/geupddong/mysql/`에 남겨 두었다. 임시 로그·도구는 복구 대상으로 보관하지 않았으며 필요한 비식별 검증 결과를 이 문서에 기록했다. 원문 덤프·회원 행·키·세부 회원별 집계는 공개 저장소로 가져오지 않았다.

## 검증 방식과 코드 보완

- 별도 임시 폴더의 새 `mysql-backup.sh`만 1회 실행했다. 운영 설치 파일·timer는 교체하지 않았다.
- DB 비밀번호를 `docker exec` 명령 인자 값에 넣지 않고 `MYSQL_PWD` 환경변수 전달로 변경했다. 환경변수가 비밀 저장소나 고권한 사용자로부터의 완전한 은닉 수단이라는 뜻은 아니다.
- 복원 도구는 metadata가 있거나 필수 모드이면 파일 내용을 검증한다. 기대 DB UUID·복원 세대는 metadata에서 그대로 복사하지 않고 캡처 이전에 정한 값으로 대조했다.
- 백업은 consistent snapshot mysqldump → gzip → 기존 키로 암호화했다. 캡처 시작 시각은 mysqldump 실행 전 보수적인 경계이지 정확한 DB snapshot 시각으로 주장하지 않는다.
- 복호화 평문은 파이프로만 격리 MySQL에 전달했다. 호스트의 평문 덤프 파일은 생성하지 않았다.
- 임시 MySQL은 포트 외부 공개 없이 internal 네트워크, 메모리 1 GB/CPU 1개 제한, 이벤트 스케줄러/binlog/local infile 비활성 상태로 실행했다.
- 원본 데이터 보존 검사는 운영 DB를 테스트 변경한 것이 아니라 **복원한 복사본**의 V11/가상 파기 전후 비교다.

관련 코드: [백업](scripts/mysql-backup.sh), [격리 복원](scripts/verify-live-backup-isolated.py), [가상 파기](scripts/LiveBackupV11Replay.java), [metadata 보호 테스트](scripts/tests/test_live_backup_guards.py).

## 검사 근거

- Python 보호 검사 3건 통과. metadata 정상·파일명/hash/크기/UUID/세대/버전/시각 오류·독립 기준 누락·metadata 누락을 subtest로 검사했다.
- Java `BackupCaptureMetadataTest` 5건, `BackupCaptureScriptTest` 2건 통과, 건너뜀/실패/오류 0.
- Bash 문법 검사·Git 공백 검사 통과.
- 서버 도구 전송 archive SHA-256 일치 확인 후 실행했다. 최초 전송은 추가 명시 승인 요구로 중단됐고, 사용자 승인 후 동일 대상에 전송했다. 거부를 우회하지 않았다.

비식별 무결성 참고값:

```text
encryptedBackupSha256=9cd86baacca79e8299e29bd10b9ffb6a0a12d8840bd1a83a056f48d523bbdcc9
metadataSha256=138338a562aed9c8d841bea84d1262a5d5c7fec966f6305d7a1c9f7fdc654d4f
privateResultSha256=b92463f3f0b31d7ac57dd774f8426b9332d01d76ecff8af8b122429cc62f3f52
```

hash는 기록의 비교 기준이며 신뢰된 외부 서명이나 불변 저장소를 대신하지 않는다.

## 아직 완료하지 않은 범위

1. **복원 세대는 검증용 후보**다. 새 metadata에 남아 있으나 운영 초기 기준으로 확정하거나 비공개 체크포인트에 등록하지 않았다. 기존 백업에 소급 적용하지 않는다.
2. 실제 R2 대장이 비어 있어 운영 대장을 재생한 시험은 아니다. 결과의 `productionLedgerReplayVerified=false`, `retentionEligible=false`를 유지한다.
3. 이번 복원은 기존 백업 암호화 키를 사용했다. 사용자가 별도로 보관한 R2 키링 사본의 실제 복구 가능성 시험을 대신하지 않는다.
4. 정기 metadata 백업·독립 점검/알림은 미설치다. 현재 기존 정기 백업은 기존 방식으로 계속 동작한다.
5. 기존 metadata 없는 백업 처리, 최장 보관 기간·전체 사본/Redis/binlog 범위·초기 기준 확립은 남아 있다. 새 백업이 생겼다는 이유로 기존 파일을 삭제하지 않았다.
6. 다음 단계는 독립 초기 기준 검토와 정기 백업 전환안 승인이다. 운영 V11·API/배치/웹 배포와 자동 파기는 별도 승인 범위다.
