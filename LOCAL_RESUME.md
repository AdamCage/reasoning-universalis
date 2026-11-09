# Продолжение на локальном компьютере

**Актуальный закрытый этап — машинная разметка, 9 ноября 2026 по Москве.** По поручению пользователя 200 сегментов S2 размечены конечным протоколом DeepSeek из пяти голосов: 1125 вызовов, 180 функциональных меток consensus, 15 `ambiguous_other`, 2 неразрешённых расхождения и 3 технически неполных панели. Общий ledger содержит 2109 строк и `2038.3174633704220 RUB charged-or-reserved` из 3300 RUB. Этап закрыт: не повторять collect-команды ниже, не сбрасывать `machine-development/condition-v1.json`, не создавать новый ledger. [Результат](reports/MACHINE_DEVELOPMENT_RESULT.md), [английская записка](manuscript/MACHINE_DEVELOPMENT_NOTE.md), [технический аудит](reports/MACHINE_VOTE_FAILURE_AUDIT.md). Пакет для людей отложен; E0 не пройден, генерации v3 и будущий test не запускались.

Проверенный бесплатный перенос без ключа и `.env` (reference CPython3.12.11 для точных численных bytes, `requirements-resumption.txt`, новый output-каталог):

```powershell
python -X utf8 scripts/reproduce_machine_development.py --manifest evidence/machine-annotation-development-2026-11-08/manifest.json --output .research/new-machine-offline-replay
```

Пакет восстанавливает точные raw source bytes и закрытые observations, включая прежнийR1; результаты и summary воспроизведены byte-exact при0network attempts. Это replay сохранённых ответов, не новый запрос модели или независимая научная валидация. Старые paragraphs/команды ниже сохраняют хронологию и не являются повторным разрешением сбора.

**Текущее offline-продолжение:** [план после v2](design/POST_V2_NEXT_STAGE_2026_11_08.md), [selection-анализ](reports/POST_V2_SELECTION_ANALYSIS.md), [кандидат v3](design/PILOT_V3_CANDIDATE_PROTOCOL_2026_11_08.json) и [human development handoff](design/E0_HUMAN_DEVELOPMENT_HANDOFF_2026_11_08.md). Новый сбор отключён; deadline и paid collector отсутствуют. 24-root human-пакет готовит процедуру, но не заменяет независимую E0-валидацию с минимум 40 roots. Все человеческие ответы/участники пока пусты. Текущий ledger и 823.5589067445220 RUB обязательств не изменены.

Позднейшее уточнение пользователя — «полностью на ИИ переносим пока что»: human handoff отложен. Текущая подготовка переключена на отдельную конечную машинную разметку DeepSeek; это не активирует v3 генерации, не создаёт human gold и не закрывает E0. Перед её paid-исполнением нужны отдельные зафиксированные protocol/source/input/cost receipts; старые paid-команды ниже не повторять.

Пользователь принял общий лимит **3300 RUB** и сообщил о пополнении после котировки полного 200-segment machine-плана. Текущий отдельный [annotation protocol](design/MACHINE_DEVELOPMENT_PROTOCOL_2026_11_08.json) готовит максимум 2100 calls (1000 round1 + до1000 conditional round2 +100 audit), дополнительные обязательства ≤2400 RUB и absolute stage ceiling 3223.5589067445220 RUB, сохраняя общий ledger. Paid cutoff нового условия — 8 ноября 23:00 UTC / 9 ноября 02:00 по Москве. Пока protocol status draft/source freeze pending, запуск запрещён. Цифры 3000 ниже относятся к закрытым старым стадиям; они не означают новый state или списание исторических резервов.

```powershell
python -X utf8 scripts/build_post_v2_design.py --check
python -X utf8 scripts/import_e0_human.py --check-package --package artifacts/e0-human-development-2026-11-08
```

**Закрытый статус v2/R1, 8 ноября 2026.** Платные вызовы завершены в 14:39:20 UTC / 17:39:20 по Москве. A содержит 98 реальных вызовов и 94 неотправленные ячейки; R1 добавил 96 GPT/AkashML вызовов и переиспользовал все 96 DeepSeek-наблюдений A. Общий ledger теперь содержит 984 строки и 823.5589067445220 RUB charged-or-reserved. Платные команды ниже не повторять; единственное R1 уже использовано, новый namespace или машина не обнуляют обязательства.

Гейт следующего исследования не пройден: общий output cap и окончательный N не выбраны, будущий test не создан, приватный holdout seed не раскрыт. E0 и человеческое scientific review остаются открытыми. Итоги: [PILOT_V2_RECOVERY_RESULT.md](reports/PILOT_V2_RECOVERY_RESULT.md), [английское дополнение](manuscript/PILOT_V2_CALIBRATION_NOTE.md).

Бесплатный переносимый replay, включая исходный A и R1, без ключа и `.env`:

```powershell
python -X utf8 scripts/reproduce_pilot_v2_recovery.py --manifest evidence/pilot-v2-recovery-2026-11-08/manifest.json --output .research/new-v2-offline-replay
```

Установи `requirements-resumption.txt`; выходной каталог должен быть новым. Исходные CRLF-байты унаследованных source snapshots сохраняются. Сильный historical v1 live-comparison verifier следует запускать с восстановленным v1 state, поскольку текущий общий ledger законно дополнен v2; обычный v1 portable replay остаётся самодостаточным.

Ограничение исходного collector на Windows и последующий I/O adapter описаны в [PILOT_V2_WINDOWS_IO_COMPATIBILITY.md](reports/PILOT_V2_WINDOWS_IO_COMPATIBILITY.md). Этот adapter не применялся к измерениям A/R1 и не разрешён их протоколами для платного запуска; будущая версия должна включить его hash в новый protocol/source inventory. Чтение ledger в параллельном процессе также должно соблюдать общий budget lock.

Ниже сохранена хронология запуска уже закрытых этапов.

**Новое продолжение — pilot v2.** Пользователь после завершения v1 поручил начать следующий development-пилот. Сначала читать [PILOT_V2_SESSION.md](reports/PILOT_V2_SESSION.md) и `design/PILOT_V2_PROTOCOL_2026_11_08.json`. Максимум 192 новых вызова по фиксированному факторному плану, только после source/corpus/protocol freeze и offline-проверок. Все расходы продолжают единственный `.research/resumption-2026-11-08-live/ledger.json`; v1-данные и результаты не перезаписываются. Новые code/artifacts находятся в `pilot_v2/` и `artifacts/pilot-v2-2026-11-08/`. Ниже — закрытый v1 и его история.

**Состояние после выполнения, 8 ноября 2026.** Платный сбор закрыт: 384 основные попытки, два полных набора по 5778 embedding chunks и пять завершённых анализов. Не запускать приведённые ниже исторические paid-команды повторно. Общий ledger содержит 790 записей, charged-or-reserved — 651.5180250837596 RUB из разрешённых 3000 RUB. Итог и научные ограничения — [LOCAL_RESEARCH_RESULT_RU.md](reports/LOCAL_RESEARCH_RESULT_RU.md); E0 и независимое человеческое review остаются открытыми.

Для бесплатного воспроизведения установи Python 3.12 и `requirements-resumption.txt`, затем выполни из корня репозитория:

```powershell
python -X utf8 scripts/reproduce_local.py --manifest evidence/local-pilot-2026-11-08/manifest.json --output .research/local-replay-check
```

Каталог результата должен быть новым. Ключ и `.env` для replay не нужны. Архив содержит raw evidence и закреплённый source snapshot; большие производные embedding JSON восстанавливаются с проверкой исходного SHA. Фактическая проверка этого архива записывается отдельно в [LOCAL_REPRODUCTION_CHECK.md](reports/LOCAL_REPRODUCTION_CHECK.md). Нижеследующие инструкции сохраняют историю переноса и не являются новым разрешением повторить сбор.

**Локальное обновление 8 ноября 2026.** Работа уже начата в `C:\projects\reasoning-universalis`; текущий pre-data commit — `fcd4426`. Пользователь в этом чате увеличил общий потолок до **3000 RUB**, включая исторические обязательства. Действующий локальный development-протокол — `design/LOCAL_PILOT_2026_11_08.json`, платный state — **`.research/resumption-2026-11-08-live`**. Запуски явно используют `--cap-total-rub 3000 --collection-cap-rub 2900 --state .research/resumption-2026-11-08-live --protocol design/LOCAL_PILOT_2026_11_08.json`; на Windows — `python -X utf8`. Старые 900 RUB и исходный протокол ниже сохранены как история передачи. До платного запуска 172/172 теста прошли. Не начинать новый state или повторный сбор: сначала читать текущие `admission-results.json`, `results.json`, ledger и `reports/LOCAL_SESSION.md` в активном state. Все `resumption/*.py` и три Stage 0 source-файла уже закреплены; правка останавливает dispatch. Два старых preflight state не содержат новых paid calls и сохранены отдельно. Deadline остаётся прежним.

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
