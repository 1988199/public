"""Linux离线回归；只操作TemporaryDirectory中的合成备份。"""
import gzip
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
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
        b.STOP_EVENT.clear()

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

    def test_stream_authentication_without_plaintext_file(self):
        src, enc = self.root / 'input', self.root / 'encrypted'
        src.write_bytes(os.urandom(2 * 1024 * 1024 + 7))
        key = os.urandom(32)
        expected = b.encrypt(src, enc, key)
        self.assertEqual(expected, hashlib.sha256(src.read_bytes()).digest())
        self.assertEqual(b.decrypt_stream(enc, key), expected)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'input', 'encrypted'})
        content = bytearray(enc.read_bytes())
        content[-1] ^= 1
        enc.write_bytes(content)
        with self.assertRaises(Exception):
            b.decrypt_stream(enc, key)

    def raw_bundle(self):
        with gzip.open(self.root / 'database.sql.gz', 'wb') as handle:
            handle.write(b'CREATE TABLE synthetic;\n-- Dump completed on test\n')
        for name in ('public-files.tgz', 'private-files.tgz'):
            with tarfile.open(self.root / name, 'w:gz') as archive:
                for index in range(3):
                    info = tarfile.TarInfo('ci.localhost/public/files/' + str(index))
                    payload = b'synthetic' * 1000
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
        (self.root / 'site-config.json').write_text(json.dumps({'db_name': 'synthetic', 'db_password': 'synthetic-only'}))
        (self.root / 'common-site-config.json').write_text('{}')

    def test_single_pass_attachment_validation(self):
        self.raw_bundle()
        with patch.object(b.gzip, 'open', wraps=gzip.open) as opened:
            b.verify_raw(self.root)
        paths = [Path(call.args[0]).name for call in opened.call_args_list]
        self.assertEqual(paths.count('public-files.tgz'), 1)
        self.assertEqual(paths.count('private-files.tgz'), 1)

    def test_attachment_crc_after_tar_end_is_checked(self):
        self.raw_bundle()
        path = self.root / 'private-files.tgz'
        content = bytearray(path.read_bytes())
        content[-8] ^= 1
        path.write_bytes(content)
        with self.assertRaises((gzip.BadGzipFile, EOFError)):
            b.verify_raw(self.root)

    def test_attachment_truncated_gzip_is_rejected(self):
        self.raw_bundle()
        path = self.root / 'public-files.tgz'
        path.write_bytes(path.read_bytes()[:-4])
        with self.assertRaises((gzip.BadGzipFile, EOFError)):
            b.verify_raw(self.root)

    def test_shutdown_wakes_idle_wait_immediately(self):
        b.stop(None, None)
        self.assertTrue(b.STOP)
        self.assertTrue(b.STOP_EVENT.is_set())

    def test_idle_and_disabled_backup_waits(self):
        for enabled, delay in [('1', 60), ('0', None)]:
            b.STOP = False
            def waiting(seconds):
                self.assertEqual(seconds, delay)
                b.STOP = True
            env = {'BACKUP_ENABLED': enabled, 'BACKUP_START_DELAY_SECONDS': '60'}
            with patch.dict(os.environ, env), patch.object(b, 'read_status', return_value={}), \
                 patch.object(b, 'status'), patch.object(b.time, 'time', return_value=1000), \
                 patch.object(b.STOP_EVENT, 'wait', side_effect=waiting), \
                 patch.object(b.subprocess, 'Popen') as popen:
                b.daemon()
                popen.assert_not_called()

    def test_healthcheck_batches_processes_and_rejects_bad_states(self):
        # 只模拟系统命令，不接触真实Supervisor、数据库或Web。
        tools = self.root / 'bin'
        tools.mkdir()
        supervisor = tools / 'supervisorctl'
        supervisor.write_text('''#!/bin/bash
printf x >> "$CALL_COUNT"
for name in "${@:2}"; do
  [[ "$name" != "$MISSING" ]] || continue
  state=RUNNING
  [[ "$name" != "$STOPPED" ]] || state=STOPPED
  printf '%s %s pid 1, uptime 0:00:01\\n' "$name" "$state"
done
[[ "$DUPLICATE" != 1 ]] || echo 'nginx RUNNING pid 1'
exit "${MANAGER_EXIT:-0}"
''')
        for name, content in {'redis-cli': 'echo PONG', 'curl': 'echo pong', 'cmp': 'exit 0', 'sudo': 'exit 0'}.items():
            (tools / name).write_text('#!/bin/bash\n' + content + '\n')
        for tool in tools.iterdir():
            tool.chmod(0o755)
        script = Path(__file__).resolve().parents[1] / 'docker/healthcheck.sh'
        for env, success in [({}, True), ({'MISSING': 'nginx'}, False), ({'STOPPED': 'worker-long'}, False),
                             ({'DUPLICATE': '1'}, False), ({'MANAGER_EXIT': '2'}, False)]:
            counter = self.root / 'calls'
            counter.write_text('')
            result = subprocess.run(['bash', str(script)], env={**os.environ, 'PATH': str(tools) + ':' + os.environ['PATH'],
                'CALL_COUNT': str(counter), 'MISSING': '', 'STOPPED': '', 'DUPLICATE': '', 'MANAGER_EXIT': '0', **env}, capture_output=True)
            self.assertEqual(result.returncode == 0, success, result.stderr.decode())
            self.assertEqual(counter.read_text(), 'x')

    def test_connection_configuration_skips_only_when_equal(self):
        script = (Path(__file__).resolve().parents[1] / 'docker/entrypoint.sh').read_text()
        section = 'if ! jq -e ' + script.split('if ! jq -e ', 1)[1].split('\nif [[ ! -f "sites/', 1)[0]
        sites = self.root / 'sites'
        sites.mkdir()
        correct = {key: 'redis://127.0.0.1:6379' for key in ('redis_cache', 'redis_queue', 'redis_socketio')}
        correct['socketio_port'] = 9000
        for config, expected in [(correct, 0), ({}, 4), ({**correct, 'socketio_port': 9001}, 4)]:
            (sites / 'common_site_config.json').write_text(json.dumps(config))
            result = subprocess.run(['bash', '-c', 'set -Eeuo pipefail; run_bench() { echo call; };\n' + section],
                cwd=self.root, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.count('call'), expected)

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
             patch.object(b, 'status', side_effect=record), patch.object(b.STOP_EVENT, 'wait'), \
             patch.object(b.subprocess, 'Popen', return_value=child) as popen:
            b.daemon()
        self.assertEqual(popen.call_count, 2)
        self.assertEqual(states[-1]['state'], 'failed')
        self.assertEqual(states[-1]['failures'], 2)


if __name__ == '__main__':
    unittest.main()
