# EpistemeOS: аудит обновления и интеграция возобновлённого исследования

Дата проверки: 8 ноября 2026. Проверены GitHub metadata/README/commits через подключённый GitHub и исходники отдельного checkout. Версия upstream закреплена: [`7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3`](https://github.com/AdamCage/EpistemeOS/commit/7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3), 4 ноября 2026. Машинный реестр: [epistemeos_resumption_source_audit.json](epistemeos_resumption_source_audit.json).

## Что изменилось

Встроенный `EpistemeOS/` имеет Git tree `a03380f3cb5e9a842c44c655a0340fe74f5c01d7`, совпадающий с upstream `5c4da6f3f37d27d2fb2ad40e04ffcac5bd87a63d`. Между этим состоянием и текущим upstream изменены 13 файлов: 1116 добавленных и 10 удалённых строк. Основное добавление — `src/episteme/stages.py` (626 строк), тесты и подключение stages в CLI/command API/graph. Старые scientific/review gates не удалены.

Согласно [ADR 0026](https://github.com/AdamCage/EpistemeOS/blob/7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3/docs/decisions/0026-stage-control.md), новый путь:

```text
уже замороженный pack protocol → stage.open → stage.run → stage.close
```

Оператор больше не обязан вручную проводить каждый slot, dispatch, analysis и назначение reviewer для завершения вычислительного stage. `stage.run` исполняет существующий frozen roster и делает `pack.analyse`. Затем stage закрывается по механическим критериям. `review=not_requested`, `scientific_validity=not_assessed`; метка `stage-unreviewed` не является рецензентом. `criteria_met` означает, что выполнен контракт stage, даже если научный `outcome=inconclusive`. Failed/unknown попытки сохраняются; unknown не получает автоматический повтор. Следующий протокол сам не возникает.

Это снимает прежний ручной контроль переходов внутри одного вычислительного этапа. Человеческая валидация измерителя, независимый научный review и пригодность рукописи к журналу этим обновлением не обеспечиваются.

## Принятое решение

Исходники и история встроенного `EpistemeOS/` сохранены. Новый [адаптер](../resumption/episteme_adapter.py) явно выбирает отдельный upstream checkout, проверяет закреплённый commit и отсутствие правок отслеживаемого runtime-кода, затем регистрирует внешний DomainPack в allowlist текущего процесса. Это не правка registry ядра. Другая уже импортированная версия ядра вызывает отказ с требованием нового Python-процесса.

Предусмотрены два пути:

1. Историческое smoke-воспроизведение шести реальных development traces через существующий `reasoning_universalis_v1`, теперь без назначения review.
2. Новый [`resumption_evidence_v1`](../resumption_evidence_v1/__init__.py): конечный реестр **явно перечисленных** protocol/tasks/results/source artifacts, их исходные bytes, hashes, JSON-readability, primary и same-data reanalysis. Отсутствие обязательной роли, отсутствующий файл, несоответствие index hash, пустой файл или повреждённый JSON вызывают отказ. Package не проверяет полноту исходного сбора и не проверяет правильность содержательных выводов.

У второго пути `pack.preregister` регистрирует только будущую офлайн-проверку уже наблюдённых bytes. Он не объявляет исходный эксперимент пререгистрированным задним числом. Оба пути всегда exploratory/inconclusive; E0 остаётся `not_passed`.

## Проверка

В Linux/Python 3.12 выполнены:

| Проверка | Наблюдение |
|---|---|
| Upstream `test_stages.py` | 8 тестов прошли, включая failed/unknown без повтора, budget stop, отсутствие review, идемпотентное закрытие |
| Прежний `test_stage2_pack.py` с новым ядром | 9 тестов прошли: совместимость standalone pack, raw provenance, tamper rejection, scientific gates |
| Новые capture checks | 5 тестов прошли: missing artifacts/roles, corruption, malformed JSON, ложный scientific status, raw tampering, unsafe/duplicate paths |
| Исторический stage через новый адаптер | 12/12 offline primary/reanalysis attempts; `criteria_met`, `inconclusive`, `exploratory`, `not_assessed`, `not_requested`; повтор не изменил историю и не создал попытки |
| Новый artifact pack, synthetic integration fixture | 5 artifacts, 10/10 offline attempts; закрытие без review, outcome `inconclusive`; повтор closed stage не изменил историю |

Исторический запуск — новая механическая проверка прежних наблюдений. Новых генераций моделей, E0, независимой репликации или scientific approval нет. Фиксированные результаты и инструкция воспроизведения не означают проверенную кроссплатформенность: Windows в этой сессии не исполнялся.

Сохранён [архив исторического stage](../evidence/episteme-stage-replay-2026-11-08.zip): переносимый kernel backup, hash inventory, `stage-result.json`, `events.jsonl`. SHA-256 ZIP и каждого файла указаны в машинном аудите и внутреннем manifest соответственно. Архив проверен и восстановлен в новый Store; graph snapshot hash совпал с исходным. Архив содержит наблюдённое механическое выполнение, а не новые научные данные; новая generic integration проверялась на явно synthetic fixture и научным результатом не считается.

## Локальное воспроизведение

Требуются Python 3.11+, Git и `uv` на PATH. Команды одинаково используют относительные пути в Bash и PowerShell; `python` должен указывать на нужный интерпретатор. Из корня исследования:

```bash
git clone https://github.com/AdamCage/EpistemeOS.git .research/deps/EpistemeOS
git -C .research/deps/EpistemeOS checkout --detach 7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3
python -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --historical-smoke .research/episteme-historical-replay
python -m unittest discover -s tests -p test_resumption_episteme.py -v
```

Checkout берётся по commit, а не по плавающему main. Его не нужно устанавливать поверх встроенной версии. Если каталог уже существует, сначала проверить его состояние; не клонировать поверх и не сбрасывать чужие изменения. Все output-каталоги новых запусков должны быть новыми. Код адаптера не содержит абсолютных путей облачной машины.

Минимальный index проверки текущего исследования — JSON с массивом `artifacts`. Каждый элемент содержит `path` относительно корня репозитория, `role` и `format` (`json` или `bytes`); опциональные `sha256` и `bytes` проверяются. Роли `protocol`, `tasks`, `results` должны встречаться ровно по одному разу, `source` — хотя бы один раз. Дополнительные роли разрешены и остаются в реестре. Например:

```json
{"schema_version":1,"artifacts":[
  {"path":"design/RESUMPTION_PROTOCOL_2026_11_08.json","role":"protocol","format":"json"},
  {"path":"artifacts/resumption-2026-11-08/tasks.json","role":"tasks","format":"json"},
  {"path":"artifacts/resumption-2026-11-08/results.json","role":"results","format":"json"},
  {"path":"resumption/runner.py","role":"source","format":"bytes"}
]}
```

```bash
python -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --evidence-index artifacts/resumption-2026-11-08/evidence-index.json --output .research/resumption-integrity
```

Output содержит `capture/`, SQLite/CAS `store/`, переносимый `backup/`, `events.jsonl` и `stage-result.json`. Реестр фиксирует конкретные bytes, не обещает неизменяемость внешнего API или полноту не перечисленных файлов. Продолжение уже открытого stage использует сохранённый ID:

```bash
python -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --resume-stage STAGE_ID --store .research/resumption-integrity/store --pack resumption_evidence_v1
```

`stage-result.json` и история Store определяют фактический результат: `blocked`/`stopped_budget` не являются выполнением. Unknown/failed не исправляются выдуманным success. OS-isolation отсутствует: процессы выполняются тем же пользователем; разные actor labels не доказывают независимость.
