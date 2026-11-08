# Продолжение на локальном компьютере

Это текущее автономное задание для Codex. Основание — [поручение от 8 ноября](reports/RESUMPTION_SCOPE_2026_11_08.md). Цель остаётся прежней: проверяемое исследовательское портфолио для Anthropic Residency и научная рукопись. Перенос на локальную машину устраняет облачную блокировку RouterAI; **новых модельных экспериментов в облаке не было**.

## Получить рабочую копию

Для Windows/PowerShell, из каталога проектов:

```powershell
git clone --branch codex/resume-local-autonomous-research https://github.com/AdamCage/reasoning-universalis.git reasoning-universalis-local
cd reasoning-universalis-local
```

Используй новый каталог, если прежний checkout содержит незакоммиченные изменения. Полная история нужна для проверки исторического G1; `--depth 1` не применять. Предварительно сливать PR не требуется: ветка уже содержит пакет. Если этот каталог уже существует, сначала проверить `git status`; не сбрасывать и не перезаписывать чужую работу.

Открой **локальную папку** в Codex Desktop как проект с локальным исполнением. Облачный чат и его запущенный процесс не переезжают через Git; контекст продолжения записан в этом файле, протоколе и отчётах. Локальные результаты и будущий ledger будут созданы заново на основе опубликованного исторического ledger.

Ключ берётся из переменной процесса `ROUTERAI_API_KEY` или локального gitignored `.env` через `--env-file .env`. Ключ не присылать в чат и не записывать в команды, коммиты или отчёты. Если есть прежний рабочий `.env`, перенеси его **локально** через файловую систему. Если его нет, создай `.env` на компьютере владельца; необходимые значения:

```dotenv
ROUTERAI_API_KEY=YOUR_LOCAL_KEY
ROUTERAI_BASE_URL=https://routerai.ru/api/v1
RU_MAX_SPEND_RUB=900
```

`YOUR_LOCAL_KEY` — заполнитель; реальное значение вводится только в локальный файл/настройки. Наличие ключа проверять как Boolean, не печатать его. Компьютер и локальный Codex должны оставаться включёнными во время исполнения.

## Сообщение локальному Codex

После открытия папки отправь:

> Прочитай AGENTS.md и LOCAL_RESUME.md. Продолжи исследование полностью автономно. Сохрани исходный срок: 8 ноября 2026, 19:19 по Москве; перенос машины не начинает отсчёт заново. Выполни настройку, проверку доступа, допустимые эксперименты, анализ с отрицательными контролями и подготовку воспроизводимых артефактов и рукописи. Общий потолок RouterAI — 900 RUB с сохранением опубликованных 246.7988793802352 RUB charged-or-reserved. Используй локальный .env, не раскрывай ключ. Не останавливайся для согласования обычных обратимых шагов и уже разрешённых вызовов. Сохрани исходные H0–H7 и честный статус E0; не подавай статью или заявку. При отрицательном результате заверши анализ и текст с соответствующим выводом.

Далее агент действует по следующим разделам; пользователю не требуется вручную запускать каждую команду.

## Первые действия агента

1. Зафиксировать реальное время локального начала, оставшееся время до **2026-11-08 16:19:12 UTC / 19:19 по Москве** и план сдачи в `reports/LOCAL_SESSION.md`. Перенос не сбрасывает исходные восемь часов. Если папку открыли уже после этого срока, явно зафиксировать просрочку и сохранить результаты; продолжение после исходного срока требует нового явно обозначенного локального плана, а не изменения старого deadline. Не считать облачный пакет выполненным исследованием.
2. Проверить `git status`, текущую ветку, наличие `.env` и его исключение из Git. Не выводить секретные значения. Прочитать текущий протокол и три аудита: [генераторы](reports/GENERATOR_AUDIT_2026_11_08.md), [EpistemeOS](reports/EPISTEMEOS_RESUMPTION_AUDIT.md), [Semantic Afterlife](reports/SEMANTIC_AFTERLIFE_TRANSFER.md). Литературные ограничения — [обновление](literature/resumption_2026_11_08/NOVELTY_UPDATE.md).
3. Создать локальное Python 3.12 окружение и установить фиксированные зависимости. При наличии `uv`:

```powershell
uv venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements-resumption.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Без `uv`, при установленном Python 3.12:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-resumption.txt
```

В Bash использовать `.venv/bin/python` вместо `.venv\Scripts\python.exe`. Активация PowerShell-скрипта не требуется. Windows в облачной сессии не исполнялся; если выявится ошибка платформы, исправить её и перепроверить.

4. Проверить корпус и выполнить бесплатную локальную проверку. Не удалять state для обхода ошибки или обновления deadline:

```powershell
.venv\Scripts\python.exe -m resumption.tasks --check
.venv\Scripts\python.exe -m resumption.runner --dry-run artifacts/resumption-2026-11-08/tasks.json --protocol design/RESUMPTION_PROTOCOL_2026_11_08.json --env-file .env
.venv\Scripts\python.exe -m resumption.runner --catalog --env-file .env
```

`--dry-run` не обращается к API. `--catalog` читает метаданные и котировки, не генерирует модельные ответы. Проверить фактическую доступность, единицы цен, лицензии и ответные идентификаторы; API-совместимость не вытекает из offline-тестов. Автоматической замены кандидатов нет. Если требуются иные модели или изменение дизайна, агент может подготовить отдельный явно обозначенный development-протокол **до новых данных**, сохраняя причину и исходный протокол; не выдавать его за утверждённый G2 или confirmatory study.

## Реальный пилот

Код: [`resumption/runner.py`](resumption/runner.py). Реестр: [96 задач / 48 парных roots](artifacts/resumption-2026-11-08/tasks.json), включая отдельные 4 admission-задачи. Новый корпус проверяется независимым решателем, содержит фиксированные train/validation/test splits и исключает точные нормализованные повторы. Имена семейств не доказывают независимость генераторных распределений.

Сначала получить prospective cost plan командой `--plan` (см. `python -m resumption.runner --help`). Сопоставить оценку с сохранённым бюджетом; не обещать все 576 запросов, пока консервативные резервы не помещаются. Нельзя начинать массовый старый пилот 1800 трасс. Сохранять 100 RUB общего лимита для эмбеддингов: генерации и admission по умолчанию имеют collection ceiling 800 RUB, включающий старые расходы. Если нужен меньший сбалансированный пилот, зафиксировать уменьшенный корпус и план **до первых платных ответов** в новом state, с тем же историческим и всеми новыми уже возникшими обязательствами. Не менять bound corpus и не обнулять ledger.

Основные команды (из корня; после настройки `.venv`):

```powershell
.venv\Scripts\python.exe -m resumption.runner --plan artifacts/resumption-2026-11-08/tasks.json --protocol design/RESUMPTION_PROTOCOL_2026_11_08.json --env-file .env
.venv\Scripts\python.exe -m resumption.runner --admit artifacts/resumption-2026-11-08/tasks.json --protocol design/RESUMPTION_PROTOCOL_2026_11_08.json --env-file .env
.venv\Scripts\python.exe -m resumption.runner --collect artifacts/resumption-2026-11-08/tasks.json --protocol design/RESUMPTION_PROTOCOL_2026_11_08.json --env-file .env
.venv\Scripts\python.exe -m resumption.runner --budget
```

До первого запроса сохранить точную котировку и план. Точный ответный model/provider и видимая законченная reasoning trace обязательны для operational admission. Это **не доказательство полноты/верности трассы** и не E0. Summary, encrypted, truncated, answer-only, provider drift, ошибки API и неизвестные списания сохраняются. Запросы с неизвестным результатом автоматически не повторяются. Если модель не допущена, её отсутствие становится результатом проверки; не подставлять другую незаметно.

State по умолчанию: `.research/resumption-2026-11-08/`. Он содержит ledger, immutable protocol/corpus snapshots, admission records, request/raw-response journal и итоговый `results.json`. Это локальные gitignored данные. **После появления новых вызовов этот state и ledger обязательны для любого дальнейшего переноса**; исходный облачный пакет переносит только старые опубликованные обязательства. Не создавай параллельные рабочие каталоги с независимыми бюджетами. Перед новым state после платных запросов реализуй и проверь явный перенос объединённого ledger; текущий runner не выполняет такое объединение автоматически.

Планируй работу по оставшемуся времени: короткий локальный preflight, затем сбор, эмбеддинги/анализ и финальный текст. Протокол прекращает новые оплачиваемые запросы к **15:19:12 UTC / 18:19 по Москве**, оставляя час до исходного срока сдачи. Уже сохранённые ответы после deadline восстанавливаются и анализируются офлайн. При частичном сборе покажи покрытие каждого root/model/sample и анализируй заранее определённые завершённые блоки, не выбирая их по исходам.

## Эмбеддинги и анализ

Сначала lexical smoke на реальных `results.json`; admission нельзя выдавать за основную выборку. Схема, метод и ограничения: [`resumption/ANALYSIS.md`](resumption/ANALYSIS.md).

```powershell
.venv\Scripts\python.exe -m resumption.analysis .research/resumption-2026-11-08/results.json --output artifacts/resumption-2026-11-08/analysis-lexical.json
.venv\Scripts\python.exe -m resumption.runner --embed .research/resumption-2026-11-08/results.json --embedding-model baai/bge-m3 --protocol design/RESUMPTION_PROTOCOL_2026_11_08.json --env-file .env
.venv\Scripts\python.exe -m resumption.runner --embed .research/resumption-2026-11-08/results.json --embedding-model qwen/qwen3-embedding-8b --protocol design/RESUMPTION_PROTOCOL_2026_11_08.json --env-file .env
.venv\Scripts\python.exe -m resumption.analysis .research/resumption-2026-11-08/baai_bge-m3-embedded.json --embedding-model baai/bge-m3 --output artifacts/resumption-2026-11-08/analysis-bge.json
.venv\Scripts\python.exe -m resumption.analysis .research/resumption-2026-11-08/qwen_qwen3-embedding-8b-embedded.json --embedding-model qwen/qwen3-embedding-8b --output artifacts/resumption-2026-11-08/analysis-qwen.json
```

Основной отчётный контраст — static-minus-dynamic **logloss при 256 наблюдаемых whitespace-словах / BGE-M3**, отдельно по отложенным моделям. Остальные бюджеты, Brier, AUROC, второй эмбеддер и pooled summaries — дополнительные результаты. Источник словаря/масштабирования/выбора C — только source train/validation. Фиксированные префиксы не используют долю будущей длины; короткие и неразмечаемые попытки остаются в coverage. Bootstrap переносит исходные roots целиком и сохраняет кратность повторных выборок.

Прямо сравни observed dynamics с переобученными order controls, а не значимость одного интервала с незначимостью другого. Все интервалы exploratory, pointwise и условны на обученных предикторах. Не объявляй H0 доказанной из-за незначимости и не объявляй H7 целиком подтверждённой из-за предсказательного улучшения. Нужны знаменатели и class balance. Для сравнения эмбеддеров выдели общие trace/prefix IDs и явно покажи исключения; сравнение разных выборок может отражать покрытие. Если данных для контраста нет, результат — «не оценён», а не ноль.

## Упрощённый EpistemeOS

Использовать закреплённый новый kernel отдельно от исторической копии:

```powershell
git clone https://github.com/AdamCage/EpistemeOS.git .research/deps/EpistemeOS
git -C .research/deps/EpistemeOS checkout --detach 7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3
.venv\Scripts\python.exe -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --historical-smoke .research/episteme-historical-local
```

Уже существующий checkout не перезаписывать. Перед финалом построить evidence-index с hashes protocol/tasks/results/source и анализов; прогнать adapter `--evidence-index ... --output ...` по [описанию](reports/EPISTEMEOS_RESUMPTION_AUDIT.md). `criteria_met` — механическое выполнение, `scientific_validity=not_assessed`, review не назначается автоматически. Исходный `EpistemeOS/`, старые manifests и спецификацию не переписывать ради прохождения checks.

## Что сдать по окончании

- `reports/LOCAL_RESEARCH_RESULT_RU.md`: вопрос, фактическая выборка/покрытие/расходы, главный результат с интервалами, ограничения, что сделано и что не оценено.
- Английская рукопись и PDF с реальными результатами, figures/tables, related work и claims-to-evidence map. Если научный пилот не состоялся, ясно обозначить методический/инфраструктурный отчёт; не маскировать отсутствие эксперимента под готовую эмпирическую статью.
- Краткое портфолио evidence sheet по [проверенным требованиям Residency](literature/resumption_2026_11_08/PORTFOLIO_CRITERIA.md), включая фактический human/AI вклад. Не выдумывать лидерство/опыт владельца и не писать за него первый личный ответ в заявку.
- Открытый reproducibility bundle: код, версии/лицензии, протоколы, tasks, all-attempt registry, очищенные raw outputs, ledger, predictions, controls, manifest hashes, команды бесплатного повторного анализа. Проверить отсутствие секретов и персональных настроек перед добавлением в Git.
- Проверки по объёму реальных изменений; commit/PR с точными выводами. Публикация статьи/подача заявки не выполняются. Отрицательный результат довести до проверяемого текста, а не останавливаться на плане.

Если возникает настоящий внешний blocker (например, неработающий локальный ключ или запрет API), сохранить диагностику без секретов и завершить независимые офлайн-работы. Не превращать каждое обычное решение в запрос согласования. При этом отсутствующий доступ, человеческую валидацию или научное approval не считать полученными по истечении времени.
