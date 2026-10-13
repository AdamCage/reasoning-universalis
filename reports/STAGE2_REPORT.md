# STAGE2 — реализация измерительного pipeline

14 октября 2026, `stage2-development-v1`. Base: G1 receipt commit `380d9f03126dedcb03d1cdc2597ea9dfca4f2389`; утверждённый дизайн — `68fc12da05000674e3d770a07e449c37a4fbc119`, payload `04988a3ec82db073a04a71519e35f91740398d9a66636dc2935ce3377c079963`.

**Техническая реализация Stage 2 готова к ревью по всем 15 критериям §8 RESEARCH_PLAN.** Научная приёмка результатов не присваивается автоматически. G1 approved; E0 не пройден, G2 не заморожен. Новых RouterAI вызовов и расходов нет; реальные исторические наблюдения импортированы из опубликованного ZIP. Измеритель и DomainPack реализованы, кода ядра/его tests/README/AGENTS и гипотез не меняли.

## Реальный результат исполнения

`python3 -m stage2.episteme_bridge --output .research/stage2-release` прошёл настоящий kernel путь: captured external source → pack binding → frozen v2 environment → 6 primary + 6 same-data reanalysis → pack analysis → awaiting human review. Code pin DomainPack: `e18d07054a2e45282effc1e0007aabd3269a57ec54e2cea9c82725fadf88dd28`.

Импортированы 6 исходных ответов GPT-OSS-20B; получены 144 segments: **S1=10, S2=95, S3=39**. S2 — прежняя configuration, поэтому 95 не переименовываются в исторические 105 Stage 0. S1 — operation-cue heuristic, S3 — реальный ResearchBPE, явно отличный от generator tokenizer. Каждый native segment содержит точный slice, char/token offsets, position/progress/length, метод и revision; generator tokenizer/checkpoint revision неизвестны и записаны как unknown.

Технический count contrast выполнен на исходных trace/root pairs. Claim остаётся `exploratory/inconclusive`, mechanical gate passed, `scientific_validity=not_assessed`. API END не называется conclusion ролью. На тех же 95 S2 сегментах сохранены 190 Local/Contextual TF-IDF представлений и выполнен nested root-grouped development fit, давший K=2 uninterpreted states. Функциональные роли не назначены; single-family diagnostics и heldout guard tests не называются межсемейной научной оценкой. Шесть трасс — короткая development-демонстрация, не полноценный четырёхдоменный пилот или десятки новых live задач.

## Матрица 15 критериев §8

| № | Требование | Реализация и проверка |
|---|---|---|
| 1 | D1–D4 generators + independent verifiers | datasets.py, 36 сохранённых development экземпляров трёх difficulty strata; verifier tests по доменам/seed/levels, invalid planning action и negative answers; math multiplication, CNF truth table, exhaustive topological reference и planning simulation |
| 2 | Пять групп §6.2 и execution metadata §5.2 | ObservationStore.record_attempt; реальные records с Identity/Inference/Raw/Outcome/Provenance, provider/model/config/usage, unknown revisions/hardware явно; request/prompt/decoding/raw usage сверены DomainPack с origin |
| 3 | Parser error не теряет raw | CAS сохраняет до parsing; broken JSON test и secret-reflection redaction test |
| 4 | Ошибки/повторы/incomplete остаются | immutable attempt inventory, run_digest, incomplete/failed tests; неудачи не превращаются в eligible segments и нулевой metric |
| 5 | S1/S2/S3 отдельные реализации | S1 cue-based operation boundary heuristic и отдельный human-boundary input, S2 protected sentences, S3 actual fixed ResearchBPE tokens; все прошли реальную цепочку |
| 6 | Segment fields и token intervals | Exact slices/offsets/progress/length/config revisions; BPE merges/token text/offset/revision подтверждены, токены названы исследовательскими и не модельными |
| 7 | Нет cross-trajectory edges | transitions группирует trace × config, contiguous checks и негативные tests; Contextual не берёт предыдущую чужую trace |
| 8 | Ровно два semantic embedders + lexical baseline | allowlist BGE-M3/Qwen3-Embedding-8B, dimensions/finite/index/model checks; TF-IDF без LLM; спорный `parasail-bge-m3` отклонён тестом |
| 9 | Local/Contextual разные условия | input/context/config hashes, previous-only capped context; tests показывают различие и одинаковые paired inputs |
| 10 | Реальная trace → metric provenance | exported provenance-chain.json: StatisticalReport → feature/segment → exact raw response → inference run → model/provider/task/protocol; public origin manifest и raw hashes перепроверены |
| 11 | Самостоятельный DomainPack проходит ядро | standalone package, explicit wrapper allowlist, contract envelopes/pinning/hooks, полный v2 batch и bounded analysis; risen smoke и registry source сохранены |
| 12 | Раздельные identity digests | dataset/task/task-set/split/method/protocol/run/raw; tests показывают различие и неизменность dataset при negative/null contrasts |
| 13 | Все свойства §13.8 | Новые pack guards плюс regression kernel suite; подробное покрытие ниже |
| 14 | Протокол roles/ambiguity/agreement/versioning | Неизменённые approved ANNOTATION_PROTOCOL/MACHINE_ANNOTATION_PROTOCOL/config/schema/prompts; renderer/vote/quotes/finite panel tests. Human validation остаётся deferred; consensus не переименован в gold |
| 15 | License + Stage 0 full-trace admission для новых live моделей | Новых live вызовов нет. Исторический GPT-OSS-20B: Apache-2.0 по MODEL_LICENSES и сохранённый technical trace review, request/response/context/provider привязки. Неизвестные revisions/quantization не выдуманы; Nemotron не вызывался |

§13.8 проверен по конкретным путям: прежние packs проходят kernel regression; foreign task/raw mutation/source-byte changes и split violation отклоняются новым pack; repeated generation не independent replication; новый pack выдаёт только exploratory/inconclusive и блокируется при обходе kernel.claim; negative fixture review сохраняет replan, повторный pack analysis не создаёт новый обходной claim; incomplete/failed records остаются; code drift меняет pin и требует новую revision; без human review нет paper eligibility/scientific approval; negative и zero contrasts сохраняют знак/нулевое значение, paper builder не публикует их без review. Существующие kernel family-veto tests также проверяют inheritance между повторными claims/protocols. Fixture negative reviews существуют только в temporary tests, не в реальном evidence store.

## Верификация и переносимый пакет

- Root suite: **61/61** (`python3 -m unittest discover -s tests -v`), включая 18 новых pipeline/DomainPack тестов.
- EpistemeOS: **711 tests, 1 skipped**, остальные прошли (`uv run python -m unittest discover -s tests -v`). Пропущен opt-in Docker test: EPISTEME_CONTAINER_TEST не задан. Docker isolation не объявлена проверенной.
- Real kernel workflow и source/bytes verification прошли; `python3 -m stage2.evidence --verify evidence/stage2-2026-10-14.zip` проверяет manifest, 6 observations, 144 segments и raw provenance без сети/env.
- G1 exact snapshot verifier, `git diff --check` и отсутствие diff в EpistemeOS/спецификации/утверждённых design files проверены. `.env` не отслеживается Git, secrets/Authorization не входят в экспорт. Исходные Stage 0 responses не переписаны.

[Stage 2 ZIP](../evidence/stage2-2026-10-14.zip) — 160 файлов, SHA-256 `74b0f24a80955af6475831532db83b62b79b671413aba3ca2b12d4686b4327fe`. В нём captured source, original public Stage 0 manifest, kernel backup, proof chain и source code. Исторический ZIP SHA-256 `420949cd9176713534f1152be1a8cbfa90c7eace91e5b267aa9e6cfc1de7ba1d`; origin manifest SHA-256 `a6aa1248ddce0c111bcdf5c4d31512b41f134ebca208d891d1e6781e414438e8`. Это authenticated-by-known-hash published bytes, не новый remote inference attestation.

Команды и API — [stage2/README.md](../stage2/README.md). Стандартный Episteme CLI без explicit application wrapper не знает внешний pack; автоматического plugin discovery нет.

## Границы и следующая стадия

Все методы — development реализации. S1 semantic accuracy, S2 language/math boundary robustness, tokenizer sensitivity, role interpretation, cluster stability и настоящее new-family transfer требуют E0/пилота. ResearchBPE не подменяет известную tokenizer revision генератора; model token billing/online policy его intervals не используют. Provider/weights/quantization неизвестности остаются ограничениями reproducibility. Field names, green suite и механический gate не утверждают H0–H7.

Episteme locked profile/hooks работают тем же OS user. Генерация — trusted external bytes; новые программы пересчитывают только JSON в разрешённом development контексте, закрытых данных не открывали. Фактическая OS independence/sandbox не заявлена; две реализации одного автора не new-data replication. Научный pipeline позже требует проверенной trusted execution процедуры/границы доступа для закрытых данных.

Для следующего live этапа нужен общий budget reconciliation: исторический Ledger содержит 32 entries и **246.7988793802352 RUB charged-or-reserved**, а не только 0.41653321870992 RUB подтверждённых receipts; 4 billing costs неизвестны. Бюджет не сброшен новым `.research`. Transport требует existing snapshot hash и общий stage0 lock, сохраняет pending/unknown, резервирует до dispatch и не делает retries. В этой среде RouterAI не входит в разрешённые HTTP destinations; здесь live validation не выполнялась и для текущего offline §8 path не требовалась.

Следующий этап — отдельно разрешённый научный пилот §5.5/Stage 3: допуск длинных повторных трасс когорты, independent human validation после возобновления deferral, все шесть E0 проверок, стоимость/мощность. После них G2 замораживает scientific thresholds/N/contrasts/budget. STAGE2 не запускает основной корпус, prefix probes или actual stopping.
