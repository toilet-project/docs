# 행정구역 정규화 운영 반영안

> 공개 요약본입니다. 작성 당시의 수치·검증 단계를 보존합니다. 최신 배포 및 남은 검증은 [관리자 검토 배포 보고서](region-admin-review-release-2026-09-05.md)를 참고하세요. 전체 JSON·시설별 검토 원문·운영 접속정보는 공개하지 않습니다.

2026-09-05 · 사용자 검토 후 승인된 실행 절차. 실제 수행 결과는 [운영 반영 보고서](region-production-result-2026-09-05.md)를 참고한다.

## DDL과 범위

현재 53,582건 중 좌표 있는 52,294건의 결과를 재사용한다. 공개 지역 조회 후보는 VERIFIED 51,985건, 나머지 309건은 검토 상태로 저장한다. 좌표 없는 1,288건은 최초 replay 대상에서 제외한다.

| 순서 | migration | 변경 | 원본 보존 |
|---|---|---|---|
| 1 | [V8](../database/ddl/v1.8-toilet-region.sql) | toilet_region + current_toilet_region + 지역 인덱스 | toilet 주소·좌표 수정 없음 |
| 2 | [V9](../database/ddl/v1.9-coordinate-address-fields.sql) | 제보/좌표 이력의 지번 컬럼, applied_road_address NULL 허용 | 이전 주소 재분류 없음 |
| 3 | [V10](../database/ddl/v1.10-region-assessment-history.sql) | 판정 이력·중복 방지·검토 인덱스 | 원천 데이터 수정 없음 |

toilet-api의 동일한 migration 파일이 실행 기준이다. Flyway 적용 시 DDL을 별도 수동 실행하여 이중 적용하지 않는다. 기존 V0~V7 체크섬·미적용 번호를 확인하고 API migration과 batch 배포 순서를 맞춘다. DDL은 이전 격리 MySQL 검증 내용과 동일하다.

## 승인 후 순서

1. API·batch·docs feature diff 검토. batch main push는 사용자 승인 후 수행하며 워커는 OFF 유지.
2. toilet, toilet_report, coordinate_revision, flyway_schema_history 및 이미 있는 파생/이력을 백업. 성공 로그·크기·체크섬·격리 복구 확인.
3. 분석 파일·검토 목록을 영속 경로에 보존. SHA256·jar 해시·알고리즘·검토 날짜를 기록. 비밀키/암호는 기존 보안 환경에서 주입.
4. V8~V10 적용 후 테이블·view·인덱스·기존 API 확인.
5. RegionReplayCli 기본 dry-run 전수 실행. 변경·신규·TTL 만료를 확인하고 필요 항목만 재검증하여 새 파일·해시 검토.
6. REGION_MAX_ITEMS=100, --apply로 100건 적용. 원본·파생·이력·view 확인. API 호출은 0회.
7. 동일 파일 재실행 시 이미 적용된 행 skip 확인 후 분할 전체 적용. 실행별 JSON 보존. 실패 시 같은 파일로 재개.
8. 후보/적용/충돌/검토 상태 합계와 원본 주소·좌표 보존 검증.
9. 일일 예산·영속 journal 경로 확정 후 워커 활성화. 신규/좌표 변경 감지와 실패 로그 확인 후 WBS 완료 판단.

## 반영 전용 CLI

Spring 애플리케이션·스케줄러·Flyway를 기동하지 않는 standalone main이며 HTTP provider를 만들지 않는다. --fill-missing 등 미지원 인자를 거부한다.

| 환경변수 | 용도 |
|---|---|
| SPRING_DB_URL / USERNAME / PASSWORD | 기존 보안 환경에서 주입. dry-run은 읽기 전용 DB 세션 |
| REGION_REPLAY_PATH | 검토된 JSONL 절대 경로 |
| REGION_REPLAY_SHA256 | 검토 시 고정한 SHA256. 실행 직전 파일에서 다시 계산해 대체하지 않음 |
| REGION_MAX_ITEMS | 이번 적용 후보 상한, 기본 100 |

```text
java -Xmx256m -XX:ActiveProcessorCount=1 \
  -Dloader.main=com.example.toiletbatch.region.RegionReplayCli \
  -cp <검증된-배치.jar> org.springframework.boot.loader.launch.PropertiesLauncher

# 기본은 dry-run. 사용자 승인 후 실제 적용할 때만 마지막에 --apply 추가.
```

검토 파일 reviewed-replay.region.jsonl의 SHA256:
`f89dce50c6b32450149908c055541b97e7e0a42931dddca4b4a202d7291d13eb`

최종 전수 모의 실행 9/5 11:54:37 KST, jar SHA256:
`6935410f275fdd02b4f75f15e7c61462df530bb437e64227ad477b3d2241b615`

누락 좌표 검색 방지까지 포함한 최종 jar로 재확인했다. 이후 코드를 변경해 다시 빌드하면 새 jar 해시와 검증 결과를 기록한다. 상세 원본 자료(비공개 운영 보관)을 함께 확인한다.

## 동시 수정·재개

파일 버전·TTL·원본 지문을 현재 DB와 비교하고, 적용 직전 toilet 행 잠금 안에서 재확인한다. 소스 불일치면 파생/이력을 쓰지 않고 concurrentChange ID로 보고한다. 이력과 현재 결과는 같은 트랜잭션이다. 같거나 최신인 저장 판정은 건너뛴다.

eligible는 실제 적용 수가 아니다. applied, alreadyStored, staleOrChanged, missingCoordinates, noResult, invalidResult, concurrentChange를 함께 확인한다. scanComplete=false이면 전체 완료가 아니며 다음 실행에서 저장된 행을 skip하여 재개한다.

## 롤백

워커와 추가 apply 중지 후 API/배치를 이전 안정 버전으로 복귀한다. 신규 파생/이력을 보존하며 기존 서비스가 이를 소비하지 않도록 한다. 행별 트랜잭션이므로 부분 적용 상태를 구분할 수 있다.

파생 결과 철회가 필요하면 먼저 파생/이력을 별도 백업하고 이번 적용 행을 확인한다. 원본 toilet 주소·좌표를 일괄 UPDATE/DELETE하지 않는다. V9 이후 지번만 있는 이력이 생길 수 있어 applied_road_address를 무조건 NOT NULL로 되돌리지 않는다. 테이블 제거·Flyway 이력 삭제는 자동 롤백 수단으로 쓰지 않는다.

이 문서는 실행 전 수립한 절차다. 2026-09-05 사용자 승인 후 실행 상태와 결과는 [운영 반영 보고서](region-production-result-2026-09-05.md)에 별도로 기록한다.
