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
