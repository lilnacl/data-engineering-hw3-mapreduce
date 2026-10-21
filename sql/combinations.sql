CREATE TEMP TABLE stacks AS
SELECT vacancy_id, [skill] AS stack FROM skills
UNION ALL
SELECT a.vacancy_id, [a.skill, b.skill] AS stack
FROM skills a JOIN skills b ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
UNION ALL
SELECT a.vacancy_id, [a.skill, b.skill, c.skill] AS stack
FROM skills a
JOIN skills b ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
JOIN skills c ON a.vacancy_id = c.vacancy_id AND b.skill < c.skill;

CREATE TEMP TABLE frequencies AS
SELECT len(stack) AS k, stack, count(*)::BIGINT AS n
FROM stacks GROUP BY stack;
