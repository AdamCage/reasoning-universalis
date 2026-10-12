# Описание `reasoning_universalis_v1` — Stage 1 v1

Статус: **design only**, пакет ещё не существует в registry. `risen_universalis_v1` остаётся неизменённым демонстрационным smoke. Текущий `measurement/` — предварительная development-библиотека, не реализованный DomainPack и не пройденный Stage 2. Это описание соответствует `EpistemeOS/src/episteme/domains/api.py`, `domain_packs.py` и ADR 0016/0019/0024. Stage 1 не меняет ядро/registry и не запускает эксперимент.

## Контракт и envelopes

Будущий package directory регистрируется отдельно с ID `reasoning_universalis_v1`, contract v1 и versioned code manifest всех относительных source paths/hashes. Hooks импортируют stdlib и публичный `episteme.domains.api`; side effects, сеть, env/time и implicit randomness запрещены. Optional read-only `capture(source)` единственный читает объявленный local path **до** binding. Никакой hook не получает Store или capability записи в CAS.

| Hook / envelope | Предметное содержание будущей реализации |
|---|---|
| `MANIFEST` / `PackManifest` v1 | pack_id/version, metrics+units, raw/metrics output schema IDs, numeric_tolerance, hidden_inputs, execution_profiles, roster_semantics, statistical_capabilities, interpretation_cautions, capture=true |
| `describe()` / `ParameterCatalog` v1 | Strict schema параметров analysis condition: hypothesis/contrast ID, dataset/task-set/split/method/ontology digests, inference cohort condition и mode; неизвестные поля отклоняются. Human approvals не задаются caller как boolean |
| `validate_parameters()` | Проверяет metric/contrast pairing, admitted cohort и method revisions; не назначает scientific approval |
| `capture(source)` / `CaptureBundle` v1 | Без сети читает frozen directory внешних артефактов, bounded inventory paths+SHA-256+sizes и audit. `source.kind=local_directory`; происхождение RouterAI указывается в audit и run manifest, нельзя придумать unsupported `routerai` envelope kind |
| `compile_protocol(CompileRequest)` / `ProtocolDraft` v1 | Статистический план выбранного контраста, roster integer indices в canonical table независимых roots, `roster_semantics=frozen_unit_index`, `sample_size_scope=total`, seen_data/exposure. Это индексы roots, не seeds inference |
| `compile_execution(CompileRequest)` / `ExecutionPlanV2` | Offline primary/reanalysis source trees, frozen input и lock/environment, raw/metrics outputs, bounded wall/bytes и capabilities. Локальное исполнение вычисляет features/statistics, **не** генерирует RouterAI reasoning |
| `validate_protocol(ProtocolContext)` | Повторно сверяет exact pinned compilation, G2 при confirmatory, E0 applicability и split policy по разрешённым frozen artifacts. Вызывается до binding, batch и анализа. Не читает hidden bytes |
| `validate_outputs(AnalysisContext,CasView)` / `OutputCheck` v1 | По slot проверяет raw bytes against исходный inventory, root/cohort/splits, отсутствие соседних trace transitions, offsets, parent digests, denominators, completeness и exclusions; ошибки дают failed |
| `recompute_metrics(...)` / `Recomputation` v1 | Независимо пересчитывает metric per root из raw observations, возвращает primary/reanalysis values, absolute differences и arithmetic tolerance |
| `analyse(...)` / `AnalysisReport` v2 + `StatisticalReport` v1 | Task-root estimates и uncertainty по frozen contrast, все 12 statistical fields с supplied/not_supplied/not_applicable и reason, scope/outcome/limitations без повышения силы claim |

Numeric tolerance — только floating-point согласованность, не scientific error или equivalence margin. Exact hashes/IDs/offsets требуют точного равенства. Конкретные metrics/units/tolerance выбираются будущей version для утверждённого контраста; Stage 1 не подставляет финальный primary score вместо отложенных §11.2.

ProtocolDraft statistical_design должен соответствовать текущему `StatisticalDesign`: experimental_unit=task_root, uncertainty resampling_unit совпадает с ним, mode/exclusions/stopping/family/data_splits и sample size из конкретного frozen roster. Все traces/repeats/segments одного root вложены в его slot; попытки inference учитываются отдельно от primary/reanalysis offline slots. `run_limit` покрывает минимум два запуска на каждый roster index по контракту и не является разрешением на столько сетевых генераций. Future derived folds не считаются независимыми roster units. Unsupported nested-design semantics требуют отдельной разработки/проверки до исполнения, не притворного поля в envelope.

## Предметные схемы и identity bindings

Планируемые schema IDs — контракт данных, не уже реализованные validators:

| Schema ID | Обязательные поля и инварианты |
|---|---|
| `reasoning_universalis_v1/inference-v1` | Identity: study/problem/model/revision/trace/run/sample; Inference: prompt digest, decoding, seed, runtime, start/end/stop; Raw: request/response digests, reasoning, final, usage; Outcome: verifier ID/version/verdict/artifact/uncertainty; Provenance: dataset/split/code/environment/parents (§6.2). Model family/lineage, provider, available tokenizer/engine/quantization, unknown fields и license snapshot (§5.2) обязательны |
| `reasoning_universalis_v1/attempt-v1` | attempt/reservation IDs, requested/observed condition, completed/failed/cancelled/unknown, errors/truncation, usage/cost/unknown, parent request/response hashes. Неудача parsing не теряет raw |
| `reasoning_universalis_v1/segments-v1` | segment/trace/run/root IDs, exact text, Unicode `[start,end)`, реальные token offsets либо unknown с причиной, index/relative progress/length, segmentation method/version; text равен slice исходной трассы, нет переходов между traces |
| `reasoning_universalis_v1/representation-v1` | segment IDs/text hash, embedder requested/returned/provider/revision/dimension, finite vector, Local/Contextual и context offsets/digest. Сравнение использует одинаковое intersection admitted IDs |
| `reasoning_universalis_v1/state-v1` | segment/fit/ontology/mapping IDs, training-root/family digests, state/role, unknown/ambiguous, confidence и source annotations; данные test не являются fit parents |
| `reasoning_universalis_v1/raw-v1` | Root-index table, immutable attempt inventory, inference/segments/representations/state parents, cohort/method/split revisions, input digest; арифметические sufficient statistics всегда имеют путь к observations |
| `reasoning_universalis_v1/metrics-v1` | finite primary metric scalar по одному root и объявленные secondary values с units/denominators и feature parent digests. Missing/undefined не заменяется нулём; невалидный root сохраняется как missing/exclusion по protocol |

Dataset digest, task digest, canonical task-set digest, split digest, method digest, protocol event hash, run digest и raw response digest **разные**. Dataset identity не включает metric/contrast. Каждый metric value ведёт через feature → segment → raw reasoning slice → raw response → inference attempt → requested/returned checkpoint + problem + protocol. Сырые bytes и parsed JSON хранятся раздельно. При secret reflection безопасная редактированная версия маркируется, запрещено хранить оригинал с секретом; такие observations не обещают безусловную byte-perfect передачу original HTTP.

Binding ядра создаётся `pack.preregister` с explanation_set, pack ID/version/code digest, parameters, host_inputs, capture digest и environment digest. Реальный binding хранит protocol/hash, study/explanation_set, pack manifest/catalog/code pin, parameters, host_inputs, capture, protocol_draft, execution_plan, roster/sample scope, environment/closure, tolerance, hidden_inputs и `scientific_validity=not_assessed`. Не добавлять выдуманные dataset/method fields в strict kernel envelope: предметные bindings находятся в parameters/frozen input/raw schemas и проверяются pack hooks. Hidden reference/gold остаются вне analysis CasView; public evaluation verdicts/ошибка допускаются только по объявленной policy. Независимый verifier производится внешним доверенным шагом и импортируется с provenance; пакет не обещает доступ к скрытому gold для его пересчёта.

## External evidence → review → claim

1. Отдельный будущий этап с разрешённым общим budget и frozen inference manifests создаёт RouterAI артефакты. Model admission включает full visible trace, license, request/response binding, provider и длинные повторы; seed/revision unknown сохраняются. Stage 1 не делает этого.
2. Внешние bytes локально захватываются `store_capture`, возвращая CAS capture digest и audit; **events_written=0**. Сам capture не evidence transition и не human approval.
3. `pack.preregister` через CommandService/planner связывает capture с question/explanation lineage, frozen protocol и exact pack code/environment. Historical bytes получают seen_data и exploratory exposure; уже увиденные данные не делаются confirmatory задним числом.
4. `batch.plan`/offline execution и reanalysis создают проверяемые features/statistics по frozen root roster. Локальный managed execution удостоверяет пересчёт импортированных bytes, не удалённую генерацию, неизвестный checkpoint или применение seed у provider. External inference remains trusted external evidence с перечисленными ограничениями.
5. Settlement, `pack.analyse` (analyst), OutputChecks/Recomputations и StatisticalReport определяют mechanical claim ceiling. При неподходящем E0, незавершённом статистическом плане, missing coverage/uncertainty или deviations нельзя предлагать confirmatory supports/refutes. Report остаётся bounded exploratory/inconclusive либо анализ вообще блокируется по preregistered rule; неправильная метрика/bytes — refusal.
6. Kernel claim basis включает protocol/run/output/code и reports, затем `review.assign`, delivery и `review.submit` с допустимым независимым human reviewer/context, obligations/resolution и повторной проверкой persisted evidence revision. Ключевые findings сохраняются при новом claim; пересоздание claim не обход отрицательного review. G3 отдельный человеческий научный checkpoint, не роль LLM. Package не пишет approval и не включает научный claim в paper без kernel/review eligibility.

StatisticalReport поля: estimand, estimator, point_estimate, uncertainty, confidence_interval, effect_size, assumptions, sample_size, multiple_testing, stopping_rule, sensitivity_analysis, deviations. Неприменимость допускается только по protocol, not_supplied требует причины и ограничивает claim. Kernel решает ceiling; новый pack не повышает scientific validity.

`uv_locked_python_v2` и subprocess хуков — тот же OS user, **не sandbox**. Allowlisted CasView ограничивает интерфейс, не файловые права пользователя. Код нельзя исполнять с доступом к закрытому research store лишь по этому профилю; до Stage 2 требуется проверенная фактическая граница исполнения либо доверенная offline процедура с раскрытием ограничений.

## Приёмка будущей реализации

До Stage 2 acceptance проверить §13.8: сохранность старых packs; отказ при чужом raw/changed bytes и split violation; отсутствие псевдорепликации; неизменность claim ceiling; сохранность veto reviewer/failed generations; новые revisions после изменения code; отсутствие scientific approval без human review; null/negative не меняется при сборке статьи. Кроме этого: exact offsets, schema strictness/finite vectors/identity, root roster/sample-size consistency, training/test fit parent audit, raw-to-metric linkage, unknown costs, external-vs-local execution. Эти тесты **не выполнены** созданием описания, текущие regression tests старого pipeline не принимают новый pack.
