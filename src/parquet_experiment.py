import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

from .benchmark import measure
from .common import BUCKET, KEY, ROOT, WORK, dump, s3_client
from .duckdb_job import connect
from .verify import verify

CSV_URI = f's3://{BUCKET}/{KEY}'
CSV_READER = f"read_csv('{CSV_URI}',\n                  header=true, delim=',', all_varchar=true)"
EVIDENCE = ROOT / 'evidence/parquet'
RESULTS = ROOT / 'results/parquet'


def reader(kind, path=None):
    uri = path or CSV_URI
    literal = "'" + str(uri).replace("'", "''") + "'"
    if kind == 'csv':
        return f"read_csv({literal}, header=true, delim=',', all_varchar=true)"
    if kind == 'parquet':
        return f'read_parquet({literal})'
    raise ValueError(kind)


def variant_sql(kind, path=None):
    sql = (ROOT / 'sql/variant.sql').read_text()
    if sql.count(CSV_READER) != 1:
        raise ValueError('CSV reader in sql/variant.sql changed')
    return sql.replace(CSV_READER, reader(kind, path))


def convert(key, output):
    con = connect()
    uri = f's3://{BUCKET}/{key}'
    started = time.perf_counter()
    rows = con.execute(f"COPY (SELECT * FROM {reader('csv')}) TO '{uri}' "
                       '(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)').fetchone()[0]
    seconds = time.perf_counter() - started
    head = s3_client().head_object(Bucket=BUCKET, Key=key)
    result = {'key': key, 'rows': rows, 'bytes': head['ContentLength'],
              'copy_seconds': seconds, 'compression': 'ZSTD', 'row_group_size': 122880}
    dump(output, result)
    print(json.dumps(result), flush=True)
    con.close()


def query(kind, key, output):
    started = time.perf_counter()
    con = connect()
    path = f's3://{BUCKET}/{key}' if kind == 'parquet' else None
    con.execute(variant_sql(kind, path))
    con.execute((ROOT / 'sql/combinations.sql').read_text())
    for k in (1, 2, 3):
        rows = con.execute('SELECT stack, n FROM frequencies WHERE k=? ORDER BY stack', [k]).fetchall()
        dump(output / f'counts_{k}.json', [{'skills': skills, 'count': count} for skills, count in rows])
    stats = {'format': kind, 'selected_rows': con.execute('SELECT count(*) FROM selected').fetchone()[0],
             'stage_seconds': time.perf_counter() - started}
    dump(output / 'stats.json', stats)
    print(json.dumps(stats), flush=True)
    con.close()


def validate_data(key):
    con = connect()
    con.execute("SET memory_limit='4GB'")
    spill = WORK / 'parquet_validation_spill'
    spill.mkdir(exist_ok=True)
    con.execute('SET temp_directory=?', [str(spill)])
    con.execute(f"CREATE TEMP TABLE csv_data AS SELECT * FROM {reader('csv')}")
    con.execute(f"CREATE TEMP VIEW parquet_data AS SELECT * FROM {reader('parquet', f's3://{BUCKET}/{key}')}")
    csv_schema = con.execute('DESCRIBE csv_data').fetchall()
    parquet_schema = con.execute('DESCRIBE parquet_data').fetchall()
    assert [(r[0], r[1]) for r in csv_schema] == [(r[0], r[1]) for r in parquet_schema]
    differences = []
    for left, right in [('csv_data', 'parquet_data'), ('parquet_data', 'csv_data')]:
        differences.append(con.execute(f'SELECT count(*) FROM (SELECT * FROM {left} EXCEPT ALL SELECT * FROM {right})').fetchone()[0])
    result = {'csv_rows': con.execute('SELECT count(*) FROM csv_data').fetchone()[0],
              'parquet_rows': con.execute('SELECT count(*) FROM parquet_data').fetchone()[0],
              'columns': len(csv_schema), 'schema_equal': True,
              'csv_minus_parquet': differences[0], 'parquet_minus_csv': differences[1]}
    assert differences == [0, 0], result
    dump(EVIDENCE / 'data_verification.json', result)
    print(json.dumps(result), flush=True)
    con.close()


def experiment(trials):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    destination = WORK / 'parquet_experiment'
    destination.mkdir(exist_ok=True)
    conversions = []
    for trial in range(1, trials + 1):
        key = f'derived/it_vacancies_2024_trial{trial}.parquet'
        output = destination / f'conversion_{trial}.json'
        command = [sys.executable, '-m', 'src.parquet_experiment', 'convert', '--key', key, '--output', str(output)]
        measured = measure(command, EVIDENCE / f'conversion_{trial}.log')
        record = json.loads(output.read_text()) | measured | {'trial': trial}
        conversions.append(record)
        dump(EVIDENCE / 'conversion_runs.json', conversions)
        print(json.dumps(record), flush=True)
    validate_data(key)
    runs = []
    verifications = []
    for trial in range(1, trials + 1):
        for kind in (('csv', 'parquet') if trial % 2 else ('parquet', 'csv')):
            output = destination / f'{kind}_{trial}'
            command = [sys.executable, '-m', 'src.parquet_experiment', 'query', '--format', kind,
                       '--key', key, '--output', str(output)]
            measured = measure(command, EVIDENCE / f'{kind}_{trial}.log')
            stats = json.loads((output / 'stats.json').read_text())
            checked = verify(ROOT / 'results/mapreduce', output)
            verifications.append({'format': kind, 'trial': trial, 'counts': checked})
            record = measured | stats | {'trial': trial}
            runs.append(record)
            dump(EVIDENCE / 'profile_runs.json', runs)
            dump(EVIDENCE / 'frequency_verification.json', verifications)
            print(json.dumps(record), flush=True)
    csv_time = statistics.median(r['wall_seconds'] for r in runs if r['format'] == 'csv')
    parquet_time = statistics.median(r['wall_seconds'] for r in runs if r['format'] == 'parquet')
    csv_rss = statistics.median(r['peak_client_rss_mib'] for r in runs if r['format'] == 'csv')
    parquet_rss = statistics.median(r['peak_client_rss_mib'] for r in runs if r['format'] == 'parquet')
    conversion_time = statistics.median(r['wall_seconds'] for r in conversions)
    csv_bytes = s3_client().head_object(Bucket=BUCKET, Key=KEY)['ContentLength']
    parquet_bytes = conversions[-1]['bytes']
    summary = {'csv_bytes': csv_bytes, 'parquet_bytes': parquet_bytes, 'parquet_key': key,
               'csv_wall_median': csv_time, 'parquet_wall_median': parquet_time,
               'csv_rss_median_mib': csv_rss, 'parquet_rss_median_mib': parquet_rss,
               'conversion_wall_median': conversion_time,
               'speedup': csv_time / parquet_time, 'size_ratio': csv_bytes / parquet_bytes,
               'rss_reduction_pct': 100 * (1 - parquet_rss / csv_rss),
               'break_even_queries': math.ceil(conversion_time / (csv_time - parquet_time)) if csv_time > parquet_time else None,
               'trials_per_format': trials, 'logical_data_equal': True, 'all_frequencies_equal': True,
               'notes': 'Fresh process per run. Wall time includes connection, query and JSON. RSS sampled every 10 ms; RustFS excluded. OS cache not flushed. No Parquet file prefiltered to Go; full 23-column dataset preserved.'}
    dump(RESULTS / 'summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['convert', 'query', 'run'])
    parser.add_argument('--key', default='derived/it_vacancies_2024_trial3.parquet')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--format', choices=['csv', 'parquet'])
    parser.add_argument('--trials', type=int, default=3)
    args = parser.parse_args()
    if args.action == 'convert':
        convert(args.key, args.output)
    elif args.action == 'query':
        query(args.format, args.key, args.output)
    else:
        experiment(args.trials)
