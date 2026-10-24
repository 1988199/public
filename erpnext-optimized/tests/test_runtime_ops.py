"""Linux离线回归；只操作TemporaryDirectory中的合成备份。"""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time
import types
from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('backup_service', Path(__file__).resolve().parents[1] / 'docker/backup_service.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        b.STOP = False
        b.CHILD = None

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, name='backup-20200101T000000000000Z'):
        folder = self.root / name
        folder.mkdir()
        (folder / 'dummy').write_text('synthetic')
        b.manifest(folder)
        return folder

    def test_complete_manifest(self):
        self.assertTrue(b.verify_manifest(self.bundle())['complete'])

    def test_database_dump_must_have_completion_marker(self):
        path = self.root / 'test.sql.gz'
        with gzip.open(path, 'wb') as handle:
            handle.write(b'CREATE TABLE synthetic;\n')
        with self.assertRaises(ValueError):
            b.verify_database(path)
        with gzip.open(path, 'wb') as handle:
            handle.write(b'CREATE TABLE synthetic;\n-- Dump completed on test\n')
        b.verify_database(path)

    def test_corrupt_copy_rejected(self):
        folder = self.bundle()
        (folder / 'dummy').write_text('changed')
        with self.assertRaises(ValueError):
            b.verify_manifest(folder)

    def test_path_traversal_rejected(self):
        folder = self.bundle()
        data = json.loads((folder / 'manifest.json').read_text())
        data['files'][0]['name'] = '../elsewhere'
        b.atomic_json(folder / 'manifest.json', data)
        with self.assertRaises(ValueError):
            b.verify_manifest(folder)

    def test_retention_only_owned_valid_bundles(self):
        for index in range(4):
            folder = self.bundle('backup-20200101T00000000000' + str(index) + 'Z')
            data = json.loads((folder / 'manifest.json').read_text())
            data['created'] = time.time() - (index + 2) * 86400
            b.atomic_json(folder / 'manifest.json', data)
        unknown = self.root / 'user-old-backups'
        unknown.mkdir()
        (unknown / 'keep').write_text('do not remove')
        broken = self.root / 'backup-20200101T000000000009Z'
        broken.mkdir()
        b.prune(self.root, 1)
        self.assertEqual(len([x for x in self.root.iterdir() if (x / 'manifest.json').exists()]), 2)
        self.assertTrue((unknown / 'keep').exists())
        self.assertTrue(broken.exists())

    def test_mutual_exclusion(self):
        with b.backup_lock(self.root):
            with self.assertRaises(RuntimeError):
                with b.backup_lock(self.root):
                    self.fail('second backup entered')

    def test_retention_preserves_unrecognized_user_content(self):
        folder = self.bundle()
        data = json.loads((folder / 'manifest.json').read_text())
        data['created'] = time.time() - 259200
        b.atomic_json(folder / 'manifest.json', data)
        (folder / 'user-added-file').write_text('preserve')
        b.prune(self.root, 1, keep=0)
        self.assertTrue((folder / 'user-added-file').exists())

    def test_lock_rejects_symlink_root(self):
        linked = self.root / 'link'
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            with b.backup_lock(linked):
                self.fail('symlink root accepted')

    def test_interrupted_retention_requires_owned_marker(self):
        owned = self.root / 'backup-20200101T000000000000Z.partial-abcdefgh'
        unknown = self.root / 'backup-20200101T000000000000Z.partial-ijklmnop'
        owned.mkdir()
        unknown.mkdir()
        b.atomic_json(owned / '.stage.json', {'format': 'runtime-backup-stage-v1', 'created': time.time() - 259200})
        b.prune_interrupted(self.root)
        self.assertFalse(owned.exists())
        self.assertTrue(unknown.exists())

    def test_authenticated_encryption(self):
        src, enc, out = [self.root / x for x in ('input', 'encrypted', 'output')]
        src.write_bytes(os.urandom(2 * 1024 * 1024 + 7))
        key = os.urandom(32)
        b.encrypt(src, enc, key)
        b.decrypt(enc, out, key)
        self.assertEqual(src.read_bytes(), out.read_bytes())
        self.assertNotEqual(enc.read_bytes()[:16], src.read_bytes()[:16])

    def test_tampered_ciphertext_leaves_no_output(self):
        src, enc, out = [self.root / x for x in ('input', 'encrypted', 'output')]
        src.write_bytes(b'synthetic-only')
        key = os.urandom(32)
        b.encrypt(src, enc, key)
        data = bytearray(enc.read_bytes())
        data[-17] ^= 1
        enc.write_bytes(data)
        with self.assertRaises(Exception):
            b.decrypt(enc, out, key)
        self.assertFalse(out.exists())
        self.assertFalse(out.with_suffix('.partial').exists())

    def test_wrong_key_rejected(self):
        src, enc, out = [self.root / x for x in ('input', 'encrypted', 'output')]
        src.write_bytes(b'synthetic-only')
        b.encrypt(src, enc, os.urandom(32))
        with self.assertRaises(Exception):
            b.decrypt(enc, out, os.urandom(32))

    def test_existing_restore_not_overwritten(self):
        out = self.root / 'output'
        out.write_text('preserve')
        with self.assertRaises(FileExistsError):
            b.decrypt(self.root / 'absent', out, os.urandom(32))
        self.assertEqual(out.read_text(), 'preserve')

    def test_invalid_encryption_key(self):
        key = self.root / 'key'
        key.write_bytes(b'short')
        with patch.dict(os.environ, {'BACKUP_ENCRYPTION_KEY_FILE': str(key)}):
            with self.assertRaises(ValueError):
                b.key_bytes()

    def test_numeric_limits(self):
        with patch.dict(os.environ, {'BACKUP_RETRIES': '1000'}):
            with self.assertRaises(ValueError):
                b.number('BACKUP_RETRIES', 3, high=5)

    def test_failed_job_counts_do_not_cleanup_registry(self):
        spec = importlib.util.spec_from_file_location('runtime_readiness', Path(__file__).resolve().parents[1] / 'docker/readiness.py')
        ready = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ready)
        frappe = types.ModuleType('frappe')
        for name in ('init', 'connect', 'destroy'):
            setattr(frappe, name, Mock())
        frappe.db = Mock()
        frappe.get_installed_apps = lambda: []
        jobs = types.ModuleType('frappe.utils.background_jobs')
        connection = Mock()
        connection.llen.return_value = 3
        connection.zcard.return_value = 42
        queue = types.SimpleNamespace(connection=connection, key='synthetic-queue')
        jobs.get_queue = lambda _: queue
        jobs.get_workers = lambda _: [types.SimpleNamespace(last_heartbeat=datetime.now(timezone.utc))]
        registry = types.ModuleType('rq.registry')
        class ReadOnlyRegistry:
            def __init__(self, queue):
                self.key = 'synthetic-failed-key'
            @property
            def count(self):
                raise AssertionError('count may clean expired jobs')
        registry.FailedJobRegistry = ReadOnlyRegistry
        env = {'BACKUP_ENABLED': '0', 'VERIFY_QUEUE_HEARTBEAT': '1', 'REQUIRED_APPS': '',
               'REQUIRED_ASSET_PATHS': '', 'DEPLOYMENT_READY_FILE': ''}
        with patch.dict(sys.modules, {'frappe': frappe, 'frappe.utils.background_jobs': jobs, 'rq.registry': registry}), \
             patch.dict(os.environ, env), patch.object(ready.os, 'chdir'):
            self.assertEqual(ready.check(True)['queues']['long']['historical_failed'], 42)

    def test_finite_retries_and_failure_status(self):
        states = []
        def record(**value):
            states.append(value)
            if value.get('state') == 'failed':
                b.STOP = True
        child = Mock()
        child.wait.return_value = 1
        env = {'BACKUP_ENABLED': '1', 'BACKUP_RETRIES': '2', 'BACKUP_START_DELAY_SECONDS': '0'}
        with patch.dict(os.environ, env), patch.object(b, 'read_status', return_value={}), \
             patch.object(b, 'status', side_effect=record), patch.object(b.time, 'sleep'), \
             patch.object(b.subprocess, 'Popen', return_value=child) as popen:
            b.daemon()
        self.assertEqual(popen.call_count, 2)
        self.assertEqual(states[-1]['state'], 'failed')
        self.assertEqual(states[-1]['failures'], 2)


if __name__ == '__main__':
    unittest.main()
