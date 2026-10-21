import hashlib
import json

from .common import BUCKET, ROOT, dump, s3_client


def run():
    s3 = s3_client()
    manifest = []
    paths = sorted((ROOT / 'results').rglob('*.json')) + sorted((ROOT / 'results').rglob('*.csv'))
    for path in paths:
        key = str(path.relative_to(ROOT))
        content = path.read_bytes()
        s3.put_object(Bucket=BUCKET, Key=key, Body=content)
        retrieved = s3.get_object(Bucket=BUCKET, Key=key)['Body'].read()
        assert retrieved == content, key
        manifest.append({'key': key, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'get_verified': True})
    dump(ROOT / 'evidence/s3_results.json', manifest)
    for entry in manifest:
        print(json.dumps(entry), flush=True)


if __name__ == '__main__':
    run()
