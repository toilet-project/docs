INSERT INTO toilet(toilet_id,name,road_address,jibun_address,latitude,longitude,coordinate_source) VALUES
(1,'검증 대전','대전광역시 유성구 대학로','대전 유성구 궁동',36.3,127.3,'ADMIN_CONFIRMED'),
(2,'검증 수원','경기도 수원시 영통구 광교로',NULL,37.3,127.1,'GEOCODED_LEGACY'),
(3,'검증 세종','세종특별자치시 한누리대로',NULL,36.5,127.2,'GEOCODED_LEGACY'),
(4,'검증 좌표 없음',NULL,NULL,NULL,NULL,'LEGACY');
INSERT INTO app_user(user_id) VALUES(1);
INSERT INTO toilet_report(report_id,toilet_id,reporter_user_id,report_type,reason,proposed_road_address)
VALUES(1,1,1,'LOCATION','합성 테스트','기존 제보 도로명');
INSERT INTO coordinate_revision(coordinate_revision_id,toilet_id,report_id,applied_latitude,applied_longitude,previous_road_address,applied_road_address,applied_by_user_id)
VALUES(1,1,1,36.3,127.3,'기존 이전 도로명','기존 확정 도로명',1);
CREATE TABLE baseline_original AS SELECT toilet_id,road_address,jibun_address,latitude,longitude,coordinate_source FROM toilet;
