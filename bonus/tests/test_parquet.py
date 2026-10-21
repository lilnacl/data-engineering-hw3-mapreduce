import csv

import duckdb

from src.common import ROOT
from bonus.parquet_experiment import variant_sql


def test_parquet_keeps_rows_and_gives_same_frequencies(tmp_path):
    fields = ['vacancy_id', 'name', 'role', 'key_skills', 'area', 'salary_from',
              'salary_to', 'currency', 'gross', 'description']
    rows = [
        ['1', 'Go developer', 'Программист, разработчик', 'Go; SQL; SQL', 'Москва',
         '100', '300', 'RUR', 'false', 'первая строка\nвторая строка'],
        ['2', 'Backend', 'Программист, разработчик', 'Golang; Docker', 'Москва',
         '', '200', 'RUR', 'false', 'текст, с запятой'],
        ['3', 'Go DevOps', 'DevOps-инженер', 'Go', 'Москва',
         '900', '', 'RUR', 'false', ''],
    ]
    csv_path = tmp_path / 'data.csv'
    parquet_path = tmp_path / 'data.parquet'
    with csv_path.open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        writer.writerows(rows)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE raw AS SELECT * FROM read_csv('{csv_path}', header=true, all_varchar=true)")
    con.execute(f"COPY raw TO '{parquet_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    assert con.execute(f"SELECT count(*) FROM (SELECT * FROM raw EXCEPT ALL SELECT * FROM read_parquet('{parquet_path}'))").fetchone()[0] == 0
    results = []
    for kind, path in [('csv', csv_path), ('parquet', parquet_path)]:
        con.execute(variant_sql(kind, str(path)))
        con.execute((ROOT / 'sql/combinations.sql').read_text())
        assert con.execute('SELECT count(*), median(salary) FROM selected').fetchone() == (2, 200.0)
        results.append(con.execute('SELECT stack, n FROM frequencies ORDER BY stack').fetchall())
        con.execute('DROP TABLE selected; DROP TABLE skills; DROP TABLE stacks; DROP TABLE frequencies')
    assert results[0] == results[1]
    assert dict((tuple(stack), n) for stack, n in results[0])[('go',)] == 2
    con.close()
