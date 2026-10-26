"""受监督的完整备份：专用目录、互斥、校验、有限重试及可选加密外部副本。"""
import argparse
import contextlib
import fcntl
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tarfile
import time
import uuid
from threading import Event
from datetime import datetime, timezone

BENCH = Path('/home/frappe/frappe-bench')
SITE = os.environ.get('SITE_NAME', 'erp.localhost')
if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', SITE):
    raise ValueError('invalid site name')
ROOT = BENCH / 'sites' / SITE / 'private' / 'automatic_backups'
MAGIC = b'ERPBK001'
STOP = False
CHILD = None
STOP_EVENT = Event()


def number(key, default, low=1, high=31536000):
    value = int(os.environ.get(key, str(default)))
    if not low <= value <= high:
        raise ValueError('invalid runtime setting: ' + key)
    return value


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temp.open('w', encoding='utf-8') as handle:
        os.chmod(temp, 0o600)
        json.dump(value, handle)
    temp.replace(path)


def read_status():
    validate_root()
    path = ROOT / 'status.json'
    if path.is_symlink():
        raise ValueError('backup status cannot be a symlink')
    return json.loads(path.read_text()) if path.exists() else {}


def validate_root():
    site = (BENCH / 'sites' / SITE).resolve()
    if ROOT.is_symlink() or not ROOT.resolve().is_relative_to(site):
        raise ValueError('local backup directory escaped site')


def status(**values):
    old = read_status()
    old.update(values)
    atomic_json(ROOT / 'status.json', old)


@contextlib.contextmanager
def backup_lock(root):
    if root.is_symlink():
        raise ValueError('backup lock root cannot be a symlink')
    if root == ROOT:
        validate_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / '.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('backup already running') from None
        yield


def key_bytes():
    path = os.environ.get('BACKUP_ENCRYPTION_KEY_FILE')
    if not path:
        return None
    file = Path(path)
    if not file.is_file() or file.stat().st_size != 32:
        raise ValueError('backup encryption key must be a 32-byte regular file')
    with file.open('rb') as handle:
        key = handle.read(33)
    if len(key) != 32:
        raise ValueError('backup encryption key must contain 32 raw bytes')
    return key


def encrypt(source, target, key):
    """分块 AES-256-GCM；密钥不进入命令行、日志、备份包或状态文件。"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    nonce = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(MAGIC)
    digest = hashlib.sha256()
    with source.open('rb') as src, target.open('xb') as dst:
        os.chmod(target, 0o600)
        dst.write(MAGIC + nonce)
        while chunk := src.read(1024 * 1024):
            digest.update(chunk)
            dst.write(cipher.update(chunk))
        dst.write(cipher.finalize())
        dst.write(cipher.tag)
    return digest.digest()


def decrypt_stream(source, key, output=None):
    """完整认证并计算明文摘要；验证模式不写出临时明文，也不占用整包内存。"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    digest = hashlib.sha256()
    with source.open('rb') as src:
        if src.read(8) != MAGIC:
            raise ValueError('unknown backup format')
        nonce = src.read(12)
        size = os.fstat(src.fileno()).st_size - 36
        if size < 0:
            raise ValueError('truncated encrypted backup')
        src.seek(-16, 2)
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, src.read(16))).decryptor()
        cipher.authenticate_additional_data(MAGIC)
        src.seek(20)
        while size:
            chunk = src.read(min(size, 1024 * 1024))
            if not chunk:
                raise ValueError('truncated encrypted backup')
            size -= len(chunk)
            plain = cipher.update(chunk)
            digest.update(plain)
            if output is not None:
                output.write(plain)
        final = cipher.finalize()
        digest.update(final)
        if output is not None:
            output.write(final)
    return digest.digest()


def decrypt(source, target, key):
    """认证成功才将临时输出提升为目标；认证失败不留下伪恢复文件。"""
    if target.exists():
        raise FileExistsError('restore target already exists')
    temp = target.with_suffix(target.suffix + '.partial')
    if temp.exists():
        raise FileExistsError('partial restore target already exists')
    try:
        with temp.open('xb') as dst:
            os.chmod(temp, 0o600)
            decrypt_stream(source, key, dst)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def verify_database(path):
    """固定大小分块验证，避免大数据库备份被整份加载到内存。"""
    found_table = False
    tail = b''
    with gzip.open(path, 'rb') as handle:
        while chunk := handle.read(1024 * 1024):
            combined = tail + chunk
            found_table |= b'CREATE TABLE' in combined
            tail = combined[-8192:]
    if not found_table or b'Dump completed' not in tail:
        raise ValueError('database dump incomplete')


def verify_raw(folder):
    """校验完整压缩流和附件内容，不仅检查文件存在。"""
    verify_database(folder / 'database.sql.gz')
    for name in ('public-files.tgz', 'private-files.tgz'):
        # 一次顺序解压同时核验tar成员与gzip尾部CRC，避免两次解压整个附件包。
        with gzip.open(folder / name, 'rb') as compressed:
            with tarfile.open(fileobj=compressed, mode='r|', stream=True) as archive:
                for member in archive:
                    if member.isfile():
                        with archive.extractfile(member) as handle:
                            while handle.read(1024 * 1024):
                                pass
            # tar结束标记之后仍须读至gzip EOF，不能漏掉损坏尾部或追加gzip成员。
            while compressed.read(1024 * 1024):
                pass
    config = json.loads((folder / 'site-config.json').read_text())
    if not config.get('db_name') or not config.get('db_password'):
        raise ValueError('site configuration incomplete')
    if not isinstance(json.loads((folder / 'common-site-config.json').read_text()), dict):
        raise ValueError('common configuration incomplete')


def manifest(folder, encrypted=False):
    files = []
    for path in sorted(folder.iterdir()):
        if path.name != 'manifest.json' and path.is_file():
            with path.open('rb') as handle:
                files.append({'name': path.name, 'sha256': hashlib.file_digest(handle, 'sha256').hexdigest(),
                              'bytes': path.stat().st_size})
            os.chmod(path, 0o600)
    atomic_json(folder / 'manifest.json', {'format': 'erpnext-runtime-v1', 'complete': True,
                'created': time.time(), 'encrypted': encrypted, 'files': files})


def verify_manifest(folder, checksum=True):
    if (folder / 'manifest.json').is_symlink():
        raise ValueError('manifest cannot be a symlink')
    data = json.loads((folder / 'manifest.json').read_text())
    if not isinstance(data, dict):
        raise ValueError('invalid manifest type')
    if data.get('format') != 'erpnext-runtime-v1' or data.get('complete') is not True or not data.get('files'):
        raise ValueError('invalid backup manifest')
    for item in data['files']:
        name = item['name']
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('unsafe backup filename')
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('invalid backup component')
        if path.stat().st_size != item['bytes']:
            raise ValueError('backup component size mismatch')
        if checksum:
            with path.open('rb') as handle:
                digest = hashlib.file_digest(handle, 'sha256').hexdigest()
            if digest != item['sha256']:
                raise ValueError('backup component checksum mismatch')
    expected = {'manifest.json'} | {item['name'] for item in data['files']}
    if {path.name for path in folder.iterdir()} != expected:
        raise ValueError('unrecognized content in backup directory')
    return data


def prune(root, days, keep=2):
    """只清理本工具拥有且清单完整的备份，绝不扫描用户旧备份目录。"""
    candidates = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir() or not re.fullmatch(r'backup-\d{8}T\d{12}Z', path.name):
            continue
        if path.resolve().parent != root.resolve():
            raise ValueError('backup retention path escaped')
        try:
            data = verify_manifest(path, checksum=False)
        except (ValueError, OSError, KeyError):
            continue
        candidates.append((float(data['created']), path))
    candidates.sort(reverse=True)
    for created, path in candidates[keep:]:
        if created < time.time() - days * 86400:
            try:
                verify_manifest(path)
            except (ValueError, OSError, KeyError):
                continue
            shutil.rmtree(path)


def prune_interrupted(root):
    """强制终止遗留的半成品须有专用所有权标记且超过两天才可删除。"""
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir() or not re.fullmatch(r'backup-\d{8}T\d{12}Z\.partial-[a-z0-9_]{8}', path.name):
            continue
        if path.resolve().parent != root.resolve():
            raise ValueError('partial backup path escaped')
        marker = path / '.stage.json'
        if marker.is_symlink():
            continue
        try:
            data = json.loads(marker.read_text())
            if data.get('format') == 'runtime-backup-stage-v1' and time.time() - float(data['created']) > 172800:
                shutil.rmtree(path)
        except (OSError, ValueError, KeyError):
            continue


def one_backup():
    import frappe
    os.umask(0o077)
    key = key_bytes()
    external = os.environ.get('BACKUP_COPY_DIR')
    if external and not key:
        raise ValueError('external copies require BACKUP_ENCRYPTION_KEY_FILE')
    with backup_lock(ROOT), contextlib.ExitStack() as cleanup:
        prune_interrupted(ROOT)
        status(state='running', started=time.time())
        name = 'backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        partial = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix=name + '.partial-', dir=ROOT)))
        atomic_json(partial / '.stage.json', {'format': 'runtime-backup-stage-v1', 'created': time.time()})
        raw = partial / 'payload'
        raw.mkdir(mode=0o700)
        os.chdir(BENCH / 'sites')
        # 官方附件备份保存get_site_path的路径，必须采用Bench标准相对sites路径，
        # 否则bench restore会把绝对路径层级带入附件目录，无法原位恢复。
        frappe.init(site=SITE, sites_path='.')
        frappe.connect()
        try:
            if frappe.get_system_settings('encrypt_backup') and not key:
                raise ValueError('site encryption policy requires a runtime encryption key')
            from frappe.utils.backups import BackupGenerator
            gen = BackupGenerator(frappe.conf.db_name, frappe.conf.db_user, frappe.conf.db_password,
                db_host=frappe.conf.db_host, db_port=frappe.conf.db_port, db_socket=frappe.conf.db_socket,
                db_type=frappe.conf.db_type, backup_path=str(raw), ignore_conf=True, compress_files=True,
                backup_path_db=str(raw / 'database.sql.gz'), backup_path_conf=str(raw / 'site-config.json'),
                backup_path_files=str(raw / 'public-files.tgz'), backup_path_private_files=str(raw / 'private-files.tgz'))
            # 使用官方生成器的完整原语，先验证明文，再按独立密钥加密整个包。
            with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                status(phase='database')
                gen.take_dump()
                status(phase='site-configuration')
                gen.copy_site_config()
                status(phase='attachments')
                gen.backup_files()
            shutil.copyfile(BENCH / 'sites/common_site_config.json', raw / 'common-site-config.json')
            atomic_json(raw / 'applications.json', {app: getattr(importlib.import_module(app), '__version__', 'unknown')
                        for app in frappe.get_installed_apps()})
        finally:
            frappe.destroy()
        status(phase='validation')
        verify_raw(raw)
        manifest(raw)
        if key:
            status(phase='encryption')
            archive = partial / 'payload.tar'
            with tarfile.open(archive, 'w') as tar:
                tar.add(raw, arcname='backup')
            expected = encrypt(archive, partial / 'backup.enc', key)
            # 保留完整GCM认证与SHA-256比对，但不再写出和重读整包verify.tar。
            if decrypt_stream(partial / 'backup.enc', key) != expected:
                raise ValueError('encrypted backup verification failed')
            archive.unlink()
            shutil.rmtree(raw)
            manifest(partial, encrypted=True)
            final = ROOT / name
            partial.rename(final)
        else:
            final = ROOT / name
            raw.rename(final)
        verify_manifest(final)
        prune(ROOT, number('BACKUP_RETENTION_DAYS', 7))
        if external:
            status(phase='external-copy')
            target = Path(external) / SITE / 'runtime-v1'
            if not Path(external).is_dir() or target.is_symlink():
                raise ValueError('external copy directory must be pre-mounted')
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            if target.resolve() == ROOT.resolve() or ROOT.resolve() in target.resolve().parents:
                raise ValueError('external copy cannot be inside local backups')
            prune_interrupted(target)
            staged = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix=name + '.partial-', dir=target)))
            atomic_json(staged / '.stage.json', {'format': 'runtime-backup-stage-v1', 'created': time.time()})
            shutil.copytree(final, staged, dirs_exist_ok=True)
            verify_manifest(staged)
            staged.rename(target / name)
            prune(target, number('BACKUP_COPY_RETENTION_DAYS', 30))
        status(state='ok', phase='complete', last_success=time.time(), last_backup=name, failures=0, external_copy=bool(external))


def stop(_signum, _frame):
    global STOP
    STOP = True
    STOP_EVENT.set()
    if CHILD and CHILD.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(CHILD.pid, signal.SIGTERM)
            try:
                CHILD.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(CHILD.pid, signal.SIGKILL)
                CHILD.wait()


def daemon():
    global CHILD
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    flag = os.environ.get('BACKUP_ENABLED', '1')
    if flag not in ('0', '1'):
        raise ValueError('BACKUP_ENABLED must be 0 or 1')
    enabled = flag == '1'
    interval = number('BACKUP_INTERVAL_SECONDS', 21600, low=60)
    retries = number('BACKUP_RETRIES', 3, high=5)
    timeout = number('BACKUP_TIMEOUT_SECONDS', 900, low=30, high=86400)
    delay = number('BACKUP_START_DELAY_SECONDS', 60, low=0)
    previous = read_status()
    status(enabled=enabled, service_started=time.time())
    next_run = max(time.time() + delay, previous.get('last_success', 0) + interval)
    while not STOP:
        if enabled and time.time() >= next_run:
            success = False
            for attempt in range(retries):
                if STOP:
                    break
                CHILD = subprocess.Popen([sys.executable, __file__, 'once'], start_new_session=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    code = CHILD.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(CHILD.pid, signal.SIGTERM)
                    try:
                        CHILD.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(CHILD.pid, signal.SIGKILL)
                        CHILD.wait()
                    code = 1
                if code == 0:
                    success = True
                    print('完整备份及所配置副本校验成功', flush=True)
                    break
                if code == 75:
                    break
                if not STOP:
                    status(state='retrying', failures=attempt + 1, last_failure=time.time())
                    STOP_EVENT.wait(min(5 * (2 ** attempt), 60))
            if not success and not STOP and code != 75:
                status(state='failed', last_failure=time.time(), failures=retries)
                print('备份失败：已达有限重试次数；请检查私有状态及存储权限', flush=True)
            next_run = time.time() + interval
        # 空闲时最多每分钟核对一次墙钟，保留计划时间精度且可被停机信号立即唤醒。
        # 关闭备份时无限等待信号，不再每秒空转。短等待仍按实际到期时间执行。
        if not STOP:
            STOP_EVENT.wait(max(0, min(next_run - time.time(), 60)) if enabled else None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['daemon', 'once', 'status', 'decrypt'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--target', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'daemon':
            daemon()
        elif args.mode == 'once':
            one_backup()
        elif args.mode == 'status':
            print(json.dumps(read_status()))
        else:
            decrypt(args.source, args.target, key_bytes())
    except Exception as error:
        # 不输出第三方异常文本或堆栈，避免数据库凭据进入容器日志。
        print('backup operation failed: ' + type(error).__name__, file=sys.stderr)
        if args.mode == 'once' and not (isinstance(error, RuntimeError) and str(error) == 'backup already running'):
            with contextlib.suppress(Exception):
                status(last_error_type=type(error).__name__)
        sys.exit(75 if isinstance(error, RuntimeError) and str(error) == 'backup already running' else 1)
