# Механическая проверка EpistemeOS: pilot v2, фаза A

8 ноября 2026. Проверены зафиксированные артефакты завершённой development-фазы A. Реестр содержит все 192 плановые ячейки: 98 фактических запросов и 94 неотправленные ячейки. Проверка EpistemeOS не выполняла новых модельных запросов и не обращалась к продолжающему изменяться общему ledger. В index включён отдельный публичный снимок `ledger-final.json` фазы A.

Использован отдельный чистый checkout `.research/deps/EpistemeOS`, revision `7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3`, и неизменённый `resumption.episteme_adapter`. Исторический `EpistemeOS/`, научная спецификация, исходники и платное состояние фазы A не изменялись.

[Индекс](../artifacts/pilot-v2-2026-11-08/index.json) фиксирует 26 непустых входов: протокол, development-корпус, результаты, class support, бюджет и решение о будущем дизайне, исходники, frozen source inventory, план распределения, prospective cost plan, launch ledger, публичный final ledger и offline reproduction check. Его построение проверило точное соответствие protocol/corpus/source pins, представление всех 192 task/model/cap-ячеек ровно один раз и связь support с точными task/result records. Это допускает честно сохранённые неотправленные и незавершённые ячейки. Пустой `resumption/__init__.py` закреплён source inventory; контракт evidence pack запрещает пустые отдельные входы. Сам index стал 27-м захваченным артефактом.

Фактическая команда:

```powershell
.venv/Scripts/python.exe -X utf8 -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --evidence-index artifacts/pilot-v2-2026-11-08/index.json --output .research/pilot-v2-integrity-stage
```

| Поле | Фактический результат |
|---|---|
| Stage | `stage_open-890f88169c9d4459` |
| Pack | `resumption_evidence_v1` |
| Захваченные артефакты | 27, включая index |
| Offline primary и same-data reanalysis | 54/54 completed; 0 failed; 0 unknown |
| Закрытие | `closed`, `criteria_met` |
| Outcome / inference mode | `inconclusive` / `exploratory` |
| Scientific validity / review | `not_assessed` / `not_requested` |
| E0 | `not_passed` |
| Повтор закрытого stage | та же история, без новых попыток |
| Модельные запросы в этом stage | 0 |

[Сохранённый результат](../artifacts/pilot-v2-2026-11-08/episteme-stage-result.json) имеет SHA-256 `279e62a8dfdc6cb2a4651d6c0ec26fb383b4d1f891b77ec9eb0e6bed1d8193f5`. SHA-256 index: `4144724ce31a4eca15661d47449b466159161a1e522508b56cc807d150f53e0f`; `events.jsonl`: `fbdeb0bc7bba77ac5a11066017b1d0d8aa9f5ac8e4144f961320c6a0d15d30f5`.

Adapter создал backup в `.research/pilot-v2-integrity-stage/backup`. `episteme.recovery.restore` восстановил его в новый `.research/pilot-v2-integrity-restored`. Экспорт всех 340 событий и 171 command receipt побайтно совпал с оригиналом. Graph snapshot hash обеих копий совпал с stage: `915685083ed9bb9cbbaeefa93daef7b332fd0216dc3a92f10a03456d40f21c84`. Машинное подтверждение: [backup check](../artifacts/pilot-v2-2026-11-08/episteme-backup-check.json).

[Переносимый ZIP](../evidence/episteme-pilot-v2-2026-11-08.zip) содержит backup Store, stage result, события, evidence index, backup check и внутренний manifest. Размер — 2 748 209 байт, 327 элементов; SHA-256 `93073db161e35a8d70b84f2b4bf4eb84b4e51ef312eed718980867b89249c388`. Все элементы после сжатия проверены по roster и точным байтам. Настроенный credential и его JSON, URL и base64-представления проверялись только в памяти; `.env`, приватный holdout seed, зависимости и execution environments в архив не включены. [Archive check](../artifacts/pilot-v2-2026-11-08/episteme-archive-check.json) сохраняет это подтверждение.

`criteria_met` относится к конечному реестру проверок целостности. Два offline пути независимо пересчитывают SHA-256 и размеры захваченных байтов; они не выполняют независимый пересчёт class support, не подтверждают полноту reasoning traces и не устанавливают engineering readiness фазы A. Это post-collection механическая проверка, без ретроспективной preregistration эксперимента, человеческой разметки, научного ревью или принятия E0/G2–G4.
