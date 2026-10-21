import csv
import io
from collections import Counter

from src.mapreduce import map_chunk, reduce_chunk
from src.common import is_variant, normalize_skills


def row(name='Go developer', role='Программист, разработчик', skills='Go; SQL; SQL; Golang; Docker'):
    return {'name': name, 'role': role, 'key_skills': skills}


def test_variant_excludes_other_roles_and_substrings():
    assert is_variant(row())
    assert is_variant(row(name='Backend', skills='Golang'))
    assert not is_variant(row(role='DevOps-инженер'))
    assert not is_variant(row(name='Django developer', skills='Django; MongoDB'))
    assert is_variant(row(name='разработчик GO / backend', skills=''))


def test_unique_canonical_skills():
    assert normalize_skills(' Go; Golang ;SQL; sql; ;Docker') == ('docker', 'go', 'sql')


def test_combinations_count_once_and_combiner_is_equivalent():
    records = [row(), row(name='Backend', skills='Go; SQL'), row(role='Аналитик')]
    expected = [Counter({('go',): 2, ('sql',): 2, ('docker',): 1}),
                Counter({('go', 'sql'): 2, ('docker', 'go'): 1, ('docker', 'sql'): 1}),
                Counter({('docker', 'go', 'sql'): 1})]
    for combine in (False, True):
        counts = [Counter(), Counter(), Counter()]
        result = map_chunk(records, combine)
        reduce_chunk(counts, result, combine)
        assert counts == expected


def test_multiline_csv_survives_tiny_network_reads():
    from src.mapreduce import csv_chunks
    class TinyRead(io.BytesIO):
        def readinto(self, b):
            return super().readinto(memoryview(b)[:3])
    raw = 'name,role,key_skills,description\r\nGo developer,"Программист, разработчик",Go; SQL,"строка 1\nстрока 2"\r\n'
    chunks = list(csv_chunks(TinyRead(raw.encode()), 1))
    assert len(chunks) == 1
    assert chunks[0][0]['key_skills'] == 'Go; SQL'


def test_prefilter_preserves_source_row_count_and_selects_before_chunking():
    from src.mapreduce import csv_chunks
    data = 'name,role,key_skills\nBackend,"Программист, разработчик",Python\nGo dev,"Программист, разработчик",Go\n'
    raw = io.BytesIO(data.encode())
    chunks = list(csv_chunks(raw, 1, prefilter=True))
    assert len(chunks) == 1
    assert raw.csv_rows == 2
    assert chunks[0][0]['name'] == 'Go dev'
