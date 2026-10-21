import argparse
import json
from pathlib import Path

from .common import dump


def verify(left: Path, right: Path):
    result = []
    for k in (1, 2, 3):
        a = {tuple(r['skills']): r['count'] for r in json.loads((left / f'counts_{k}.json').read_text())}
        b = {tuple(r['skills']): r['count'] for r in json.loads((right / f'counts_{k}.json').read_text())}
        differences = sum(a.get(key) != b.get(key) for key in a.keys() | b.keys())
        record = {'k': k, 'unique_keys': len(a), 'total_occurrences': sum(a.values()), 'differences': differences}
        result.append(record)
        print(json.dumps(record), flush=True)
        if differences:
            samples = [key for key in a.keys() | b.keys() if a.get(key) != b.get(key)][:10]
            raise AssertionError(f'k={k} mismatch: {samples}')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('left', type=Path)
    p.add_argument('right', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = verify(a.left, a.right)
    if a.output:
        dump(a.output, result)
