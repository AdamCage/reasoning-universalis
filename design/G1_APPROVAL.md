# Конкретный пакет G1 — Stage 1 v1.1

Утверждающий: **AdamCage**, владелец репозитория, назначен пользователем. Статус: **дизайн подготовлен, Stage 1 ожидает утверждения**. Основание требования explicit approval: `STAGE1_CLOUD_HANDOFF.md`, работы 7–8 и критерий завершения; `AGENTS.md` отличает выбор направлений от утверждения версии; §7.9 плана и §13.7 спецификации требуют имени и immutable hash. Настоящее разрешение начать Stage 1 не является approval этой новой версии.

## Что предъявлено

`STAGE1_APPROVAL_MANIFEST.json` задаёт точные files и SHA-256 bytes, Git blob IDs, research question/ontology sources, selected-decisions source и baseline commit. Payload digest — SHA-256 canonical JSON payload (`sort_keys=True`, separators `,`/`:`, `ensure_ascii=False`, `allow_nan=False`), без поля самого digest. Git snapshot commit с этим manifest сохраняет весь набор. Hash научной спецификации назван отдельно от hash пакета; исходные гипотезы сохранены.

Основной документ — `PREREGISTRATION_DRAFT.md`, source snapshots/operational fields — `hypotheses.json`. Правила cluster-first — `STATE_DISCOVERY.md`, разметка — `MACHINE_ANNOTATION_PROTOCOL.md` + config/schema/prompts, splits/E0 — `SPLITS.md` и прежние human/E0 протоколы. DomainPack **описан**, не реализован. Матрица приёмки и проверки — `../reports/STAGE1_REPORT.md`.

На ревью предъявляются также выбранные здесь инженерные детали: пять голосов, majority 3/5, максимум два раунда; incomplete panel не открывает semantic повтор, audit 10% completed development items с одной same-seed панелью, decoding/timeout/token cap, strict schema и два prompt revisions. Это конкретизация user-selected диапазона, не утверждённый ранее пользователем набор чисел. H4/H5/H7 — prespecified secondary exploratory (H5/H7 feasibility-gated), H6 — exploratory admission-gated; H1–H3 — основное candidate family. Final G2 procedures/contrasts и пороги остаются отложенными.

## Как проверить и утвердить

Из корня: `python3 design/verify_stage1.py`; для неизменяемого Git snapshot: `python3 design/verify_stage1.py --commit <snapshot_commit>`. Проверка read-only, без env и сети. `--commit` должен называть commit, содержащий предъявленный manifest, а не baseline. Для независимой проверки скрипт должен происходить из доверенной/reviewed версии; green exit не является scientific approval.

AdamCage утверждает **названные snapshot commit и payload digest** явным сообщением/решением, например: «Утверждаю G1 для Stage 1 v1.1, commit <snapshot_commit>, payload SHA-256 <payload_sha256>. Утверждаю научный вопрос и исходную онтологию гипотез в этом пакете; это не G2, не разрешение платного запуска и не scientific review G3». Допустимо утверждение только вопроса/онтологии с замечаниями к остальному дизайну — тогда отдельно записываются scope/замечания и Stage 1 acceptance не выдаётся автоматически.

После explicit решения повторно проверить exact snapshot и manifest. В **новом** commit записать `G1.json`: status approved, approver AdamCage, approved_commit=<snapshot_commit>, approved_artifact_hashes=<payload_sha256 и source/ontology manifest references>, approved_at с timezone, дословный approval_statement и reference решения. Нельзя подставить текущую дату/имя как свидетельство уже совершённого approval. Если версия изменена по замечаниям, создать новый payload manifest/snapshot и предъявить заново.

Manifest не включает самого себя и изменяемый receipt `G1.json`, исключая self-reference. Requested пакет фиксирует pending status в отчёте; после approval он остаётся историческим review snapshot. Approval receipt связывает его отдельно, не меняя approved bytes. Manifest файлов **не** является EpistemeOS persisted scientific transition: отдельный будущий импорт/checkpoint должен сохранить реальное решение с provenance, не выдуманные события.

## Следующие условия

G1 не принимает E0 и не открывает confirmatory. Stage 2 требует отдельного разрешения на реализацию/адаптацию измерителя и DomainPack, реальных validators/§13.8 tests и безопасного execution boundary. Для платной разметки/admission нужны отдельное разрешение этапа, лицензии/route/identity, frozen request manifests и общий reconciled budget с unknown Stage 0 расходов. Научный пилот/E0 требует реальных D1–D4 и независимого human reference после отмены deferral; окончательная freeze G2 включает E0, power, sample sizes, criteria/procedures, splits, cohort и общий бюджет. H5/H7 дополнительно требуют feasibility continuation/cancellation и измеренного billing; G3/G4 остаются позже.
