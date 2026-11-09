# Локальная проверка EpistemeOS

8 ноября 2026. Windows, основной checkout `codex/resume-local-autonomous-research`.

Отдельный upstream checkout создан в `.research/deps/EpistemeOS` и закреплён на `7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3`. Отслеживаемые файлы этого checkout не изменены. Историческая копия `EpistemeOS/` и научная спецификация сохранены.

## Историческое воспроизведение

Команда выполнена системным Python 3.13.1; frozen offline jobs используют собственный закреплённый `uv` environment:

```powershell
python -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --historical-smoke .research/episteme-historical-local
```

| Поле результата | Наблюдение |
|---|---|
| Сохранённые исторические трассы | 6 |
| Primary и same-data reanalysis attempts | 12/12 completed; 0 failed; 0 unknown |
| Stage | `closed`, `criteria_met` |
| Научный outcome | `inconclusive`, `exploratory` |
| Review и scientific validity | `not_requested`, `not_assessed` |
| Повтор закрытого stage | та же история, без новых попыток |
| Новые генерации моделей и API-вызовы моделей | 0 |
| E0 | `not_passed` |

Полные локальные артефакты: `.research/episteme-historical-local/stage-result.json`, `events.jsonl`, `backup/` и `store/`. Это новые результаты механического пересчёта прежних наблюдений, без новой независимой выборки.

Контрольные суммы точных локальных байтов:

```text
stage-result.json SHA-256 048a1c348bf6dba1367e50fe73fe6acf9e9c67ed519b8dd644f33b2090b001db
events.jsonl SHA-256 546fb1d2889fa7acbec4a5f2c2053e4e00dd50cb964e52b9d132a1b8c202ad8b
kernel source inventory SHA-256 b40f7b5201b353c0e4971c6a72640185aba915ae26b6b77bdc578f16f3a81d1d
graph snapshot hash ea4d4b97f035989d16c340e836e6f69757b8cbe9a7f6af33aad855be495a05ef
```

`python -m unittest discover -s tests -p test_resumption_episteme.py -v` — 5/5 тестов проверки реестра прошли. Они проверяют отказы при отсутствии/подмене артефактов и ложном scientific status; сами тестовые fixtures научными данными не являются. Финальный evidence-index текущего пилота проверяется отдельно после сбора и анализа.

## Историческая приёмка Stage 2 на Windows

Старые рабочие копии `RESEARCH_SPECIFICATION.md` и `reports/MODEL_LICENSES.md` сохранили CRLF, тогда как их исторические text locks рассчитаны для UTF-8/LF. Изменение `.gitattributes` само по себе не переписывает уже существующие рабочие файлы.

`design/verify_stage2_acceptance.py` теперь выполняет только CRLF→LF для четырёх явно перечисленных текстовых locks. Payload implementations, receipt и evidence ZIP продолжают проверяться по точным байтам. Исходные manifests/receipts/hashes не изменены. Добавлены проверки допуска CRLF в text locks, отказа при содержательном изменении и сохранения byte-exact проверки receipt.

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_stage2_acceptance.py -v
.venv/Scripts/python.exe -X utf8 design/verify_stage2_acceptance.py
```

6/6 targeted tests прошли на Python 3.12.11. Verifier сохранил результат `accepted`, `E0=not_passed`, `G2=not_frozen`, `scientific_validity=not_assessed`, `paid_stage2_calls=0`. `git diff --check` для двух изменённых файлов прошёл.

Исторический `stage2/annotation.py` использует платформенную кодировку `read_text()`; русский UTF-8 template требует запуска старого runtime с `-X utf8` на этой Windows-машине. Этот файл входит в утверждённый payload и сохранён без правки; режим UTF-8 задаётся при запуске. Новое разрешение на узкий пилот не переписывает историческую приёмку.

## Проверка артефактов выполненного локального пилота

После завершения оплачиваемого сбора и пяти анализов выполнен отдельный stage с реальными артефактами текущего исследования. Он не использует исторический smoke как новые экспериментальные данные.

```powershell
.venv/Scripts/python.exe -X utf8 -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --evidence-index artifacts/resumption-2026-11-08/local/evidence-index.json --output .research/local-integrity-stage
```

[Evidence index](../artifacts/resumption-2026-11-08/local/evidence-index.json) фиксирует 26 непустых входных артефактов: протокол, задачи, результаты сбора, исходники, два операционных дополнения, пять анализов, ledger и связанные сведения о происхождении. Сам index становится 27-м захваченным артефактом. Пустой `resumption/__init__.py` учтён в неизменном source inventory и frozen closure переносимого пакета.

Первый запуск остановился на предварительной проверке списка, который включал этот пустой файл: контракт `resumption_evidence_v1` требует положительный размер отдельного артефакта. Output-каталог и события тогда ещё не были созданы. После явного уточнения index исходники, данные и история не переписывались; второй запуск создал новый stage.

Фактический [результат stage](../artifacts/resumption-2026-11-08/local/episteme-stage-result.json):

| Поле | Наблюдение |
|---|---|
| Stage ID | `stage_open-55cb017036834e90` |
| Pack | `resumption_evidence_v1` |
| Захваченные артефакты | 27, включая evidence index |
| Primary и same-data reanalysis | 54/54 completed; 0 failed; 0 unknown |
| Закрытие | `closed`, `criteria_met` |
| Outcome и режим | `inconclusive`, `exploratory` |
| Scientific validity | `not_assessed` |
| Review | `not_requested` |
| Повтор закрытого stage | та же история, без новых попыток |
| Вызовы моделей в этом stage | 0 |
| E0 | `not_passed` |

SHA-256 сохранённого `stage-result.json`: `a36e7ad223426c28c7f51206fb3352c41b7821408c57470406d81aeda9e0e09c`. SHA-256 evidence index: `a49a0e2d8e333f662501c896c8f51cf476e443151dcce1653863a5b4caf356b0`. `events.jsonl`: `712bc1b347cdb0101f78b2b0990976a9053feb59fd550eaef8fa42cd4a298c8c`.

Adapter создал проверяемый backup в `.research/local-integrity-stage/backup`. `episteme.recovery.restore` восстановил его в новый `.research/local-integrity-restored`, проверив bytes базы и CAS по manifest. В восстановленном Store сохранены все 340 событий и graph snapshot hash `8cbb413ffca128e7f534a2615c107b32ee9c0a7b9749054939fbb85a89c3ffd6`, совпадающий с исходным stage. Машинное подтверждение: [episteme-backup-check.json](../artifacts/resumption-2026-11-08/local/episteme-backup-check.json).

Переносимый [архив stage](../evidence/episteme-local-stage-2026-11-08.zip) содержит backup Store, `events.jsonl`, `stage-result.json`, подтверждение восстановления и внутренний manifest точных hashes. SHA-256 ZIP: `614c111420a49a76e205ebc55e389d75471518a7b2f9204ad520eed316634bfd`; размер 7 186 964 байта, 328 элементов. Все элементы проверены после сжатия по roster, размеру и SHA-256. Перед сжатием содержимое проверено в памяти на настроенный ключ и его JSON, URL и base64-представления; настройки, `.env`, зависимости и окружения исполнения в архив не включены. [Машинная проверка архива](../artifacts/resumption-2026-11-08/local/episteme-archive-check.json) сохраняет его hash и подтверждённый graph hash. Исходный локальный backup сохранён отдельно.

Эта проверка устанавливает целостность перечисленных байтов и выполнение конечного офлайн-реестра. Она не устанавливает полноту модельной трассы, истинность научного вывода, независимость рецензии или preregistration исходного эксперимента задним числом. Научная интерпретация остаётся exploratory; G2–G4 и E0 этим stage не принимаются.
