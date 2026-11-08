# Reasoning Universalis

**Development-пилот v2 начат 8 ноября.** [Фиксированный протокол](design/PILOT_V2_PROTOCOL_2026_11_08.json), [статистический план](design/PILOT_V2_STATISTICAL_PLAN.md), [ход работы](reports/PILOT_V2_SESSION.md). Проверяется поддержка завершённых ошибочных и верных решений на новых development-roots при раздельных уровнях сложности и лимитах генерации. V1 ниже сохраняется как закрытый результат; E0 не пройден.

**8 ноября 2026: локальный ограниченный пилот завершён.** Сохранены 384 основные попытки, 333 оцениваемых ответа и четыре ошибки; BGE-M3 и Qwen embedding покрывают по 5778 chunks. Основной вопрос о предсказании ошибок остался неразрешённым из-за нехватки классов. [Результат и ограничения](reports/LOCAL_RESEARCH_RESULT_RU.md), [английская рукопись](manuscript/LOCAL_RESEARCH_PAPER.md), [PDF](output/pdf/local-reasoning-pilot.pdf), [evidence sheet](output/pdf/portfolio-evidence-sheet.pdf). E0 не пройден; H0–H7 не подтверждены.

Платный сбор закрыт. Консервативный charged-or-reserved итог — 651.51803 RUB из разрешённых 3000 RUB, включая исторические обязательства; это не измеренная фактическая оплата. Переносимый архив находится в `evidence/local-pilot-2026-11-08/manifest.json`; [бесплатный offline replay](reports/LOCAL_REPRODUCTION_CHECK.md) восстанавливает исходные bytes и повторяет пять анализов без API. Команды и статус для продолжения — [LOCAL_RESUME.md](LOCAL_RESUME.md).

Состояние предыдущих этапов ниже сохранено для истории. Текущие границы и авторизация — [resumption scope](reports/RESUMPTION_SCOPE_2026_11_08.md); исходные H0–H7 не изменены.

**Этап 3 подготовлен офлайн и не запущен.** Конвейер резервирует ledger до отправки, но оплачиваемый допуск Qwen3-32B и DeepSeek-V4.1-Flash не выполнен. E0 не пройден. План до первого вызова: [STAGE3_PRE_DISPATCH.md](reports/STAGE3_PRE_DISPATCH.md).

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

Текущее поручение разрешает Codex и программных помощников; исторические ограничения сохранены в [AGENTS.md](AGENTS.md) с пояснением приоритета. Все экспериментальные модельные вызовы учитываются через RouterAI. Секреты и `.env` не публикуются.

## Cursor Cloud

Установка выполняется `bash .cursor/install.sh` из `.cursor/environment.json`. Секрет `ROUTERAI_API_KEY` задаётся во вкладке секретов Cursor Cloud. При старте агента `.cursor/start.sh` собирает из него и из `env.example` локальный `.env`; этот файл в git не попадает.

## Статус

Ревью после PR #8: guards подключены к `stage3/pipeline.py`, контекстный эмбеддинг сверяется по полному входу. Список v2 сохраняет семейную утечку (always-UNSAT 66%). Дополнение v3 — [PILOT_SECTION_5_5_ROSTER_V3.json](design/PILOT_SECTION_5_5_ROSTER_V3.json). Допуск двух новых моделей, E0 и массовый прогон не выполнены.

Этап 2 принят 18 октября 2026: [приёмка](reports/STAGE2_ACCEPTANCE.md), [матрица реализации](reports/STAGE2_REPORT.md), [воспроизведение](stage2/README.md). Standalone DomainPack прошёл kernel workflow на 6 реальных исторических GPT-OSS трассах.

Stage 1: G1 утверждён AdamCage 14 октября 2026 для v1.1, commit `68fc12d`. [Текущая приёмка](reports/STAGE1_ACCEPTANCE.md), [исторический review report](reports/STAGE1_REPORT.md), [preregistration утверждённого пакета](design/PREREGISTRATION_DRAFT.md). Новые вызовы моделей не выполнялись; E0 не пройден, G2 не заморожен.

12 октября 2026 технический Этап 0 выполнен: пробы шести кандидатов и двух эмбеддеров, сохранённые ответы, прогон GPT-OSS-20B на шести задачах (6/6), сегментация и оба эмбеддера. Qwen3-8B недоступен, предложена отдельная замена Qwen3-14B. Литературный Этап 0 принят пользователем по полному препринту Levy с ограничением «журнальная версия не проверена». Подробности — в [отчёте](reports/STAGE0_REPORT.md).

Основное исследование ждёт расширенного научного пилота и замороженного протокола. Технический прогон не заменяет пилот §5.5 и не подтверждает гипотезы.
