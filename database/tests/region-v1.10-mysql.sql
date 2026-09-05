DELIMITER //
CREATE PROCEDURE assert_ok(IN passed BOOLEAN, IN label VARCHAR(100))
BEGIN
 IF passed IS NULL OR NOT passed THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT=label; END IF;
END//
DELIMITER ;
CALL assert_ok((SELECT proposed_road_address='기존 제보 도로명' AND proposed_jibun_address IS NULL FROM toilet_report WHERE report_id=1),'V9 original report preserved');
CALL assert_ok((SELECT applied_road_address='기존 확정 도로명' AND applied_jibun_address IS NULL FROM coordinate_revision WHERE coordinate_revision_id=1),'V9 original revision preserved');
INSERT INTO coordinate_revision(coordinate_revision_id,toilet_id,applied_latitude,applied_longitude,applied_road_address,applied_jibun_address,applied_by_user_id)
VALUES(2,1,36.3,127.3,NULL,'지번만 있는 확정',1);
CALL assert_ok((SELECT applied_road_address IS NULL AND applied_jibun_address='지번만 있는 확정' FROM coordinate_revision WHERE coordinate_revision_id=2),'V9 nullable road supported');

INSERT INTO toilet_region(toilet_id,sido_name,sido_code,sigungu_name,sigungu_code,city_name,district_name,legal_dong_code,region_source,status,reason,source_hash,source_latitude,source_longitude,source_road_address,source_jibun_address,evaluated_latitude,evaluated_longitude,result_json,checked_at)
SELECT toilet_id,
 CASE toilet_id WHEN 1 THEN '대전광역시' WHEN 2 THEN '경기도' ELSE '세종특별자치시' END,
 CASE toilet_id WHEN 1 THEN '30' WHEN 2 THEN '41' ELSE '36' END,
 CASE toilet_id WHEN 1 THEN '유성구' WHEN 2 THEN '수원시 영통구' ELSE NULL END,
 CASE toilet_id WHEN 1 THEN '30200' WHEN 2 THEN '41117' ELSE '36110' END,
 CASE toilet_id WHEN 2 THEN '수원시' ELSE NULL END,CASE toilet_id WHEN 2 THEN '영통구' ELSE NULL END,
 CASE toilet_id WHEN 1 THEN '3020012200' WHEN 2 THEN '4111710100' ELSE '3611010100' END,
 'KAKAO_COORD2REGIONCODE_B','VERIFIED','TEST',REPEAT('a',64),latitude,longitude,road_address,jibun_address,latitude,longitude,JSON_OBJECT('test',TRUE),NOW()
FROM toilet WHERE toilet_id<=3;
CALL assert_ok((SELECT COUNT(*)=3 FROM current_toilet_region),'V8 visible verified coordinates');
START TRANSACTION;
UPDATE toilet SET latitude=36.4 WHERE toilet_id=1;
CALL assert_ok((SELECT COUNT(*)=2 FROM current_toilet_region),'V8 coordinate invalidation');
UPDATE toilet SET road_address='주소 오타 수정' WHERE toilet_id=2;
CALL assert_ok((SELECT COUNT(*)=1 FROM current_toilet_region),'V8 address evidence invalidation');
UPDATE toilet_region SET status='ADDRESS_UNVERIFIED' WHERE toilet_id=3;
CALL assert_ok((SELECT COUNT(*)=0 FROM current_toilet_region),'V8 unresolved excluded');
ROLLBACK;

INSERT INTO toilet_region_assessment_history(toilet_id,source_hash,algorithm_version,status,reason,result_json,checked_epoch_millis,checked_at)
VALUES(1,REPEAT('a',64),'kakao-b-v2','ADDRESS_UNVERIFIED','RECHECK_MANUAL_REVIEW',JSON_OBJECT('evidence',JSON_OBJECT('distanceMeters',83.1,'reason','ADDRESS_DISTANCE_EXCEEDED')),1000,'2026-09-04 15:00:00.123')
ON DUPLICATE KEY UPDATE assessment_id=assessment_id;
INSERT INTO toilet_region_assessment_history(toilet_id,source_hash,algorithm_version,status,reason,result_json,checked_epoch_millis,checked_at)
VALUES(1,REPEAT('a',64),'kakao-b-v2','ADDRESS_UNVERIFIED','RECHECK_MANUAL_REVIEW',JSON_OBJECT(),1000,'2026-09-04 15:00:00.123')
ON DUPLICATE KEY UPDATE assessment_id=assessment_id;
CALL assert_ok((SELECT COUNT(*)=1 FROM toilet_region_assessment_history),'V10 replay idempotent');
CALL assert_ok((SELECT JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.evidence.reason'))='ADDRESS_DISTANCE_EXCEEDED' AND MICROSECOND(checked_at)=123000 FROM toilet_region_assessment_history),'V10 JSON original evidence and milliseconds preserved');
START TRANSACTION;
INSERT INTO toilet_region_assessment_history(toilet_id,source_hash,algorithm_version,status,reason,result_json,checked_epoch_millis,checked_at)
VALUES(1,REPEAT('a',64),'kakao-b-v2','VERIFIED','TEST',JSON_OBJECT(),2000,NOW());
UPDATE toilet_region SET reason='UNCOMMITTED' WHERE toilet_id=1;
ROLLBACK;
CALL assert_ok((SELECT COUNT(*)=1 FROM toilet_region_assessment_history),'V10 history transaction rollback');
CALL assert_ok((SELECT reason='TEST' FROM toilet_region WHERE toilet_id=1),'V10 projection transaction rollback');
CALL assert_ok((SELECT COUNT(DISTINCT INDEX_NAME)=3 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='toilet_region_assessment_history'),'V10 indexes present');
CALL assert_ok((SELECT COUNT(*)=3 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='toilet_region' AND index_name='idx_toilet_region_review'),'V10 admin queue index');
EXPLAIN SELECT toilet_id FROM toilet_region WHERE status='ADDRESS_UNVERIFIED' ORDER BY checked_at,toilet_id LIMIT 5;
EXPLAIN SELECT assessment_id FROM toilet_region_assessment_history WHERE toilet_id=1 ORDER BY checked_at,assessment_id LIMIT 5;

-- Export evidence before destructive schema rollback, only in this isolated synthetic database.
CREATE TABLE history_backup AS SELECT * FROM toilet_region_assessment_history;
CREATE TABLE revision_backup AS SELECT * FROM coordinate_revision;
DROP INDEX idx_toilet_region_review ON toilet_region;
DROP TABLE toilet_region_assessment_history;
DROP VIEW current_toilet_region;
DROP TABLE toilet_region;
-- V9 NOT NULL rollback is unsafe with real new jibun-only data: preserve it in backup first.
DELETE FROM coordinate_revision WHERE coordinate_revision_id=2;
ALTER TABLE toilet_report DROP COLUMN proposed_jibun_address;
ALTER TABLE coordinate_revision DROP COLUMN previous_jibun_address,DROP COLUMN applied_jibun_address,MODIFY COLUMN applied_road_address VARCHAR(255) NOT NULL;
CALL assert_ok((SELECT COUNT(*)=1 FROM history_backup),'history backup survives rollback');
CALL assert_ok((SELECT COUNT(*)=1 FROM revision_backup WHERE applied_road_address IS NULL AND applied_jibun_address='지번만 있는 확정'),'jibun-only evidence survives rollback');
CALL assert_ok((SELECT COUNT(*)=4 FROM toilet),'original toilets preserved');
CALL assert_ok((SELECT COUNT(*)=0 FROM toilet t JOIN baseline_original b ON b.toilet_id=t.toilet_id WHERE NOT(t.road_address<=>b.road_address) OR NOT(t.jibun_address<=>b.jibun_address) OR NOT(t.latitude<=>b.latitude) OR NOT(t.longitude<=>b.longitude) OR t.coordinate_source<>b.coordinate_source),'original values preserved');
SELECT 'ALL_ASSERTIONS_PASSED';
DROP PROCEDURE assert_ok;
