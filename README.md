# Reasoning Universalis

Исследование того, какая часть структуры и динамики машинного рассуждения сохраняется при смене модели, а какая задаётся архитектурой, обучением, задачей и способом измерения.

EpistemeOS — ядро доказательств: протоколы, провенанс, эксперименты, статистический вывод и аудит. Корень репозитория — рабочее пространство этого исследования.

## Документы

- [RESEARCH_SPECIFICATION.md](RESEARCH_SPECIFICATION.md) — научная спецификация
- [RESEARCH_PLAN.md](RESEARCH_PLAN.md) — план работ и критерии приёмки этапов
- [literature/README.md](literature/README.md) — обзор литературы этапа 0 спецификации
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

Установка выполняется командой из `.cursor/environment.json`. Секрет `ROUTERAI_API_KEY` задаётся во вкладке секретов Cursor Cloud и в git не попадает.

## Статус

Этап 0 не запускался: пробы шести моделей и двух эмбеддеров, сырые ответы и пилот на 5–10 задач ещё впереди. Основное исследование не начинается, пока пилот не завершён и протокол не заморожен.
