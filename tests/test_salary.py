import duckdb

from src.analysis import analyze
from src.common import ROOT


def test_salary_base_uses_most_frequent_subset(tmp_path):
    con = duckdb.connect()
    con.execute('CREATE TABLE selected(vacancy_id VARCHAR, area VARCHAR, skills VARCHAR[], salary DOUBLE, currency VARCHAR, gross VARCHAR)')
    rows = [(str(i), 'Москва', ['docker', 'go', 'sql'] if i < 10 else ['go', 'sql'] if i < 20 else ['sql'],
             300.0 if i < 10 else 100.0 if i < 20 else 50.0, 'RUR', 'false') for i in range(30)]
    con.executemany('INSERT INTO selected VALUES (?,?,?,?,?,?)', rows)
    con.execute('CREATE TABLE skills AS SELECT vacancy_id, unnest(skills) AS skill FROM selected')
    con.execute((ROOT / 'sql/combinations.sql').read_text())
    analyze(con, tmp_path)
    import json
    effects = {tuple(r['stack']): r for r in json.loads((tmp_path / 'salary_effects.json').read_text())}
    assert effects[('docker', 'go')]['base'] == ['go']
    assert effects[('docker', 'go', 'sql')]['base'] == ['go', 'sql']
    assert effects[('docker', 'go', 'sql')]['base_vacancies'] == 20
    assert effects[('docker', 'go', 'sql')]['base_median'] == 200.0
    assert effects[('docker', 'go', 'sql')]['delta_rub'] == 100.0
    con.close()
