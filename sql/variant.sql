CREATE TEMP TABLE selected AS
WITH normalized AS (
    SELECT *, list_sort(list_distinct(list_transform(
        list_filter(string_split(coalesce(key_skills, ''), ';'), x -> trim(x) <> ''),
        x -> CASE WHEN lower(trim(x)) = 'golang' THEN 'go' ELSE lower(trim(x)) END
    ))) AS skills
    FROM read_csv('s3://hh-lake/raw/it_vacancies_2024.csv',
                  header=true, delim=',', all_varchar=true)
), filtered AS (
    SELECT * FROM normalized
    WHERE role = 'Программист, разработчик'
      AND (list_contains(skills, 'go') OR
           regexp_matches(lower(name), '(^|[^a-zа-яё0-9])(go|golang)([^a-zа-яё0-9]|$)'))
)
SELECT vacancy_id, name, area, skills, currency, gross,
       CASE WHEN currency = 'RUR' AND gross = 'false' THEN
         CASE WHEN try_cast(salary_from AS DOUBLE) > 0 AND try_cast(salary_to AS DOUBLE) > 0
              THEN (cast(salary_from AS DOUBLE) + cast(salary_to AS DOUBLE)) / 2
              WHEN try_cast(salary_from AS DOUBLE) > 0 THEN cast(salary_from AS DOUBLE)
              WHEN try_cast(salary_to AS DOUBLE) > 0 THEN cast(salary_to AS DOUBLE)
         END
       END AS salary
FROM filtered;

CREATE TEMP TABLE skills AS
SELECT vacancy_id, unnest(skills) AS skill FROM selected;
