// Persist randomly generated instance secrets. Never print their values.
const fs = require('node:fs');
const crypto = require('node:crypto');
const dir = '/data/config';
fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
for (const name of ['POSTGRES_PASSWORD', 'APP_SECRET', 'ENCRYPTION_KEY']) {
  const file = `${dir}/${name}`;
  const supplied = process.env[name];
  if (fs.existsSync(file)) {
    if (supplied && supplied !== fs.readFileSync(file, 'utf8').trim()) {
      throw new Error(`${name} differs from /data/config/${name}; restore the original value. See README for rotation.`);
    }
  } else {
    if (name === 'POSTGRES_PASSWORD' && fs.existsSync('/data/postgres/PG_VERSION')) {
      throw new Error('Existing database has no saved password. Restore /data/config from its backup.');
    }
    const value = supplied || crypto.randomBytes(32).toString(name === 'POSTGRES_PASSWORD' ? 'hex' : 'base64');
    if (/[\r\n]/.test(value) || value.length < 32) throw new Error(`${name} must be at least 32 characters with no newline`);
    fs.writeFileSync(file, value + '\n', { mode: 0o600, flag: 'wx' });
  }
}
