# Разделение данных v0.1

Схема предназначена для development; финальный объём определяется мощностью и G2. `measurement.core.split_manifest` создаёт настоящий JSON-манифест из списка задач, без выдуманного будущего корпуса.

Каждая задача содержит `task_id`, `root_id`, `domain`, `generator_id`, точное условие `prompt`. Root объединяет исходный экземпляр, переводы, перефразы, варианты шаблона, исходные задачи и производные с тем же решением/структурой. Параметризованные задачи с общей скрытой структурой группируются консервативно по шаблону/семейству экземпляров, если возможна утечка. Неизвестное происхождение отправляется в карантин до ручного разрешения; новый ID сам по себе не создаёт независимость.

Назначение по SHA-256 `[seed,root_id]`: 60% buckets development, 20% measurement-validation, 20% confirmatory. Это целевые доли hash buckets, не гарантия точных долей или размера каждой страты. Seed `measurement-development-v1` записывается до открытия корпуса. Переставлять seed ради удачного баланса после просмотра результатов нельзя. Баланс доменов/сложности/семейств проверяется до вычисления outcomes; если недостаточен, новую схему регистрировать до доступа к закрытой части.

Задачи Stage 0 и уже просмотренные задачи всегда development-only: `previously_observed=true`, `forced_split=development`. Функция отклоняет попытку оставить такую задачу в holdout. Для всех вариантов одного root exclusion-флаги совпадают. Резерв новых генераторов задаётся отдельным заранее зарегистрированным манифестом после G2; текущая функция не изображает это реализованной независимой репликацией.

Ни одна повторная генерация или модель не меняет task split. Совместная матрица обобщения:

| Проверка | Обучение | Оценка |
|---|---|---|
| Новая семья, знакомые задачи | development roots, остальные семьи | те же roots, отложенная семья; маркировка «знакомые задачи» |
| Новые задачи, знакомые семьи | development roots | закрытые validation/test roots, обучающие семьи |
| Новая семья и новые задачи | development roots, остальные семьи | закрытые roots и отложенная семья |
| Новый генератор | разрешённые генераторы | отдельно зарезервированный генератор и новые roots |

Для выбора алгоритма применяются nested grouped folds внутри development. Все сегменты, повторные генерации, варианты и измерительные конфигурации root принадлежат одному fold. Отложенная семья не участвует в vocabulary, IDF, PCA, центроидах, выборе кластеров, выравнивании или порогов. Для каждой leave-one-family-out проверки своя fit revision и её provenance. После настройки measurement-validation используется один раз; confirmatory остаётся закрытой до G2 и валидного E0.

Манифест включает точные hashes условий, task-set digest и собственный digest. Порядок входных задач не меняет результат. Повторный ID, одинаковое нормализованное условие у разных roots и конфликт provenance отклоняются. Это ловит точные дубликаты, но не доказывает отсутствие семантических near duplicates: до импорта нужна человеческая проверка происхождения. Машинный запрет fit не заменяет разграничения файлов/доступа к закрытым данным.

## Stage 1 v1: exposure, freeze и E0

Действующий scientific дизайн следует `STATE_DISCOVERY.md`; прежняя hash-allocation функция — только development-прототип. Она не выделяет автоматически новую модельную семью, новый генератор или независимый validation corpus. На Stage 1 реальный manifest остаётся `historical-development-manifest.json`: **шесть roots, все development**. Даже если новая машина не видела их текста, historical exposure сохраняется. Параметризованные варианты одной структуры и перевод не добавляют независимых roots; задания, увиденные в admission/probes/разработке, становятся development-only вместе со всеми вариантами.

Будущий frozen split manifest хранит task/root IDs, exact prompt и verifier digests, generator/version/lineage, difficulty definition, observed/exposure history, split/role, family assignment отдельно, task-set digest, allocation revision/seed, quarantine reason, seal/access policy и audit. Dataset identity вычисляется без metric/method/contrast, task-set identity не меняется от анализа. Semantic near-duplicate/provenance review проводится до закрытия; человеческая проверка происхождения не заменяется простым hash и сейчас не считается выполненной. При последующем раскрытии родства roots новые связи и нарушения фиксируются, результаты затронутых contrasts остаются unusable до решения, без удаления старых manifests.

| Набор | Доступ и назначение | Что не разрешает |
|---|---|---|
| Development/pilot | Настройка генераторов, сегментации, измерителя, K, mapping, policies и power | Называть эти roots независимой подтверждающей выборкой |
| Measurement-validation | После freeze выбранного измерителя и критериев E0, только назначенной проверке; новые roots | Повторную настройку и повторную приёмку на тех же roots |
| Confirmatory | Закрыт разработчику; открывается после G2 и принятого независимого E0 | Выбор порогов, числа состояний, N, baseline или policy по результатам |
| New-generator replication | Отдельно запечатанные новый generator lineage × новые roots; fixed protocol | Называть rerun/re-prefill независимой new-data репликацией |

Exposure log должен фиксировать actor, action, time, artifact/root digest, цель и фактический доступ. Один OS user облачной среды и `uv_locked_python_v2` **не обеспечивают** изоляцию. Будущие закрытые данные требуют отдельного хранителя и проверенной границы доступа; нынешний документ не создаёт её. Metadata manifests без gold можно открыть разработчику только если они не раскрывают тестовые тексты/ответы. Нарушение seal/exposure закрывает affected confirmatory contrast и требует новый независимый набор, а не нового filename.

После первого доступа к measurement-validation revision метода/ontology/prompt/schema/K/alignment/segmentation/threshold требует свежих ранее закрытых roots и новой validation revision. Старый отрицательный E0 не стирается. Confirmatory никогда не становится tuning data; amendment после exposure получает exploratory статус для старых данных и новый protocol/new data для будущего подтверждения.

Для основного анализа generalization target — новая семья × новые roots; три остальных клетки (новая семья/знакомые tasks, новые tasks/знакомая семья, новый generator) показываются раздельно. Leave-one-family-out использует fold-specific ontology/fit: запрещено сначала обучить общий mapping на всех семьях и потом объявить одну held out. Все prefixes/annotation panels/measurements root остаются вместе; calibration политики H7 также root-disjoint от её оценки, выбирается только на development, без future-token features.

## Независимая E0-валидация пока отложена

`E0_PRELIMINARY.json` сохраняется без смены targets. Это development-триаж, не acceptance и не power для H. Future E0 требует результатов всех шести пунктов §10: synthetic known phases, точность границ, восстановление состояний, paraphrase, style/length robustness и random-sequence false-universality control. Coverage относится к roots/ролям/семьям/доменам и полным trajectories; редкие роли oversampled отдельно от natural frequencies. Восемь исходных ролей оцениваются по исходной человеческой онтологии, а cluster-first states — отдельной таблицей mapping/coverage: удалять редкую роль ради macro-F1 запрещено.

Human validation требует возобновления отложенной пользователем работы, независимых двух аннотаторов и сохранённых pre-adjudication labels по `ANNOTATION_PROTOCOL.md`, затем решения расхождений и оценки ошибки. Until then human kappa/macro-F1 — **not evaluated**, согласие DeepSeek — только machine agreement. При разработке метода final E0 quality thresholds фиксируются **до** открытия его независимой validation; G2 впоследствии включает эти revision/results и scientific thresholds. Deferral не отменяет зависимость: без human reference и успешного E0 интерпретация H1–H7 и основного корпуса заблокирована.
