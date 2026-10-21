# ДЗ3. MapReduce и DuckDB — вариант 7 (Go)

| Файл | Содержание |
|---|---|
| `src/infrastructure.py` | Запуск RustFS и загрузка CSV |
| `src/common.py` | Настройки S3, фильтр Go, подготовка навыков |
| `src/mapreduce.py` | MapReduce с чанками, комбайнером и повтором задачи |
| `src/duckdb_job.py` | Чтение S3 и выполнение SQL в DuckDB |
| `src/analysis.py` | Зарплатный и региональный анализ |
| `src/benchmark.py` | Замеры времени и памяти |
| `src/parquet_experiment.py` | Сравнение CSV и Parquet, преобразование и замеры |
| `src/verify.py` | Сверка частот двух реализаций |
| `src/store_results.py` | Сохранение результатов в S3 и проверка GET |
| `sql/variant.sql` | Отбор варианта в SQL |
| `sql/combinations.sql` | Частоты навыков, пар и троек |
| `tests/` | Проверки CSV/Parquet, фильтра, сочетаний, SQL и зарплатной базы |
| `results/mapreduce/` | Частоты MapReduce и показатели запуска |
| `results/duckdb/` | Частоты DuckDB и показатели запуска |
| `results/parquet/` | Итоги сравнения CSV и Parquet |
| `results/analysis/` | Таблицы зарплат и регионов в CSV и JSON |
| `evidence/` | Выводы запусков, замеры, контрольные суммы и сверки |
| `requirements.txt` | Зависимости |
| `ИнжДан_lab3_Вдовина А.Р.pdf` | Отчёт |
| `ИнжДан_lab3_доп_Вдовина А.Р.pdf` | Бонусное задание: CSV и Parquet |
