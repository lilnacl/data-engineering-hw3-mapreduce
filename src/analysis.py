import csv
import itertools
import json
from pathlib import Path

from .common import dump


def export_csv(path, records):
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows({k: '; '.join(v) if isinstance(v, list) else v for k, v in r.items()} for r in records)


def query_dicts(con, sql):
    cursor = con.execute(sql)
    fields = [d[0] for d in cursor.description]
    return [dict(zip(fields, r)) for r in cursor.fetchall()]


def analyze(con, destination: Path):
    summary = query_dicts(con, '''SELECT count(*) AS vacancies, count(salary) AS with_salary,
        median(salary) AS median_salary, count(*) FILTER (WHERE len(skills)=0) AS without_skills,
        max(len(skills)) AS max_skills, avg(len(skills)) AS mean_skills FROM selected''')[0]
    summary['skill_count_distribution'] = query_dicts(con, 'SELECT len(skills) AS skills, count(*) AS vacancies FROM selected GROUP BY 1 ORDER BY 1')
    summary['salary_currency_gross'] = query_dicts(con, 'SELECT currency, gross, count(*) AS vacancies FROM selected GROUP BY 1,2 ORDER BY 3 DESC')
    stack_stats = query_dicts(con, '''SELECT t.stack, count(*) AS vacancies, count(v.salary) AS salary_n,
        median(v.salary) AS median_salary FROM stacks t JOIN selected v USING (vacancy_id)
        GROUP BY t.stack''')
    indexed = {tuple(r['stack']): r for r in stack_stats}
    effects = []
    for stack, row in indexed.items():
        if len(stack) not in (2, 3) or row['salary_n'] < 10:
            continue
        subsets = itertools.combinations(stack, len(stack) - 1)
        base = min(subsets, key=lambda subset: (-indexed[subset]['vacancies'], subset))
        baseline = indexed[base]
        if baseline['salary_n'] < 10 or not baseline['median_salary']:
            continue
        effects.append({'k': len(stack), 'stack': list(stack), 'vacancies': row['vacancies'],
                        'salary_n': row['salary_n'], 'median_salary': row['median_salary'],
                        'base': list(base), 'base_vacancies': baseline['vacancies'],
                        'base_salary_n': baseline['salary_n'], 'base_median': baseline['median_salary'],
                        'delta_rub': row['median_salary'] - baseline['median_salary'],
                        'delta_pct': 100 * (row['median_salary'] / baseline['median_salary'] - 1)})
    effects.sort(key=lambda r: (r['k'], -r['delta_pct'], r['stack']))
    rankings = {}
    for k in (2, 3):
        subset = [r for r in effects if r['k'] == k]
        rankings[f'positive_{k}'] = [r for r in subset if r['delta_rub'] > 0][:5]
        rankings[f'negative_{k}'] = sorted([r for r in subset if r['delta_rub'] < 0], key=lambda r: (r['delta_pct'], r['stack']))[:5]
    regions = query_dicts(con, '''SELECT area, count(*) AS vacancies, count(salary) AS salary_n,
        median(salary) AS median_salary,
        count(*) FILTER(WHERE len(skills)>0) AS with_skills,
        avg(len(skills)) AS mean_skills FROM selected GROUP BY area ORDER BY vacancies DESC, area LIMIT 3''')
    region_skills = []
    for region in regions:
        for k in (1, 2, 3):
            rows = con.execute('''SELECT t.stack, count(*) AS n, count(v.salary), median(v.salary)
                 FROM stacks t JOIN selected v USING(vacancy_id)
                 WHERE v.area=? AND len(t.stack)=? GROUP BY t.stack ORDER BY n DESC, t.stack LIMIT 5''', [region['area'], k]).fetchall()
            for stack, n, salary_n, median in rows:
                region_skills.append({'area': region['area'], 'k': k, 'stack': stack, 'vacancies': n,
                                      'share_pct': 100 * n / region['vacancies'], 'salary_n': salary_n, 'median_salary': median})
    for name, value in [('summary', summary), ('salary_rankings', rankings), ('regions', regions),
                         ('region_skills', region_skills), ('salary_effects', effects)]:
        dump(destination / f'{name}.json', value)
    export_csv(destination / 'salary_effects.csv', effects)
    export_csv(destination / 'regions.csv', regions)
    export_csv(destination / 'region_skills.csv', region_skills)
    print('ANALYSIS', json.dumps(summary, ensure_ascii=False), flush=True)
