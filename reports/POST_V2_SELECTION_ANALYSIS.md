# Post-v2: наблюдаемый отбор завершённых ответов и поддержки ошибок

Это новый post-data описательный анализ закрытых A/R1. Он не меняет выборку, метки, исходный failed gate или протокол. Причины ненаблюдённой правильности обрезанных ответов и причинный эффект cap не идентифицированы.

R1 содержит 192 строки на 48 задачах и 24 roots: 96 исходных DeepSeek наблюдений A и 96 новых GPT/AkashML. A анализируется отдельно; reuse не удваивает N. Всего A+R1 содержат 194 различных отправленных физических вызова.

## Последовательные потери support

| Model | Cap | План | Completed gradeable | Censored | Short at 256: raw / after censor | Eligible256 | Error traces / roots | Correct / mixed roots |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek-v4.1-flash | 2048 | 48 | 14 | 34 | 0 / 5 | 9 | 0 / 0 | 7 / 0 |
| deepseek-v4.1-flash | 8192 | 48 | 37 | 11 | 2 / 14 | 21 | 0 / 0 | 15 / 0 |
| gpt-oss-20b | 2048 | 48 | 11 | 37 | 0 / 0 | 11 | 0 / 0 | 7 / 0 |
| gpt-oss-20b | 8192 | 48 | 35 | 13 | 0 / 2 | 33 | 3 / 2 | 18 / 1 |

При 256 словах считаются лишь completed+gradeable ответы с достаточным текстом до первого буквального ANSWER:. Censored ответы имеют null primary correctness; их нельзя считать ошибками или угаданными успехами. Short raw означает исходный reasoning короче 256 слов; after censor — исходный reasoning достигал 256, но текст до первого ANSWER: не достигал. Это разные причины prefix-исключения. Feasibility reference certificate также не является модельной правильностью.

## Завершённость по domain

| Model | Cap | Domain | Completed / planned | Eligible256 | Completed errors |
|---|---:|---|---:|---:|---:|
| deepseek-v4.1-flash | 2048 | algorithms | 7 / 12 | 4 | 0 |
| deepseek-v4.1-flash | 2048 | logic | 0 / 12 | 0 | 0 |
| deepseek-v4.1-flash | 2048 | math | 4 / 12 | 2 | 0 |
| deepseek-v4.1-flash | 2048 | planning | 3 / 12 | 3 | 0 |
| deepseek-v4.1-flash | 8192 | algorithms | 12 / 12 | 5 | 0 |
| deepseek-v4.1-flash | 8192 | logic | 3 / 12 | 1 | 0 |
| deepseek-v4.1-flash | 8192 | math | 12 / 12 | 9 | 0 |
| deepseek-v4.1-flash | 8192 | planning | 10 / 12 | 6 | 0 |
| gpt-oss-20b | 2048 | algorithms | 4 / 12 | 4 | 0 |
| gpt-oss-20b | 2048 | logic | 0 / 12 | 0 | 0 |
| gpt-oss-20b | 2048 | math | 4 / 12 | 4 | 0 |
| gpt-oss-20b | 2048 | planning | 3 / 12 | 3 | 0 |
| gpt-oss-20b | 8192 | algorithms | 12 / 12 | 12 | 0 |
| gpt-oss-20b | 8192 | logic | 2 / 12 | 2 | 0 |
| gpt-oss-20b | 8192 | math | 12 / 12 | 12 | 3 |
| gpt-oss-20b | 8192 | planning | 9 / 12 | 7 | 1 |

## Парное сравнение caps

Сопоставлены те же task/model и requested seed. Два варианта остаются внутри одного root; ниже показаны счётчики пар и root blocks, без p-values, CI или предположения независимости 48 вариантов. Совпадение requested seed не доказывает его фактическое применение внешним backend.

| Model | Task pairs / root blocks | Стали completed | Потеряли completed | Roots net completion gain / loss / unchanged | Eligible256 gain / loss pairs |
|---|---:|---:|---:|---:|---:|
| deepseek-v4.1-flash | 48 / 24 | 23 | 0 | 14 / 0 / 10 | 18 / 6 |
| gpt-oss-20b | 48 / 24 | 24 | 0 | 15 / 0 / 9 | 23 / 1 |

Эти переходы описывают фиксированные полученные ответы. Они не позволяют утверждать, что более высокий cap причинно исправляет или ухудшает ответ либо сколько обрезанных ответов были бы неверны.

## Длины и исходные типы задач

Подсчёт — Unicode non-whitespace spans, отдельно в исходном reasoning, до первого ANSWER: и после него. API final-answer channel не добавляется в reasoning; suffix не возвращается в prefix. Отсутствие reasoning не заменяется нулевой длиной в сводках возвращённых текстов. Suffix оценивается только на traces с ANSWER marker; raw/prefix — на всех возвращённых reasoning. Эти медианы не требуется складывать. Квантили описательные, линейная интерполяция, не интервалы уверенности.

| Model | Cap | Returned reasoning | С ANSWER marker | Median raw / pre-ANSWER / suffix words |
|---|---:|---:|---:|---:|
| deepseek-v4.1-flash | 2048 | 48 | 29 | 772.5 / 576.0 / 285.0 |
| deepseek-v4.1-flash | 8192 | 48 | 42 | 1317.0 / 500.5 / 334.5 |
| gpt-oss-20b | 2048 | 48 | 10 | 829.0 / 829.0 / 20.0 |
| gpt-oss-20b | 8192 | 48 | 29 | 1396.0 / 1277.5 / 17.0 |

| Domain | Reference type | Tasks / roots |
|---|---|---:|
| algorithms | IMPOSSIBLE | 6 / 3 |
| algorithms | feasible | 6 / 3 |
| logic | SAT | 8 / 4 |
| logic | UNSAT | 4 / 2 |
| math | feasible | 12 / 6 |
| planning | IMPOSSIBLE | 4 / 2 |
| planning | feasible | 8 / 4 |

Все strata, отрицательные группы, roots, raw/prefix/suffix длины и парные переходы сохранены в [selection-analysis.json](../artifacts/post-v2-design-2026-11-08/selection-analysis.json). Распределения по reference type являются описанием данного набора, а не балансом модельных ошибок.

Завершённых ошибок: 4, на 3 roots; при 256 словах остаётся 3 traces на 2 roots. Ошибок короче 128 слов: 1. Эти счётчики относятся к наблюдённой completed подвыборке и не объясняют контрфактическую правильность censored.

Окончательный N и новый test не выбраны. Этот post-data анализ может мотивировать только новый development-дизайн, который потребуется зафиксировать отдельно до новых ответов. Он не оценивает power, не подбирает test до ошибок, не проверяет H0–H7, не создаёт человеческое E0 или scientific approval. Новых API вызовов не выполнено.
