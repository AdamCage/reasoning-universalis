# EpistemeOS: целостность machine-development пакета

**Механическая проверка завершена; E0 не пройден.** Pinned kernel 7f5a1a0e43d7c35196cc8b3c9c74a618aa2559c3, отдельный checkout .research/deps/EpistemeOS, остался неизменным. Исторический bundled EpistemeOS также не редактировался.

Индекс [evidence-index.json](../artifacts/machine-annotation-development-2026-11-08/evidence-index.json) связывает 48 непустых артефактов / 9,660,483 bytes: закрытые inputs/results/summary, final ledger, стоимость, raw-export manifest и passed replay receipt, frozen source snapshots, failure audit и стабильные исходные квитанции. SHA индекса: 557ec9aa9ce3d1f2a52e5044187a08a91ddd12148cefbb7b3344e44ac3a0ce1d. Сам индекс становится 49-м артефактом kernel capture. Один пустой исходник сохраняется через source inventory, поскольку индивидуальные пустые CAS inputs pack не принимает.

Stage stage_open-ce4e6ef15a254d31 закрыл конечный реестр из **98/98 offline hash jobs**, 0 failed, 0 unknown. Это два прохода по тем же 49 артефактам, а не 98 новых модельных экспериментов. Disposition — criteria_met; inference_mode — exploratory; outcome — inconclusive; scientific_validity — not_assessed; review — not_requested. Закрытый stage повторно читался без новых jobs, events или receipts.

| Проверка | Фактический результат |
|---|---|
| Events / receipts | 604 / 303 |
| Fresh restored Store | 562 файла / 37,661,248 bytes |
| Backup → restore | Database и все CAS bytes совпадают точно |
| Event / receipt exports | Совпадают точно |
| Measured source/config files | Все 26 совпадают с frozen inventory и snapshot; изменённых 0 |
| Новые модельные / сетевые вызовы проверки | 0 / 0 |

Graph snapshot до и после восстановления: 7ef01bf967f0f4f368751729ab142ac2ff561e033f424c28c396778e7aec0779. Raw source inventory: 942e6a58acc19649cc5407e94acfbd72eed4f2944d4ffae441de624fc41c6f0e. CRLF у наследованных исходников сохранены в точных captured bytes; Git LF файлы не подставлялись. Все 48 индексированных файлов остались неизменными после capture.

Публичные результаты: [stage-result](../artifacts/machine-annotation-development-2026-11-08/episteme-stage-result.json), [backup/restore/source proof](../artifacts/machine-annotation-development-2026-11-08/episteme-backup-check.json), [archive verification](../artifacts/machine-annotation-development-2026-11-08/episteme-archive-check.json). SHA stage-result: 2addc99b8ccca58e4e7cd2815ec02b65f6136ed78a6cc5e9f9abcce12c471c5e.

## Переносимый архив

[episteme-machine-annotation-2026-11-08.zip](../evidence/episteme-machine-annotation-2026-11-08.zip) содержит coherent backup, capture, events, stage-result, проверку восстановления и использованные внешние post-stage drivers. 620 членов, 9,972,264 compressed bytes / 48,125,289 uncompressed bytes. Внутренний manifest сопоставляет каждому payload точные SHA-256 и размер; после сжатия все члены проверены повторно.

SHA ZIP: **21844be84bae9e267c4e12176b7f82515917ea38b48192ee29487b3474c5e382**. Перед упаковкой выполнен in-memory scan configured credentials и common encodings, включая nested ZIP payloads; значения секретов не выводились. .env, зависимости, venv и приватные настройки в архив не входят. Сохранённый holdout seed не читался.

Для Windows backup можно извлечь отдельно в короткий путь и передать pinned recovery.restore через обычный путь SQLite. Capture с длинными исходными путями допускает проверку manifest/SHA непосредственно через ZIP, без распаковки этих длинных имён. Внутренний manifest покрывает и capture, и весь переносимый Store backup.

## Windows path recovery

Первый запуск остановился на MAX_PATH при копировании длинного frozen source path, до создания kernel Store/events. Его partial capture и диагностическая provenance сохранены отдельно в .research/machine-annotation-integrity-stage-longpath-failure.

Новый свежий capture с extended-length Windows prefix выполнил все 98 jobs и stage_close. Затем pinned backup столкнулся с несовместимостью extended prefix и SQLite read-only URI (invalid authority %3F). Внешний driver открыл **тот же уже закрытый Store** через обычный путь и завершил backup/export. Сравнение до/после closed-stage resume подтвердило неизменность events/receipts; jobs не повторялись. Kernel, 26 measured source files и логический индекс не менялись; registry/system settings не затрагивались. Backup затем восстановлен в новом Store, с проверкой точных database/CAS bytes и графа. Исходный активный SQLite file не объявляется физически неизменным: доказательство byte equality относится к backup → restored database/CAS.

Эта регистрация сделана **после сбора** и проверяет хэши, граф и переносимость. Она не повторяет независимо статистический анализ, не проверяет истинность machine labels, полноту исследования или hypotheses H0–H7 и не создаёт человеческое approval, scientific review, независимую репликацию либо E0 pass. Final ledger здесь только захеширован из закрытой копии: все 2109 строк / 2038.3174633704220 RUB и исходный 984-row prefix сохранены; новый paid сбор не выполнялся.
