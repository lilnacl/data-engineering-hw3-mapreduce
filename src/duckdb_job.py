import argparse
import json
import time
from pathlib import Path

import duckdb

from .common import ROOT, WORK, credentials, dump


def connect():
    extension_dir = WORK / 'duckdb_extensions'
    extension_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute('SET extension_directory = ?', [str(extension_dir)])
    con.execute('SET threads=4')
    con.execute("SET memory_limit='2GB'")
    con.execute('INSTALL httpfs; LOAD httpfs;')
    c = credentials()
    def literal(s):
        return "'" + s.replace("'", "''") + "'"
    con.execute('CREATE SECRET (TYPE S3, KEY_ID ' + literal(c['access']) +
                ', SECRET ' + literal(c['secret']) + ', ENDPOINT ' + literal(c['endpoint'].split('://')[1]) +
                ", REGION 'us-east-1', URL_STYLE 'path', USE_SSL false)")
    return con


def run(destination: Path, analytics=False):
    con = connect()
    started = time.perf_counter()
    con.execute((ROOT / 'sql/variant.sql').read_text())
    con.execute((ROOT / 'sql/combinations.sql').read_text())
    for k in (1, 2, 3):
        rows = con.execute('SELECT stack, n FROM frequencies WHERE k=? ORDER BY stack', [k]).fetchall()
        dump(destination / f'counts_{k}.json', [{'skills': stack, 'count': n} for stack, n in rows])
    stats = {'selected_rows': con.execute('SELECT count(*) FROM selected').fetchone()[0],
             'distinct_ids': con.execute('SELECT count(DISTINCT vacancy_id) FROM selected').fetchone()[0],
             'seconds': time.perf_counter() - started, 'duckdb_version': duckdb.__version__,
             'emitted': [con.execute('SELECT sum(n) FROM frequencies WHERE k=?', [k]).fetchone()[0] for k in (1,2,3)]}
    dump(destination / 'stats.json', stats)
    print(json.dumps(stats, indent=2), flush=True)
    if analytics:
        from .analysis import analyze
        analyze(con, destination.parent / 'analysis')
    con.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--analytics', action='store_true')
    a = p.parse_args()
    run(a.output, a.analytics)
