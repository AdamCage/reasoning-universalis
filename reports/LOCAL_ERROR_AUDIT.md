# Независимая программная проверка ошибок локального пилота

Это диагностика после сбора: проверены все записи с `correct=false` и завершённые записи с `verdict=unparseable`. Проверка использует отдельный код без импорта основного `verify_answer`. Исходные labels, статистические метрики и состав первичной выборки сохранены. Проверка ИИ не является независимым человеческим G3; E0 не пройден.

Проверено: 4 неверных и 2 неразбираемых ответов. Все проверенные неверные ответы нарушают условие задачи; для этих случаев ошибка scorer не обнаружена.

## Воспроизведение

```powershell
.venv/Scripts/python.exe -X utf8 scripts/audit_local_errors.py --results .research/resumption-2026-11-08-live/results.json --tasks .research/resumption-2026-11-08-live/corpus.json --output artifacts/resumption-2026-11-08/local/error-audit.json --report reports/LOCAL_ERROR_AUDIT.md
```

Все вычисления выполняются локально и без API. JSON содержит точные task data и проверяемые сертификаты; hashes входов связывают отчёт с сохранённым состоянием.

## Случай 1

Модель: `openai/gpt-oss-20b`; split: `train`; sample: `1`.

Trace: `160223954cf4284f6cc8b5870e378d7416e822470736eac9eae45e8d81a3f71c`.

Task: `resumption-generators-v1:primary:math:fixed_residues:medium:0:0`.

Root: `resumption-generators-v1:primary:math:fixed_residues:medium:0`.

Записанный verdict: `unparseable`; исходный `correct=null`.

Последняя непустая строка ответа:

```text
**ANSWER: 44**
```

Markdown emphasis мешает точному формату `ANSWER: <integer>`. Это завершённая генерация с нарушением формата ответа.

Только для диагностики удаление `**` даёт число `44`. Перебор диапазона `0 <= x < 77` даёт решения `[44]`; остатки: `[2, 0]` по модулям `[7, 11]`.

Числовое содержание удовлетворяет арифметике.

Первичный label остаётся `null`, и запись не добавляется задним числом к gradeable выборке.

## Случай 2

Модель: `deepseek/deepseek-v4.1-flash`; split: `train`; sample: `0`.

Trace: `73e16ae88ba8430b91992cbfefa0f5c3feb7ac7003de09e4b918e1f337131662`.

Task: `resumption-generators-v1:primary:logic:two_cnf:hard:1:1`.

Root: `resumption-generators-v1:primary:logic:two_cnf:hard:1`.

Записанный verdict: `incorrect`; исходный `correct=false`.

Последняя непустая строка ответа:

```text
ANSWER: SAT
```

Перебраны все `256` присваивания 8 переменным; удовлетворяющих присваиваний `0`. Ответ модели `SAT` противоречит этому результату.

Дополнительно каждый шаг следующего resolution-сертификата проверен символьным удалением противоположных литералов. `C` с исходным номером обозначает дизъюнкт из сохранённого CNF; пустой дизъюнкт завершает доказательство UNSAT.

```text
C1 = [1, 6] (исходный дизъюнкт 1)
C4 = [2, 5] (исходный дизъюнкт 4)
C5 = [-5, 2] (исходный дизъюнкт 5)
C7 = [-2, -1] (исходный дизъюнкт 7)
C8 = [-5, -1] (исходный дизъюнкт 8)
C10 = [-6, 4] (исходный дизъюнкт 10)
C13 = [-4, 5] (исходный дизъюнкт 13)
C14 = [-5, 1] (исходный дизъюнкт 14)
C15 = resolve(C4, C5; x5) = [2]
C16 = resolve(C7, C15; x2) = [-1]
C17 = resolve(C1, C16; x1) = [6]
C19 = resolve(C8, C14; x1) = [-5]
C21 = resolve(C10, C17; x6) = [4]
C22 = resolve(C13, C19; x5) = [-4]
C23 = resolve(C21, C22; x4) = []
```

## Случай 3

Модель: `openai/gpt-oss-20b`; split: `test`; sample: `1`.

Trace: `8bd12663846a5a187e138f1ce06a13d20815f21d7637f4041071c9bad9e6cdb3`.

Task: `resumption-generators-v1:primary:planning:rectangular_grid:hard:0:0`.

Root: `resumption-generators-v1:primary:planning:rectangular_grid:hard:0`.

Записанный verdict: `incorrect`; исходный `correct=false`.

Последняя непустая строка ответа:

```text
ANSWER: ["N","N","N","E","E","E","E","E","N"]
```

Прямая симуляция координат обнаруживает первое нарушение:

```json
{"constraint": "coordinate outside grid", "from": [0, 0], "height": 5, "move": "N", "step": 1, "to": [0, -1], "width": 6}
```

Независимый поиск в ширину нашёл допустимый путь из 9 ходов при лимите 13:

```json
["S", "S", "S", "E", "E", "E", "E", "E", "S"]
```

Этот путь повторно проверен отдельной симуляцией. Существование допустимого решения не делает предложенный моделью путь корректным.

## Случай 4

Модель: `openai/gpt-oss-20b`; split: `test`; sample: `0`.

Trace: `a7d29198f341e06dcceba903fc16feab8bd2671937c32807f8ca2321dc7e03e6`.

Task: `resumption-generators-v1:primary:math:fixed_residues:easy:0:0`.

Root: `resumption-generators-v1:primary:math:fixed_residues:easy:0`.

Записанный verdict: `unparseable`; исходный `correct=null`.

Последняя непустая строка ответа:

```text
**ANSWER:** 32
```

Markdown emphasis мешает точному формату `ANSWER: <integer>`. Это завершённая генерация с нарушением формата ответа.

Только для диагностики удаление `**` даёт число `32`. Перебор диапазона `0 <= x < 35` даёт решения `[32]`; остатки: `[2, 4]` по модулям `[5, 7]`.

Числовое содержание удовлетворяет арифметике.

Первичный label остаётся `null`, и запись не добавляется задним числом к gradeable выборке.

## Случай 5

Модель: `openai/gpt-oss-20b`; split: `train`; sample: `1`.

Trace: `f1544d9d82faecfc8df83ad2e25d683259cbde0d2876694f9efd95e5012994bb`.

Task: `resumption-generators-v1:primary:planning:square_grid:hard:1:1`.

Root: `resumption-generators-v1:primary:planning:square_grid:hard:1`.

Записанный verdict: `incorrect`; исходный `correct=false`.

Последняя непустая строка ответа:

```text
ANSWER: ["E","E","E","E","E","N","N","N","W","N","N","E"]
```

Прямая симуляция координат обнаруживает первое нарушение:

```json
{"constraint": "coordinate outside grid", "from": [5, 0], "height": 6, "move": "N", "step": 6, "to": [5, -1], "width": 6}
```

Независимый поиск в ширину нашёл допустимый путь из 10 ходов при лимите 14:

```json
["E", "S", "S", "E", "S", "S", "E", "E", "S", "E"]
```

Этот путь повторно проверен отдельной симуляцией. Существование допустимого решения не делает предложенный моделью путь корректным.

## Случай 6

Модель: `openai/gpt-oss-20b`; split: `train`; sample: `1`.

Trace: `fe32603f9781c65e405acdf262d23d92c7a9b9b4fb2b541fcb6f0b276226160c`.

Task: `resumption-generators-v1:primary:planning:square_grid:medium:1:1`.

Root: `resumption-generators-v1:primary:planning:square_grid:medium:1`.

Записанный verdict: `incorrect`; исходный `correct=false`.

Последняя непустая строка ответа:

```text
ANSWER: ["E","E","S","S","S","N","E","E"]
```

Прямая симуляция координат обнаруживает первое нарушение:

```json
{"constraint": "obstacle collision", "from": [3, 2], "move": "E", "step": 8, "to": [4, 2]}
```

Независимый поиск в ширину нашёл допустимый путь из 8 ходов при лимите 10:

```json
["E", "E", "S", "S", "S", "S", "E", "E"]
```

Этот путь повторно проверен отдельной симуляцией. Существование допустимого решения не делает предложенный моделью путь корректным.

## Границы вывода

Это проверка конкретных ответов и конкретных ограничений задач. Она не устанавливает внутреннюю причину ошибки, верность CoT, overthinking или истинность H1–H7. Проверка не меняет frozen scorer и не исправляет формат ответов для первичного анализа. Наличие решений задач отделено от фактической корректности ответа каждой генерации.
