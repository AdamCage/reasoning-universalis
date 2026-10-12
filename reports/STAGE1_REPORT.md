# STAGE1 — пакет научного дизайна для ревью

12 октября 2026, версия `stage1-design-v1`, baseline `83da1ca355c767f67d4558d5735078f443037e28` (`origin/main` при передаче).

**Дизайн подготовлен, Stage 1 ожидает утверждения AdamCage.** G1 pending, G2/G3/G4 не выполнены; E0 не пройден. Выполнена документальная реализация §7 RESEARCH_PLAN, не измерительный Stage 2, научный пилот или основной корпус. Новых вызовов RouterAI и платной разметки нет. H0–H7, научная спецификация и EpistemeOS сохранены.

## Пакет и прослеживаемость

- [Preregistration](../design/PREREGISTRATION_DRAFT.md): точные исходные секции H0–H7, поддержка/опровержение, наблюдаемые признаки, выводы, девять окончательных полей и отдельные кандидаты дизайна. H0 не имеет самостоятельных support/refutation блоков в источнике: операционные правила обозначены как производные, не выдуманные цитаты.
- [Hypotheses JSON](../design/hypotheses.json): source hashes, operational_fields, design_choices и references на неизменённый SELECTED_DECISIONS. Все окончательные незаданные поля сохраняют обязательный deferred текст.
- [Cluster-first](../design/STATE_DISCOVERY.md): nested root/family holdouts, development selection K, out-of-sample states, functional mapping freeze, noise/ambiguous и защита от leakage.
- [Машинная разметка](../design/MACHINE_ANNOTATION_PROTOCOL.md): пять голосов, majority 3/5, максимум два раунда, десять различных seeds, отсутствие automatic retries; config, strict response schema и два exact prompt templates. Инженерные детали выбраны агентом в разрешённых рамках и предъявлены на ревью, не приписаны прежнему user approval.
- [Splits](../design/SPLITS.md): исторические roots development-only, exposure/access и validation reset, новая семья × новые roots; independent human reference/E0 пока deferred. Новых validation/confirmatory manifests нет.
- [DomainPack design](../design/DOMAIN_PACK_DESIGN.md): действующие envelopes/hooks, strict kernel binding и отдельные предметные schemas, external evidence capture/import, offline metrics, review/claims. Реализация registry/pack не начата.
- [G1 package](../design/G1_APPROVAL.md) и [manifest](../design/STAGE1_APPROVAL_MANIFEST.json): конкретная версия вопроса/исходной онтологии и файлов. Mutable `G1.json` pending — отдельный receipt, исключён из payload вместе с самим manifest для устранения круговых hashes.

| User-selected направление | Конкретное решение этой версии | Источник выбора |
|---|---|---|
| Вся первая статья H1–H7 | H1–H3 primary candidate family; H4 secondary exploratory; H5/H7 secondary exploratory feasibility-gated; H6 exploratory admission-gated | SELECTED_DECISIONS: article_scope, multiplicity, scope_resolution |
| Cluster-first | Состояния сначала development, K не равен заранее восьми; исходные роли сохранены для mapping | ontology |
| Conservative roots, новая семья × новые roots | Fold-specific fit без всей target family; repeats/variants/prefixes в одном root | task_grouping, transfer |
| S1/S2/S3 | Все три как отдельные measurement conditions, S1 и true token maps остаются будущей работой | segmentation |
| Только DeepSeek ensemble, human deferred | Один multiseed измеритель, конечный voting protocol; никакого human gold/E0 pass | annotation, human_validation, E0_status |
| Предварительные E0 targets | Прежний JSON сохранён, пересмотр только development, после validation новая закрытая выборка | preliminary_E0_targets |
| Metric/statistical recommendations | Per-H candidates рядом с deferred final fields; Holm/FDR остаются G2 candidates | metric_candidates_selected, statistical_candidates_selected |
| Самостоятельный pack, AdamCage G1 | Описание по публичному API, exact manifest и explicit version approval | domain_pack, G1 |

## Девять критериев §7 RESEARCH_PLAN

«Подготовлен» ниже относится к проверяемому дизайну. Приёмка всего этапа не объявлена до пункта 9.

| № | Критерий | Свидетельство | Статус / открытая часть |
|---|---|---|---|
| 1 | H0–H7, support и refutation в исходном смысле | Preregistration + source_text/quote hashes + exact section verification | Подготовлен; производные H0 правила маркированы |
| 2 | Основное исследование A/B, C не доказан | Preregistration: вопрос и границы | Подготовлен |
| 3 | Visible reasoning, hidden activations, зависимости генерации и post-answer explanation разделены | Preregistration: граница наблюдаемого; raw admission rules | Подготовлен |
| 4 | Все девять полей §11.2 для каждой H | Hypotheses JSON + таблицы preregistration | Подготовлен, final G2 values отложены |
| 5 | Незаданные поля deferred, нет выдуманных чисел; Holm example/candidate | operational_fields exact deferred строка; separate design_choices; E0 targets отдельно | Подготовлен; procedures/contrasts/thresholds позже G2 |
| 6 | Единица — задача/независимый экземпляр, не segment/repeat | Preregistration + SPLITS + DomainPack root roster | Подготовлен; реальная independence audit ещё не проводилась |
| 7 | Шесть условий §11.4 — совместное правило, не результат | Preregistration: нумерованный список | Подготовлен; ни одно не объявлено полученным результатом |
| 8 | reasoning_universalis_v1 самостоятельный, risen остаётся smoke | DOMAIN_PACK_DESIGN; diff вне EpistemeOS | Подготовлено описание; Stage 2 реализация не выполнена и не требуется §7 |
| 9 | G1 связывает вопрос/исходную онтологию с человеком и immutable state | Approval manifest + G1_APPROVAL + designated AdamCage + pending receipt | **Открыт:** explicit approval конкретного snapshot commit/payload digest отсутствует |

## Проверки

- Handoff preparation manifest: все 12 записей сверены с точными Git blobs baseline `83da1ca`, не working CRLF hashes.
- `python3 design/verify_stage1.py`: hashes/полный inventory, exact исходные секции восьми H, все 72 deferred поля, отдельные candidates, seeds/schema, исторические roots и E0 status. Read-only, без env и сети. `--commit` проверяет immutable Git snapshot; выход означает integrity, не scientific validity.
- `python3 -m unittest discover -s tests -v`: **43/43** (37 прежних + 6 guards пакета G1). Новые проверки отклоняют изменённые bytes, урезанную исходную гипотезу даже после перевычисления manifest, преждевременный final threshold, повтор seed и historical root в confirmatory. Это не тесты несуществующего нового DomainPack.
- `python3 -m measurement.demo`: 6 historical traces, 95 S2 segments, manifest `3b5ec259210d90f41ee3f6f0009d2daa1c5ce4eb83bcc75286758e30c4e8ee9a`, scientific_approved=false, token_alignment_complete=false. Это проверка прежнего offline import, не E0.
- `python3 -m stage0.evidence --verify evidence/stage0-2026-10-12.zip`: 32 paid attempts, 6/6, 105 old segments, 210 vectors, 175 identity-verified. Два `parasail-bge-m3` ответа (35 vectors) остаются inadmissible; 28 confirmed receipts = 0.41653321870992 RUB, 4 costs unknown. Алиасы и unknown costs не «исправлены» документами.
- `git diff --check`: без ошибок. Diff от baseline не меняет `RESEARCH_SPECIFICATION.md`, `RESEARCH_PLAN.md`, `SELECTED_DECISIONS.json`, `E0_PRELIMINARY.json`, исходники/тесты/README/AGENTS EpistemeOS или stage0/measurement runtime. Нет отслеживаемого `.env`; Stage 1 verifier не читает секреты. Не добавлены API headers/credentials. Интеграционные тесты ядра не требуются: его семантика/код не менялись.

## Риски, открытые решения и порядок продолжения

Документы задают метод, но не доказывают пригодность измерителя, RouterAI seed determinism или полноту checkpoint identity. Будущие сетка K/folds, representative coverage, edge support/smoothing, scientific equivalence margins, tests/contrasts/correction, N/power и budget требуют development/pilot и G2. Их отсутствие — намеренный scientific deferred status, не скрытый этап реализации. Конкретные prompts/voting config предъявлены как engineering design, будущий renderer и validators ещё не написаны.

Следующий шаг этой задачи — ревью пакета AdamCage и явное version-bound G1 по [инструкции](../design/G1_APPROVAL.md). Это требование handoff, §7.9 плана и §13.7 спецификации. Пока approval не получен, `approved_commit`, `approved_artifact_hashes`, `approved_at`, `approval_statement` остаются null.

Последующие Stage 2/3 — отдельная работа: generators/verifiers D1–D4, cluster-first adaptation, собственный DomainPack и §13.8 tests, безопасная execution boundary, admission и согласованный общий бюджет. Human validation должна быть отдельно возобновлена; до независимого E0 содержательная интерпретация H1–H7 закрыта. G2 замораживает cohorts/splits/criteria/procedures/power/budget перед основным корпусом. Actual stopping/continuation для H5/H7 требует feasibility и реального billing; G3/G4 не выполняются этим пакетом.
