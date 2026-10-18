# Stage 2 — приёмка измерительного pipeline

18 октября 2026. **Этап 2 спецификации принят** по всем пятнадцати критериям §8 `RESEARCH_PLAN.md`. Принят измерительный путь от задачи и сохранённого запуска до сегмента, представления и проверяемой тестовой метрики. Научный результат H0–H7 этой записью не устанавливается.

Основание закрытия — прямое поручение владельца репозитория завершить этап 2. Проверка выполнена повторно на неизменном implementation payload. Это не контрольная точка G2 и не прохождение E0.

Receipt: [STAGE2_ACCEPTANCE.json](STAGE2_ACCEPTANCE.json), SHA-256 `47fcab3c254f1229f87abcb6fa777c2c72d73a5726eb5bd1d0b8e7dad547a287`.

Implementation payload остаётся коммитом `62b9cd5c1ecad8ee6711cc354c25fa8ea67ce07f`. Его manifest — [STAGE2_MANIFEST.json](STAGE2_MANIFEST.json), payload SHA-256 `03932e8f90dd3a8fa1b7d22a42c1cd0527585e70a158a6f1fb6decba39e0dab8`. Внутренний статус этого payload по-прежнему `implementation_ready_for_review_not_E0`: историческая матрица [STAGE2_REPORT.md](STAGE2_REPORT.md) не переписывалась. Приёмка лежит в этом receipt, вне payload.

Утверждённый дизайн G1 v1.1 остаётся snapshot `68fc12da05000674e3d770a07e449c37a4fbc119`, payload `04988a3ec82db073a04a71519e35f91740398d9a66636dc2935ce3377c079963`.

## Что повторно проверено

- Корневой suite до добавления guards приёмки: **61/61**. После guards приёмки тот же прогон даёт **65/65** (`python3 -m unittest discover -s tests -v`).
- EpistemeOS: **711 tests, 1 skipped**, остальные прошли (`uv run python -m unittest discover -s tests -v` из `EpistemeOS`). Пропущен opt-in Docker test. Docker isolation не объявлена проверенной.
- `python3 -m stage2.evidence --verify evidence/stage2-2026-10-14.zip`: integrity verified, 6 attempts, 144 segments (S1=10, S2=95, S3=39), provenance chain verified, `scientific_validity=not_assessed`, network calls 0.
- SHA-256 архива `74b0f24a80955af6475831532db83b62b79b671413aba3ca2b12d4686b4327fe`, 484814 bytes.
- `python3 design/verify_stage1.py --commit 68fc12da05000674e3d770a07e449c37a4fbc119` подтвердил неизменный пакет G1. Verifier по-прежнему возвращает `pending_in_review_snapshot` для исторического review snapshot; текущий G1 читается из `design/G1.json`.
- `RESEARCH_SPECIFICATION.md`, исходники, тесты, `README.md` и `AGENTS.md` внутри `EpistemeOS` не изменены. Новых вызовов RouterAI нет.

Проверка самой приёмки:

```bash
python3 design/verify_stage2_acceptance.py
```

## Пятнадцать критериев §8

| № | Критерий | Где выполнен |
|---|---|---|
| 1 | Генераторы и независимые верификаторы D1–D4 | `stage2/datasets.py`; тест четырёх доменов, отрицательных и неразборчивых ответов |
| 2 | Группы Identity, Inference, Raw observations, Outcome, Provenance | `stage2/observations.py` |
| 3 | Ошибка парсера оставляет сырой ответ | CAS до разбора; тест сломанного JSON |
| 4 | Ошибки, повторы, обрывы и неудачи остаются | статусы `failed` и `incomplete` сохраняются в inventory и в `details` анализа |
| 5 | Отдельные S1, S2 и S3 | operation-cue heuristic, protected sentences, fixed ResearchBPE blocks размера 64 |
| 6 | Текст, границы, интервалы токенов, позиция, прогресс, длина, версия | поля сегмента; интервалы ResearchBPE, не tokenizer генератора |
| 7 | Нет перехода между разными траекториями | `transitions` и тест двух трасс |
| 8 | Только BGE-M3 и Qwen3-Embedding-8B; лексический baseline без LLM | `EmbeddingAdapter` и training-only TF-IDF |
| 9 | Local и Contextual — разные конфигурации | отдельные inputs, hashes и 190 лексических строк на 95 сегментах S2 |
| 10 | Реальная трасса и путь метрики | 6 исторических трасс GPT-OSS-20B; `provenance-chain.json` внутри evidence ZIP |
| 11 | Самостоятельный `reasoning_universalis_v1`; `risen_universalis_v1` остаётся smoke | kernel workflow и тест старых pack |
| 12 | Раздельные digest датасета, задачи, множества задач, split, метода, протокола, запуска и сырого ответа | `inventory.verify` |
| 13 | Все свойства §13.8 | `tests/test_stage2_pack.py` и regression suite ядра |
| 14 | Протокол ролей: определения, примеры, ambiguous/other, разрешение расхождений, согласие, журнал версий | `design/ANNOTATION_PROTOCOL.md`. Доля двойной разметки основного корпуса и численный порог согласия отложены до этапа 4. Majority 3/5 и предварительные цели E0 остаются engineering-кандидатами |
| 15 | Лицензия и полная трасса этапа 0 для живой модели | `openai/gpt-oss-20b`, Apache-2.0, полная трасса этапа 0, нового живого вызова нет. `nvidia/nemotron-3-nano-30b-a3b` не вызывался; лицензия — NVIDIA Nemotron Open Model License |

S1 измеряет смену явного маркера операции и не является валидированным восстановлением смысловых шагов. S3 использует исследовательский BPE и блок 64 как параметр development, не как научный порог. Оба ограничения уже записаны в payload и не мешают технической приёмке этапа 2: ошибку измерителя оценивает E0.

`AGENTS.md`, `RESEARCH_PLAN.md` и `STAGE1_CLOUD_HANDOFF.md` входят в утверждённый пакет G1 и оставлены байт-в-байт. Фразы о следующем задании этапа 1 внутри них — исторический текст snapshot `68fc12d`. Действующий статус записан здесь и в `README.md`.

## Что эта приёмка не открывает

E0 **не пройден**. Независимая человеческая валидация остаётся отложенной. Согласие DeepSeek-ансамбля не становится человеческим эталоном. G2 не заморожен, G3 и G4 не выполнены. Этап 3, пилот §5.5, не начат. Платный ансамбль, новая когорта и основной корпус требуют отдельного разрешения и сверенного бюджета.

Claim DomainPack остаётся `exploratory/inconclusive`, `scientific_validity=not_assessed`. Шесть исторических roots остаются development-only.
