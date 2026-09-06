import com.geupddong.account.AccountErasureRestore;
import com.geupddong.account.ErasureRecord;
import java.nio.ByteBuffer;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.ResultSet;
import java.time.LocalDateTime;
import java.util.*;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

/** Test-only source launcher. No Spring application, scheduling, R2 access or production credentials. */
public class LiveBackupV11Replay {
    static JdbcTemplate jdbc;
    static DriverManagerDataSource ds;
    static String phase = "guard";
    static int checks;
    static final String REALM = "synthetic-v11-replay";
    static final LocalDateTime CREATED = LocalDateTime.of(2000, 1, 1, 0, 0);
    static final LocalDateTime NOW = LocalDateTime.of(2020, 1, 1, 0, 0);
    record Shape(String table, List<String> columns, List<String> keys) { }
    static void require(boolean ok) { if (!ok) throw new IllegalStateException("CHECK_FAILED"); checks++; }
    static String ident(String s) {
        if (!s.matches("[A-Za-z0-9_]+")) throw new IllegalArgumentException();
        return "`" + s + "`";
    }
    static long number(String sql, Object... args) { return jdbc.queryForObject(sql, Long.class, args); }
    static long next(String table, String key) {
        long nextRow = Math.addExact(number("SELECT COALESCE(MAX(" + ident(key) + "),0) FROM " + ident(table)), 1);
        return Math.max(nextRow, number("SELECT COALESCE(auto_increment,0) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?", table));
    }
    static List<Shape> shapes() {
        var tables = jdbc.queryForList("SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_type='BASE TABLE' AND table_name<>'erasure_restore_guard' ORDER BY table_name", String.class);
        return tables.stream().map(t -> {
            var cols = jdbc.queryForList("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? ORDER BY ordinal_position", String.class, t);
            var keys = jdbc.queryForList("SELECT column_name FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name=? AND constraint_name='PRIMARY' ORDER BY ordinal_position", String.class, t);
            require(!keys.isEmpty());
            return new Shape(t, cols, keys);
        }).toList();
    }
    // Stream original fields only; no row values or fingerprints leave process memory.
    // Length prefixes/null tags prevent ambiguous concatenation. Stable PK order supports composite keys.
    static Map<String,String> fingerprint(List<Shape> shapes) throws Exception {
        var result = new TreeMap<String,String>();
        try (Connection c = ds.getConnection()) {
            for (var shape : shapes) {
                var hash = MessageDigest.getInstance("SHA-256");
                String cols = String.join(",", shape.columns().stream().map(LiveBackupV11Replay::ident).toList());
                String keys = String.join(",", shape.keys().stream().map(LiveBackupV11Replay::ident).toList());
                try (var stmt = c.createStatement(ResultSet.TYPE_FORWARD_ONLY, ResultSet.CONCUR_READ_ONLY)) {
                    stmt.setFetchSize(Integer.MIN_VALUE);
                    try (var rows = stmt.executeQuery("SELECT " + cols + " FROM " + ident(shape.table()) + " ORDER BY " + keys)) {
                        while (rows.next()) {
                            hash.update((byte) 2);
                            for (int i = 1; i <= shape.columns().size(); i++) {
                                byte[] bytes = rows.getBytes(i);
                                hash.update((byte) (bytes == null ? 0 : 1));
                                if (bytes != null) {
                                    hash.update(ByteBuffer.allocate(4).putInt(bytes.length).array());
                                    hash.update(bytes);
                                }
                            }
                        }
                    }
                }
                result.put(shape.table(), HexFormat.of().formatHex(hash.digest()));
            }
        }
        return result;
    }
    static ErasureRecord record(long id) { return new ErasureRecord(1, REALM, id, CREATED.toString(), UUID.randomUUID().toString(), CREATED.plusMonths(3).toString()); }
    static void expectIdentityFailure(AccountErasureRestore restore, List<ErasureRecord> records) {
        try { restore.replay(records, REALM, NOW, true); }
        catch (IllegalStateException e) { require("ERASURE_RESTORE_IDENTITY_CONFLICT".equals(e.getMessage())); return; }
        throw new IllegalStateException("IDENTITY_FAILURE_EXPECTED");
    }
    public static void main(String[] args) {
        try {
            String ip = System.getenv("V11_REPLAY_IP"), marker = System.getenv("V11_REPLAY_MARKER");
            require(args.length == 1 && ip != null && ip.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}"));
            int[] octets = Arrays.stream(ip.split("\\.")).mapToInt(Integer::parseInt).toArray();
            require(Arrays.stream(octets).allMatch(n -> n >= 0 && n <= 255));
            require(octets[0] == 10 || octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31 || octets[0] == 192 && octets[1] == 168);
            require(marker != null && marker.matches("[a-f0-9]{32}"));
            var ddl = Path.of(args[0]).toRealPath();
            require(ddl.toString().matches("/tmp/geupddong-live-backup-check\\.[A-Za-z0-9]+/v1\\.11-account-withdrawal-retention\\.sql"));
            ds = new DriverManagerDataSource("jdbc:mysql://" + ip + ":43317/toilet_db?connectionTimeZone=%2B09:00&forceConnectionTimeZoneToSession=true&connectTimeout=5000&socketTimeout=120000&allowPublicKeyRetrieval=true&sslMode=DISABLED", "root", Objects.requireNonNull(System.getenv("MYSQL_PWD")));
            jdbc = new JdbcTemplate(ds);
            require(marker.equals(jdbc.queryForObject("SELECT marker FROM erasure_restore_guard", String.class)));
            require(Objects.requireNonNull(System.getenv("V11_REPLAY_UUID")).equals(jdbc.queryForObject("SELECT @@server_uuid", String.class)));
            require("DISABLED".equals(jdbc.queryForObject("SELECT @@event_scheduler", String.class)));
            require(number("SELECT @@log_bin") == 0 && number("SELECT @@local_infile") == 0 && number("SELECT @@port") == 43317);
            phase = "baseline";
            var originalShapes = shapes();
            require(originalShapes.size() == 16);
            var original = fingerprint(originalShapes);
            require(number("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='account_withdrawal'") == 0);
            require(number("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND ((table_name='app_user' AND column_name='auth_version') OR (table_name='audit_log' AND column_name='actor_erased'))") == 0);
            phase = "exact-v11-ddl";
            try (var conn = ds.getConnection()) { ScriptUtils.executeSqlScript(conn, new FileSystemResource(ddl)); }
            require(original.equals(fingerprint(originalShapes)));
            require(number("SELECT COUNT(*) FROM app_user WHERE auth_version<>0") == 0);
            require(number("SELECT COUNT(*) FROM audit_log WHERE actor_erased<>0") == 0);
            require(number("SELECT COUNT(*) FROM account_withdrawal") == 0);
            require(number("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND ((table_name='toilet_report' AND column_name='reporter_user_id') OR (table_name='coordinate_revision' AND column_name='applied_by_user_id')) AND is_nullable='YES'") == 2);
            require(number("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='account_withdrawal' AND index_name='idx_withdrawal_due'") == 2);
            phase = "synthetic-fixture";
            long u = next("app_user", "user_id"), reviewer = u + 1, keeper = u + 2;
            long toilet = number("SELECT MIN(toilet_id) FROM toilet"), policy = number("SELECT MIN(policy_document_id) FROM policy_document");
            long report = next("toilet_report", "report_id"), report2 = report + 1;
            long audit = next("audit_log", "audit_log_id"), revision = next("coordinate_revision", "coordinate_revision_id");
            String key = marker + marker;
            require(number("SELECT COUNT(*) FROM audit_log WHERE actor_user_id IN (?,?,?) OR (target_type='USER' AND target_id IN (?,?,?)) OR (target_type='TOILET_REPORT' AND target_id IN (?,?))", u, reviewer, keeper, u, reviewer, keeper, report, report2) == 0);
            for (long id : List.of(u, reviewer, keeper)) {
                jdbc.update("INSERT INTO app_user(user_id,status,display_name,email,created_at,updated_at) VALUES(?,'ACTIVE','synthetic','fixture@example.invalid',?,?)", id, CREATED, CREATED);
                jdbc.update("INSERT INTO user_role(user_id,role,granted_by_user_id) VALUES(?,'USER',?)", id, u);
            }
            for (long id : List.of(u, reviewer)) {
                jdbc.update("INSERT INTO user_social_account(user_id,provider,provider_subject_hash,provider_email) VALUES(?,'GOOGLE',?,'fixture@example.invalid')", id, String.format("%064x", id));
                jdbc.update("INSERT INTO user_policy_consent(user_id,policy_document_id,consent_source) VALUES(?,?,'SIGNUP')", id, policy);
                jdbc.update("INSERT INTO user_notification(user_id,notification_type,reference_type,reference_id,title,message) VALUES(?,'REPORT_REVIEWED','TOILET_REPORT',?,'synthetic','synthetic')", id, report);
                jdbc.update("INSERT INTO account_withdrawal(user_id,withdrawal_key,withdrawn_at,purge_after,recovery_allowed,next_attempt_at) VALUES(?,?,?,?,TRUE,?)", id, UUID.randomUUID().toString(), CREATED, CREATED.plusMonths(3), CREATED.plusMonths(3));
            }
            jdbc.update("INSERT INTO toilet_report(report_id,toilet_id,reporter_user_id,report_type,reason,reviewed_by_user_id,review_note,active_request_key,proposed_latitude,proposed_longitude,status) VALUES(?,?,?,'LOCATION','synthetic',?,'synthetic',?,37.5,127.0,'PENDING')", report, toilet, u, reviewer, key);
            jdbc.update("INSERT INTO toilet_report(report_id,toilet_id,reporter_user_id,report_type,reason,reviewed_by_user_id,review_note,status) VALUES(?,?,?,'LOCATION','keeper reason',?,'synthetic','REJECTED')", report2, toilet, keeper, reviewer);
            jdbc.update("INSERT INTO coordinate_revision(coordinate_revision_id,toilet_id,report_id,applied_latitude,applied_longitude,applied_by_user_id) VALUES(?,?,?,37.5,127.0,?)", revision, toilet, report, reviewer);
            jdbc.update("INSERT INTO coordinate_quality_review(group_key,latitude,longitude,reviewed_by_user_id,review_note) VALUES(?,37.5,127.0,?,'synthetic')", key, reviewer);
            jdbc.update("INSERT INTO audit_log(audit_log_id,actor_user_id,action,target_type,target_id,detail_json) VALUES(?,?,'SYNTHETIC','TOILET_REPORT',?,JSON_OBJECT('fixture','synthetic'))", audit, keeper, report);
            jdbc.update("INSERT INTO audit_log(audit_log_id,actor_user_id,action,target_type,target_id,detail_json) VALUES(?,?,'SYNTHETIC','USER',?,JSON_OBJECT('fixture','synthetic'))", audit+1, reviewer, u);
            var allShapes = shapes();
            var fixture = fingerprint(allShapes);
            var restore = new AccountErasureRestore(jdbc, new DataSourceTransactionManager(ds));
            var records = List.of(record(u), record(reviewer));
            phase = "dry-run";
            var dry = restore.replay(records, REALM, NOW, false);
            require(dry.matched() == 2 && dry.erased() == 0 && fixture.equals(fingerprint(allShapes)));
            phase = "identity-conflict-atomicity";
            var bad = new ErasureRecord(1, REALM, reviewer, CREATED.plusSeconds(1).toString(), UUID.randomUUID().toString(), CREATED.plusMonths(3).toString());
            expectIdentityFailure(restore, List.of(records.getFirst(), bad));
            require(fixture.equals(fingerprint(allShapes)));
            phase = "unknown-fk-rollback";
            jdbc.execute("CREATE TABLE synthetic_erasure_blocker(user_id BIGINT PRIMARY KEY, FOREIGN KEY(user_id) REFERENCES app_user(user_id))");
            jdbc.update("INSERT INTO synthetic_erasure_blocker VALUES(?)", reviewer);
            boolean blocked = false;
            try { restore.replay(records, REALM, NOW, true); }
            catch (org.springframework.dao.DataIntegrityViolationException expected) { blocked = true; }
            require(blocked && fixture.equals(fingerprint(allShapes)));
            require(number("SELECT COUNT(*) FROM synthetic_erasure_blocker WHERE user_id=?", reviewer) == 1);
            jdbc.execute("DROP TABLE synthetic_erasure_blocker");
            phase = "committed-erasure";
            var applied = restore.replay(records, REALM, NOW, true);
            require(applied.matched() == 2 && applied.erased() == 2);
            require(number("SELECT COUNT(*) FROM app_user WHERE user_id IN (?,?)", u, reviewer) == 0);
            for (String table : List.of("user_social_account","user_policy_consent","user_notification","user_role","account_withdrawal"))
                require(number("SELECT COUNT(*) FROM " + ident(table) + " WHERE user_id IN (?,?)", u, reviewer) == 0);
            require(number("SELECT COUNT(*) FROM toilet_report WHERE report_id=? AND reporter_user_id IS NULL AND reviewed_by_user_id IS NULL AND review_note IS NULL AND active_request_key IS NULL AND reason='탈퇴한 사용자 — 사유 파기' AND proposed_latitude=37.5 AND proposed_longitude=127.0", report) == 1);
            require(number("SELECT COUNT(*) FROM toilet_report WHERE report_id=? AND reporter_user_id=? AND reason='keeper reason' AND reviewed_by_user_id IS NULL AND review_note IS NULL", report2, keeper) == 1);
            require(number("SELECT COUNT(*) FROM audit_log WHERE audit_log_id=? AND actor_user_id=? AND actor_erased=FALSE AND target_id=? AND detail_json IS NULL", audit, keeper, report) == 1);
            require(number("SELECT COUNT(*) FROM audit_log WHERE audit_log_id=? AND actor_user_id IS NULL AND actor_erased=TRUE AND target_id IS NULL AND detail_json IS NULL", audit+1) == 1);
            require(number("SELECT COUNT(*) FROM coordinate_revision WHERE coordinate_revision_id=? AND applied_by_user_id IS NULL AND applied_latitude=37.5 AND applied_longitude=127.0", revision) == 1);
            require(number("SELECT COUNT(*) FROM coordinate_quality_review WHERE group_key=? AND reviewed_by_user_id IS NULL AND review_note IS NULL", key) == 1);
            require(number("SELECT COUNT(*) FROM user_role WHERE user_id=? AND granted_by_user_id IS NULL", keeper) == 1);
            require(number("SELECT COUNT(*) FROM app_user WHERE user_id=? AND status='ACTIVE'", keeper) == 1);
            phase = "idempotence";
            var erasedState = fingerprint(allShapes);
            var repeated = restore.replay(records, REALM, NOW, true);
            require(repeated.matched() == 0 && repeated.absent() == 2 && repeated.erased() == 0 && erasedState.equals(fingerprint(allShapes)));
            phase = "fixture-cleanup-and-preservation";
            jdbc.update("DELETE FROM audit_log WHERE audit_log_id IN (?,?)", audit, audit+1);
            jdbc.update("DELETE FROM coordinate_revision WHERE coordinate_revision_id=?", revision);
            jdbc.update("DELETE FROM coordinate_quality_review WHERE group_key=?", key);
            jdbc.update("DELETE FROM toilet_report WHERE report_id IN (?,?)", report, report2);
            jdbc.update("DELETE FROM user_role WHERE user_id=?", keeper);
            jdbc.update("DELETE FROM app_user WHERE user_id=?", keeper);
            require(original.equals(fingerprint(originalShapes)));
            require(number("SELECT COUNT(*) FROM account_withdrawal") == 0);
            System.out.println("{\"outcome\":\"V11_SYNTHETIC_REPLAY_VERIFIED\",\"originalTables\":16,\"ddlApplied\":true,\"originalDataUnchanged\":true,\"dryRunVerified\":true,\"identityConflictAtomic\":true,\"unknownForeignKeyRollback\":true,\"syntheticAccountsErased\":2,\"idempotenceVerified\":true,\"syntheticFixturesRemoved\":true,\"productionLedgerReplayVerified\":false,\"retentionEligible\":false,\"assertions\":" + checks + "}");
        } catch (Exception e) {
            // Do not expose SQL, row values, addresses, user IDs or JDBC exceptions.
            System.err.println("V11_REHEARSAL_FAILED phase=" + phase);
            System.exit(1);
        }
    }
}
