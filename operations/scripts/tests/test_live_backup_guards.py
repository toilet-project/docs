import importlib.util
from pathlib import Path
import tempfile
import json
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "verify-live-backup-isolated.py"
spec = importlib.util.spec_from_file_location("isolated_backup", SOURCE)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupHelpersTest(unittest.TestCase):
    def test_metadata_requires_matching_independent_identity_and_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toilet-db-20260907-000000.sql.gz.enc"
            path.write_bytes(b"synthetic ciphertext")
            epoch = "a1111111-1111-1111-1111-111111111111"
            server = "b2222222-2222-2222-2222-222222222222"
            meta = dict(version=1, filename=path.name, sha256=backup.digest(path), bytes=path.stat().st_size,
                        captureStartedAt="2000-01-01T00:00:00Z", captureCompletedAt="2000-01-01T00:00:01Z",
                        database="toilet_db", serverUuid=server, databaseEpoch=epoch)
            target = Path(str(path) + ".metadata.json")
            target.write_text(json.dumps(meta))
            self.assertTrue(backup.verify_metadata(path, epoch, server)["captureMetadataVerified"])
            for field, wrong in [("filename", "other"), ("sha256", "0" * 64), ("bytes", 0),
                                 ("serverUuid", epoch), ("databaseEpoch", server), ("version", True),
                                 ("captureStartedAt", "2001-01-01T00:00:00Z"),
                                 ("captureCompletedAt", "2999-01-01T00:00:00Z")]:
                with self.subTest(field=field):
                    target.write_text(json.dumps({**meta, field: wrong}))
                    with self.assertRaises(ValueError):
                        backup.verify_metadata(path, epoch, server)
            target.write_text(json.dumps(meta))
            with self.assertRaises(ValueError):
                backup.verify_metadata(path, None, server)
            target.unlink()
            with self.assertRaises(ValueError):
                backup.verify_metadata(path, epoch, server)

    def test_identifier_only_allows_schema_identifiers(self):
        self.assertEqual("`app_user`", backup.identifier("app_user"))
        for name in ["a;DROP TABLE x", "a`", "a.b", "a b", "", "a\n"]:
            with self.assertRaises(ValueError):
                backup.identifier(name)

    def test_hash_reads_source_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic"
            path.write_bytes(b"abc")
            before = path.stat().st_mtime_ns
            self.assertEqual("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", backup.digest(path))
            self.assertEqual(before, path.stat().st_mtime_ns)
            self.assertEqual(b"abc", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
