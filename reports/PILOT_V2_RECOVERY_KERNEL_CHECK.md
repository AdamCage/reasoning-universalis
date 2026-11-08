# Механическая проверка EpistemeOS: provider recovery R1

8 ноября 2026. После закрытия R1 выполнен отдельный post-collection stage целостности. Первоначальные результаты и [проверка фазы A](PILOT_V2_KERNEL_CHECK.md) сохранены. R1 использует 96 неизменённых физических DeepSeek-записей A и 96 новых GPT-OSS/AkashML записей на тех же 24 roots; повторное использование не является независимой репликацией.

Использованы неизменённый `resumption.episteme_adapter` и чистый отдельный checkout `.research/deps/EpistemeOS` на revision `7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3`. Bundled `EpistemeOS/`, frozen package/collector и платные состояния не изменялись. Общий live ledger не читался для построения этого index: использован публичный `ledger-final.json` R1.

[Index](../artifacts/pilot-v2-recovery-2026-11-08/index.json) закрепляет 33 непустых входа: R1 protocol, development tasks, results, support, budget и future-design decision; 13 непустых исходников из 14-file frozen closure; source inventory и планы; public final ledger, reuse mapping, error audit с кодом диагностического проверяющего, actual offline reproduction check, manifest R1 delta, parent-A manifest и index. Пустой `resumption/__init__.py` остаётся закреплён inventory; evidence pack не принимает пустые отдельные артефакты. Сам index даёт 34-й captured artifact.

Перед запуском проверены совпадения scope/public protocol и corpus, frozen/current source bytes, представление всех 192 task/model/cap-ячеек и связь support с точными records. Эти проверки не изменяют исходные labels или статусы. Все входы повторно проверены по index после завершения stage.

```powershell
.venv/Scripts/python.exe -X utf8 -m resumption.episteme_adapter --kernel-root .research/deps/EpistemeOS --evidence-index artifacts/pilot-v2-recovery-2026-11-08/index.json --output .research/pilot-v2-recovery-integrity-stage
```

| Поле | Фактический результат |
|---|---|
| Stage | `stage_open-154376bc6e98427f` |
| Pack | `resumption_evidence_v1` |
| Captured artifacts | 34, включая index |
| Offline primary / same-data reanalysis | 68/68 completed; 0 failed; 0 unknown |
| Закрытие | `closed`, `criteria_met` |
| Outcome / inference mode | `inconclusive` / `exploratory` |
| Scientific validity / review | `not_assessed` / `not_requested` |
| E0 | `not_passed` |
| Повтор закрытого stage | та же история, без новых попыток |
| Новые модельные запросы | 0 |

[Stage result](../artifacts/pilot-v2-recovery-2026-11-08/episteme-stage-result.json): SHA-256 `a0f5a3f400811996763bf921d6e0c6f9230f259c9a4f3db6b118f41fedddce15`. SHA-256 index: `02f314c92420a49b069a0c7af559c082d52b290c9e4f606fc5b34a7f78c8c48d`; `events.jsonl`: `528bda32aa2785357d919afa87ee753a08df89e91d6c24c7d1cfd48f7c7681cb`.

Backup из `.research/pilot-v2-recovery-integrity-stage/backup` восстановлен через `episteme.recovery.restore` в новый `.research/pilot-v2-recovery-integrity-restored`. Все 424 события и 213 command receipts имеют точные совпадающие exports. Graph snapshot hash исходного и восстановленного Store совпадает с result: `61a57ebe03ba43d7405b6a6e641065ae3b333be86c0dd6ca4c462b4a16bad1e1`. Подтверждение: [backup check](../artifacts/pilot-v2-recovery-2026-11-08/episteme-backup-check.json).

[ZIP механического stage](../evidence/episteme-pilot-v2-recovery-2026-11-08.zip) содержит backup Store, stage result, события, evidence index, backup check и внутренний manifest. Размер — 4 673 118 байт, 404 элемента; SHA-256 `556945a0b3a2045a8aa2796c7b26fb3c0265151864d1b9627c4f17f30b32d3b6`. После сжатия каждый элемент проверен по roster и точным байтам. Настроенный credential и его JSON, URL и base64-представления сканировались только в памяти. `.env`, приватный holdout seed и execution environments в ZIP не включены. Машинное подтверждение: [archive check](../artifacts/pilot-v2-recovery-2026-11-08/episteme-archive-check.json).

Этот небольшой ZIP подтверждает сохранность kernel backup и захваченных inputs. Полный API-журнал находится в отдельном [R1 delta bundle](../evidence/pilot-v2-recovery-2026-11-08/manifest.json), связанном с parent A; его [network-disabled replay](../artifacts/pilot-v2-recovery-2026-11-08/reproduction-check.json) проверяет source/records/ledger и пересчитывает support. Kernel stage независимо хеширует байты в двух offline путях; он не повторяет статистический анализ независимо, не доказывает полноту reasoning и не оценивает научную валидность. `criteria_met` относится к byte-integrity roster, а не к не пройденному engineering gate R1. Человеческая разметка, scientific review, E0/G2–G4 и внешняя preregistration этим действием не создаются.
