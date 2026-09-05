-- Disposable MySQL schema ONLY. Run: mysql region_test < this-file (V8 copied alongside).
CREATE TABLE toilet (
  toilet_id BIGINT PRIMARY KEY, road_address VARCHAR(255), jibun_address VARCHAR(255),
  latitude DECIMAL(10,7), longitude DECIMAL(10,7)
);
SOURCE /tmp/V8__create_toilet_region.sql;
INSERT INTO toilet VALUES (1,'대전광역시 유성구 대학로',NULL,36.3,127.3),
 (2,'경기도 수원시 영통구 광교로',NULL,37.3,127.1),(3,'세종특별자치시 한누리대로',NULL,36.5,127.2);
INSERT INTO toilet_region(toilet_id,sido_name,sido_code,sigungu_name,sigungu_code,city_name,district_name,
 legal_dong_code,region_source,status,reason,source_hash,source_latitude,source_longitude,source_road_address,
 evaluated_latitude,evaluated_longitude,result_json,checked_at)
SELECT toilet_id,
 CASE toilet_id WHEN 1 THEN '대전광역시' WHEN 2 THEN '경기도' ELSE '세종특별자치시' END,
 CASE toilet_id WHEN 1 THEN '30' WHEN 2 THEN '41' ELSE '36' END,
 CASE toilet_id WHEN 1 THEN '유성구' WHEN 2 THEN '수원시 영통구' ELSE NULL END,
 CASE toilet_id WHEN 1 THEN '30200' WHEN 2 THEN '41117' ELSE '36110' END,
 CASE toilet_id WHEN 2 THEN '수원시' ELSE NULL END, CASE toilet_id WHEN 2 THEN '영통구' ELSE NULL END,
 CASE toilet_id WHEN 1 THEN '3020012200' WHEN 2 THEN '4111710100' ELSE '3611010100' END,
 'KAKAO_COORD2REGIONCODE_B','VERIFIED','TEST',REPEAT('a',64),latitude,longitude,road_address,
 latitude,longitude,JSON_OBJECT(),NOW() FROM toilet;
DELIMITER //
CREATE PROCEDURE assert_region_count(IN expected INT)
BEGIN
  IF (SELECT COUNT(*) FROM current_toilet_region) <> expected THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Region view freshness check failed';
  END IF;
END//
DELIMITER ;
CALL assert_region_count(3);
UPDATE toilet SET latitude=36.4 WHERE toilet_id=1;
CALL assert_region_count(2);
UPDATE toilet SET road_address='주소 오타만 수정' WHERE toilet_id=2;
CALL assert_region_count(1);
UPDATE toilet_region SET status='MISMATCH' WHERE toilet_id=3;
CALL assert_region_count(0);
SHOW INDEX FROM toilet_region;
EXPLAIN SELECT toilet_id FROM current_toilet_region WHERE sido_code='30';
EXPLAIN SELECT toilet_id FROM current_toilet_region WHERE sigungu_code='41117';
EXPLAIN SELECT toilet_id FROM current_toilet_region WHERE sido_code='41' AND city_name='수원시';
DROP PROCEDURE assert_region_count;
DROP VIEW current_toilet_region;
DROP TABLE toilet_region;
SELECT COUNT(*) AS original_rows_after_derived_rollback FROM toilet;
