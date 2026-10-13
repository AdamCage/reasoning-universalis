# STAGE2 — измерительный pipeline

Python ≥3.11, stdlib, EpistemeOS из соседнего каталога. Рабочая реализация Stage 2 поверх утверждённого G1 v1.1; научный пилот, E0 и H0–H7 здесь не выполняются. Новых LLM-агентов нет. Исторический пакет G1 и исходники/тесты ядра сохранены.

## Воспроизведение без ключа и сети

Из корня, в новый каталог:

```bash
python3 -m unittest discover -s tests -v
python3 -m stage2.episteme_bridge --output .research/stage2-replay
python3 -m stage2.evidence --verify evidence/stage2-2026-10-14.zip
```

`episteme_bridge` явно добавляет `reasoning_universalis_v1` в allowlist текущего процесса и использует настоящие `pack.preregister`, batch execution, reanalysis, `pack.analyse` и assignment. Встроенный registry EpistemeOS не редактируется; обычный CLI без этой обёртки не знает внешний пакет. Полный pack code pin фиксируется ядром. Captured source и CAS проверяют исходные байты против опубликованного Stage 0 manifest с известным SHA-256, а не доверяют выставленным caller флагам.

Экспорт нового воспроизведения:

```bash
python3 -m stage2.evidence --export evidence/stage2-replay.zip --workspace .research/stage2-replay
```

Пакет содержит exact captured observations, origin manifest, provenance chain, code, kernel backup и manifest hashes. Backup сохраняет события; импорт/restore не превращает старый inference в fresh replication. ZIP exporter отказывается переписывать существующий файл. Пример использует шесть **реальных исторических** GPT-OSS трасс и 12 новых offline primary/reanalysis slots. Это не новые оплачиваемые генерации и не пилот §5.5.

## Компоненты

- `datasets.py`: D1 арифметика с независимым умножением; D2 CNF с exhaustive truth-table verifier; D3 lexicographic topological order с exhaustive reference; D4 planning с перебором и симуляцией действий. Три solver-based difficulty strata, сохранённый seed и conservative structural-template roots. Генерации исключительно development-only, без инструментов модели или eval/exec ответа.
- `observations.py`: immutable content-addressed bytes до parsing, отдельно записи всех failed/incomplete/unknown попыток, пять групп §6.2, independent dataset/task/task-set/split/method/protocol/run/raw identities. Secret reflection редактируется до сохранения с marker; historical envelopes не переименовываются в original HTTP bytes.
- `segmentation.py`: S1 operation-cue semantic-step heuristic без назначения функциональных ролей; отдельно принимаются человеческие boundaries. S2 защищённые предложения; S3 блоки действительных токенов явно названного анализирующего токенизатора. Exact char/token offsets, native segment IDs/config revisions, previous-only context и отдельные trajectory edges. Cross-segmentation pairing по raw traces/roots, не по incompatible IDs.
- `tokenization.py`: самостоятельно обученный на development ResearchBPE, Unicode-initial BPE с настоящими merges, revision и offsets. Это независимая **исследовательская** токенизация; generator tokenizer остаётся unknown. Не использовать её counts как model output-token billing или online budget. Подтверждённый внешний model token map можно передать интерфейсу сегментации, но нынешний исторический DomainPack проверяет названный research-BPE режим. E0 должен оценить sensitivity к tokenization.
- `representations.py`: training-only TF-IDF без role labels и адаптеры ровно BGE-M3/Qwen3-Embedding-8B, finite dimensions и identity checks, отдельные Local/Contextual provenance. Парность — одинаковые segment texts/boundaries внутри фиксированной segmentation. Лексический supervised baseline прежнего `measurement/lexical.py` сохранён отдельно, человеческого gold сейчас нет.
- `discovery.py`: cluster-first training centroids, K из конечной development grid, root-grouped и nested lexical folds с refit vocabulary/IDF в каждом fold; frozen mapping с training-root guard. Число состояний не фиксировано восьмью, до интерпретации состояния `uninterpreted`. Настоящая leave-one-family-out оценка требует нескольких admitted families и остаётся для будущего пилота; один GPT-OSS набор не объявлен такой оценкой. Nested fit проверен на fixtures и выполнен на реальных development S2 сегментах; single-family диагностика не является scientific transfer result. Local/Contextual lexical vectors и uninterpreted states сохранены в captured source.
- `annotation.py`: exact segment/cluster templates утверждённого дизайна, strict vote/quotes, пять голосов, максимум два раунда, incomplete не считается semantic disagreement. Только DeepSeek разрешён как будущий ансамбль; код не dispatch-ит платную разметку и не считает consensus человеческим gold.
- `inference.py`: RouterAI-only transport для отдельно admitted development runs, shared persisted ledger hash/lock, reservation до dispatch, durable raw journal, fail-closed model/provider/pricing, без retries. Chat generation проверяет request/response-bound full-trace admission до сети. Прежние резервы/unknown расходы не сбрасываются пустой машиной. В демонстрации transport не вызывался.
- `reasoning_universalis_v1/`: standalone contract-v1 package, только public DomainPack API/stdlib, read-only capture и pure hooks, v2 source trees/uv lock. Тестовая метрика — paired segmentation-count delta per trace, затем root; исходные bytes/task/split/method и контраст закреплены до offline анализа. Она не является метрикой H1–H7. Output всегда bounded exploratory/inconclusive без scientific approval.

S1/S2 и BPE — реализованные измерительные методы с ограниченным диапазоном поддержки, **не валидированный E0 измеритель**. Изменение метода после независимой validation потребует свежих roots. Все шесть исторических roots development-only; новые validation/confirmatory данные не создавались.

## Исполнение и дальнейшие gates

Генерация RouterAI остаётся trusted external evidence. Новые primary/reanalysis программы выполняют только offline пересчёт JSON; им не выдаётся API-ключ. `uv_locked_python_v2` и hooks — same-user процессы, не sandbox: раскрываются фактические ограничения, никаких закрытых данных этому запуску не передано. Разные actor labels не доказывают независимость авторства, контекста или ОС. Reanalysis — другая реализация того же автора, не new-data replication.

G1 approved; E0 not passed, human validation deferred, G2/G3/G4 не выполнены. Следующая научная стадия требует допущенной когорты, общего reconciled бюджета, независимого human reference после возобновления deferral и отдельного пилота/проверки мощности. Prefix probes и actual stopping не запускаются STAGE2.
