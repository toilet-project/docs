import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "verify-live-backup-isolated.py"
spec = importlib.util.spec_from_file_location("isolated_backup", SOURCE)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupHelpersTest(unittest.TestCase):
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
