import csv
from collections import Counter

import duckdb

from src.common import ROOT
from src.mapreduce import map_chunk, reduce_chunk


def test_independent_sql_matches_hand_checked_csv(tmp_path):
    rows = [
        ['1', 'Go developer', 'Программист, разработчик', 'Go; Golang; SQL; sql; Docker', 'Москва', '100', '300', 'RUR', 'false'],
        ['2', 'Backend', 'Программист, разработчик', 'Golang; SQL', 'Москва', '200', '', 'RUR', 'false'],
        ['3', 'Go DevOps', 'DevOps-инженер', 'Go; SQL', 'Москва', '900', '', 'RUR', 'false'],
        ['4', 'Django developer', 'Программист, разработчик', 'MongoDB; Django', 'Москва', '50', '', 'RUR', 'false'],
        ['5', 'Go developer', 'Программист, разработчик', '', 'Москва', '1000', '', 'USD', 'false'],
    ]
    fields = ['vacancy_id', 'name', 'role', 'key_skills', 'area', 'salary_from', 'salary_to', 'currency', 'gross']
    path = tmp_path / 'fixture.csv'
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)
    con = duckdb.connect()
    sql = (ROOT / 'sql/variant.sql').read_text().replace('s3://hh-lake/raw/it_vacancies_2024.csv', str(path))
    con.execute(sql)
    con.execute((ROOT / 'sql/combinations.sql').read_text())
    assert con.execute('SELECT count(*) FROM selected').fetchone()[0] == 3
    assert con.execute('SELECT count(salary), median(salary) FROM selected').fetchone() == (2, 200.0)
    records = [dict(zip(fields, row)) for row in rows]
    counts = [Counter(), Counter(), Counter()]
    reduce_chunk(counts, map_chunk(records, True), True)
    for k in (1, 2, 3):
        actual = {tuple(stack): n for stack, n in con.execute('SELECT stack, n FROM frequencies WHERE k=?', [k]).fetchall()}
        assert actual == counts[k - 1]
    con.close()
