# Reasoning Universalis

**Этап 2 закрыт. Массовый пилот не разрешён.** Guards Stage 3 стоят на пути `stage3/pipeline.py`. Список v2 остаётся development-проверкой с утечкой ответа через семейство; дополнение v3 её снижает. E0 не пройден. Подробности: [STAGE3_PIPELINE.md](reports/STAGE3_PIPELINE.md).

Исследование того, какая часть структуры и динамики машинного рассуждения сохраняется при смене модели, а какая задаётся архитектурой, обучением, задачей и способом измерения.

EpistemeOS — ядро доказательств: протоколы, провенанс, эксперименты, статистический вывод и аудит. Корень репозитория — рабочее пространство этого исследования.

## Документы

- [RESEARCH_SPECIFICATION.md](RESEARCH_SPECIFICATION.md) — научная спецификация
- [RESEARCH_PLAN.md](RESEARCH_PLAN.md) — план работ и критерии приёмки этапов
- [literature/README.md](literature/README.md) — обзор литературы этапа 0 спецификации
- [reports/STAGE0_REPORT.md](reports/STAGE0_REPORT.md) — результаты обоих этапов 0, расходы и ограничения
- [stage0/README.md](stage0/README.md) — технический pipeline и команды воспроизведения
- [cursor_objective.md](cursor_objective.md) — рабочий бриф
- [env.example](env.example) — контракт окружения без секрета
- [AGENTS.md](AGENTS.md) — операционные правила агента

## Раскладка

- `EpistemeOS/` — пакет `epistemeos` (Python ≥ 3.11, `uv.lock`)
- `.cursor/environment.json` — установка Cursor Cloud
- `.cursor/rules/research-harness.mdc` — постоянные ограничения харнеса
- `.research/` — локальные артефакты исследования, в git не входят

## Локальный старт

```powershell
copy env.example .env
```

Ключ `ROUTERAI_API_KEY` пишется только в `.env`. Дальше:

```powershell
cd EpistemeOS
uv sync --frozen
```

## Правила агента

Cursor — единственный агентный харнес. Отдельные LLM для сегментации, анализа, рецензии и текста статьи не заводятся. Модели и эмбеддеры эксперимента вызываются через RouterAI. Подробности — в `AGENTS.md` и `.cursor/rules/research-harness.mdc`.

## Cursor Cloud

Установка выполняется `bash .cursor/install.sh` из `.cursor/environment.json`. Секрет `ROUTERAI_API_KEY` задаётся во вкладке секретов Cursor Cloud. При старте агента `.cursor/start.sh` собирает из него и из `env.example` локальный `.env`; этот файл в git не попадает.

## Статус

Ревью после PR #8: guards подключены к `stage3/pipeline.py`, контекстный эмбеддинг сверяется по полному входу. Список v2 сохраняет семейную утечку (always-UNSAT 66%). Дополнение v3 — [PILOT_SECTION_5_5_ROSTER_V3.json](design/PILOT_SECTION_5_5_ROSTER_V3.json). Допуск двух новых моделей, E0 и массовый прогон не выполнены.

Этап 2 принят 18 октября 2026: [приёмка](reports/STAGE2_ACCEPTANCE.md), [матрица реализации](reports/STAGE2_REPORT.md), [воспроизведение](stage2/README.md). Standalone DomainPack прошёл kernel workflow на 6 реальных исторических GPT-OSS трассах.

Stage 1: G1 утверждён AdamCage 14 октября 2026 для v1.1, commit `68fc12d`. [Текущая приёмка](reports/STAGE1_ACCEPTANCE.md), [исторический review report](reports/STAGE1_REPORT.md), [preregistration утверждённого пакета](design/PREREGISTRATION_DRAFT.md). Новые вызовы моделей не выполнялись; E0 не пройден, G2 не заморожен.

12 октября 2026 технический Этап 0 выполнен: пробы шести кандидатов и двух эмбеддеров, сохранённые ответы, прогон GPT-OSS-20B на шести задачах (6/6), сегментация и оба эмбеддера. Qwen3-8B недоступен, предложена отдельная замена Qwen3-14B. Литературный Этап 0 принят пользователем по полному препринту Levy с ограничением «журнальная версия не проверена». Подробности — в [отчёте](reports/STAGE0_REPORT.md).

Основное исследование ждёт расширенного научного пилота и замороженного протокола. Технический прогон не заменяет пилот §5.5 и не подтверждает гипотезы.
