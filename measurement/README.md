# Измерительный pipeline: development v0.1

Stdlib Python ≥ 3.11, без LLM-разметчиков и сетевых вызовов. Это самостоятельный development-код, не зарегистрированный DomainPack и не научно валидированный измеритель. Наблюдаемые роли нельзя интерпретировать как внутренние состояния модели.

## Интерфейс

```powershell
python -m unittest discover -s tests -v
python -m measurement.demo
python -m measurement.cli --tasks tasks.json --traces traces.json --output measured.json --methods S1 S2 S3 --block-size 64
```

`tasks.json` — список объектов `task_id`, `root_id`, `domain`, `generator_id`, `prompt`. Все варианты общего root остаются вместе. Просмотренные исторические задачи имеют `previously_observed: true`, `forced_split: development`. Доли buckets 60/20/20 и seed заданы как development-дизайн, не расчёт мощности. При отсутствии подтверждённого происхождения задача не импортируется в holdout.

`traces.json` — список с `trace_id`, `task_id`, `root_id`, `family`, `model_id`, `visible_reasoning`, `raw_response_path`, `raw_response_sha256`. Путь относительно файла traces или абсолютный; raw — сохранённый Stage 0 envelope с HTTP status и JSON. Импорт проверяет hash и точное соответствие явному reasoning успешного ответа той же модели; итоговый ответ не становится reasoning. Сохранённый исходник не изменяется. Повторная raw-генерация не считается независимой репликацией.

S1 требует `semantic_boundaries`: внутренние границы, поставленные человеком по протоколу; отдельный LLM не используется. S2 — детерминированные границы предложений с защитой fenced/inline code, dollar-delimited формул, нумерации, десятичных чисел и ряда сокращений. Это ограниченная эвристика; другие математические delimiters, языки и сокращения требуют E0, не гарантируются. S3 требует `token_map` с `text_sha256`, `tokenizer_id`, `tokenizer_revision`, `offsets` в Unicode code points. Внешний подтверждённый tokenizer должен покрывать весь non-whitespace текст без перекрытия. Special/zero-width offsets и перекрывающиеся byte-fallback spans нужно отдельно обработать до импорта, не менять число токенов молча. Карта без доказанной revision не подтверждает истинность tokenizer только потому, что проходит форму. При её отсутствии S3 отклоняется; S1/S2 помечают token alignment unavailable. Regex-слова не называются токенами модели. 64 — development-параметр примера, не выбранный научный размер блока.

Сегменты сохраняют точный текст, char/token intervals, позицию, длину, версию/конфигурацию, parent trace/raw hashes и стабильный ID. `relative_progress` ретроспективен и **запрещён для online stopping**. `previous_context` содержит только два предыдущих сегмента текущей трассы, до 1000 символов. Разные трейсы не сшиваются.

TF-IDF nearest-centroid baseline: `measurement.lexical.LexicalBaseline.fit(rows, manifest, heldout_families)`; строки содержат task/root/segment IDs, family, split, text и человеческий `role` из протокола. Функция проверяет manifest digest, development split и исключённые семьи. Vocabulary/IDF/центроиды не переобучаются при predict. Запрещено скрывать происхождение обучающих меток: результаты тестовых fixtures не являются человеческой разметкой или E0. Baseline использует только текст, а длина/позиция — отдельные будущие сравнения.

`measurement.evaluation` вычисляет confusion, macro-F1 восьми ролей, recall, ambiguous fraction, root-bootstrap CI, boundary-F1 и Cohen kappa до adjudication. При вырожденном согласии или недостатке roots выдаёт неопределённость; метрики не присваивают scientific approval. Coverage, strata, paraphrase/style drops и отрицательные контроли E0 требуют реальной оценочной выборки.

`paired_embeddings` выбирает общие допущенные segment IDs для обеих систем; полная Qwen-выборка против неполной BGE запрещена. Допуск/identity flags должны приходить из проверенного журнала, а не выставляться ради полного пересечения. Нет автоматического восстановления 35 спорных исторических векторов.

## Границы готовности

Реализованы offline импорт, offsets, три интерфейса сегментации, training-only lexical baseline, task grouping и описательные метрики. Не выполнены человеческая разметка, валидация S1/S2/S3, получение реальных tokenizer maps, генераторы/верификаторы четырёх доменов, embedding collector научного pipeline, кластеризация/PCA/TICA/VAMP, DomainPack-контракт §13.8, допуск длинных повторных трасс и human gates. Существование этого кода и зелёные тесты не закрывают весь этап 2.
