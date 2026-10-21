import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .common import ROOT, WORK, dump, s3_client, BUCKET


def measure(command, log):
    started = time.perf_counter()
    peak = samples = 0
    registry = WORK / 'profile_pids.txt'
    registry.write_text('')
    with log.open('w') as output:
        child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, cwd=ROOT,
                                 env=os.environ | {'HW_PID_REGISTRY': str(registry)})
        process = psutil.Process(child.pid)
        while child.poll() is None:
            rss = 0
            pids = {child.pid} | {int(pid) for pid in registry.read_text().splitlines() if pid}
            tree = []
            for pid in pids:
                try:
                    tree.append(psutil.Process(pid))
                except psutil.NoSuchProcess:
                    pass
            for p in tree:
                try:
                    rss += p.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
            peak = max(peak, rss)
            samples += 1
            time.sleep(0.01)
        code = child.wait()
    seconds = time.perf_counter() - started
    if code:
        raise RuntimeError(log.read_text())
    return {'wall_seconds': seconds, 'peak_client_rss_mib': peak / 1024**2, 'samples': samples}


def run(trials, optimized_only=False):
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    profile_path = evidence / 'profile_runs.json'
    runs = json.loads(profile_path.read_text()) if optimized_only else []
    for trial in range(1, trials + 1):
        for engine in (('mapreduce_prefilter',) if optimized_only else ('mapreduce_baseline', 'mapreduce_combiner', 'duckdb', 'mapreduce_prefilter')):
            destination = WORK / 'benchmarks' / f'{engine}_{trial}'
            module = 'src.duckdb_job' if engine == 'duckdb' else 'src.mapreduce'
            command = [sys.executable, '-m', module, '--output', str(destination)]
            if engine == 'mapreduce_baseline':
                command.append('--no-combiner')
            if engine == 'mapreduce_prefilter':
                command.extend(['--prefilter', '--chunk-rows', '200'])
            measurement = measure(command, evidence / f'{engine}_{trial}.log')
            stats = json.loads((destination / 'stats.json').read_text())
            record = {'engine': engine, 'trial': trial, **measurement, 'compute_seconds': stats['seconds']}
            from .verify import verify
            verify(ROOT / 'results/mapreduce', destination)
            runs.append(record)
            dump(evidence / 'profile_runs.json', runs)
            print(json.dumps(record), flush=True)
    dump(evidence / 'environment.json', {'platform': platform.platform(), 'processor': platform.machine(),
         'python': platform.python_version(), 'logical_cpus': psutil.cpu_count(),
         'physical_memory_gib': psutil.virtual_memory().total / 1024**3,
         'sampling_interval_seconds': 0.01, 'workers_and_duckdb_threads': 4,
         'notes': 'Fresh process per run; sampled sum of RSS for coordinator plus registered mapper workers (DuckDB: one multithreaded process). RustFS and multiprocessing resource tracker excluded. Shared pages counted per process. OS file cache not flushed. Wall times include imports and result serialization.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--optimized-only', action='store_true')
    args = parser.parse_args()
    run(args.trials, args.optimized_only)
