import argparse
import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

from .common import BUCKET, KEY, WORK, dump, s3_client


def start(binary: str):
    WORK.mkdir(parents=True, exist_ok=True)
    cp = WORK / '.credentials.json'
    if not cp.exists():
        dump(cp, {'endpoint': 'http://127.0.0.1:9000', 'access': 'homework3-local', 'secret': secrets.token_hex(24)})
        cp.chmod(0o600)
    c = json.loads(cp.read_text())
    disks = [WORK / 'storage' / f'disk{i}' for i in range(1, 5)]
    for d in disks:
        d.mkdir(parents=True, exist_ok=True)
    env = os.environ | {'RUSTFS_ACCESS_KEY': c['access'], 'RUSTFS_SECRET_KEY': c['secret'],
        'RUSTFS_STORAGE_CLASS_STANDARD': 'EC:2', 'RUSTFS_ERASURE_SET_DRIVE_COUNT': '4',
        'RUSTFS_UNSAFE_BYPASS_DISK_CHECK': 'true', 'RUSTFS_OBS_LOG_DIRECTORY': str(WORK / 'server-logs')}
    command = [str(Path(binary).resolve()), 'server', '--address', '127.0.0.1:9000',
               '--console-enable', '--console-address', '127.0.0.1:9001', *map(str, disks)]
    with (WORK / 'rustfs.log').open('ab') as log:
        p = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    (WORK / 'server.pid').write_text(str(p.pid))
    for _ in range(90):
        if p.poll() is not None:
            raise RuntimeError((WORK / 'rustfs.log').read_text()[-4000:])
        try:
            s3_client().list_buckets()
            print('RustFS ready: S3 127.0.0.1:9000; console 127.0.0.1:9001; EC 2+2', flush=True)
            return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError('RustFS did not become ready')


def upload(source: str, evidence: Path):
    s = s3_client()
    if BUCKET not in [b['Name'] for b in s.list_buckets()['Buckets']]:
        s.create_bucket(Bucket=BUCKET)
    path = Path(source)
    with path.open('rb') as body:
        response = s.put_object(Bucket=BUCKET, Key=KEY, Body=body, ContentLength=path.stat().st_size)
    print('PUT', f's3://{BUCKET}/{KEY}', response['ResponseMetadata']['HTTPStatusCode'], flush=True)
    sha = hashlib.sha256()
    body = s.get_object(Bucket=BUCKET, Key=KEY)['Body']
    for block in iter(lambda: body.read(1024 * 1024), b''):
        sha.update(block)
    body.close()
    head = s.head_object(Bucket=BUCKET, Key=KEY)
    record = {'bucket': BUCKET, 'key': KEY, 'bytes': head['ContentLength'], 'sha256_s3_get': sha.hexdigest(),
              'etag': head['ETag'], 'source_url': 'https://drive.google.com/file/d/1rLEu3N2isIBhAkK1EcSJ2482ouOPAots/view'}
    assert record['sha256_s3_get'] == '303db922b541e4440906f5a7e8be32fb55e8808f950ffddb8c272f1548212a65'
    dump(evidence / 'source.json', record)
    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['start', 'upload'])
    p.add_argument('--binary')
    p.add_argument('--source')
    p.add_argument('--evidence', type=Path, default=Path('evidence'))
    a = p.parse_args()
    start(a.binary) if a.action == 'start' else upload(a.source, a.evidence)
