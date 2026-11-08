# Машинная development-разметка наблюдаемого текста

Фиксировано 200 S2 items на 24 root blocks; максимум 2100 primary/conditional/audit slots. Новых задач или человеческих ответов этот отчёт не создаёт.

Это один multiseed DeepSeek/BytePlus измеритель. Его согласие не является точностью, human gold, независимой репликацией или E0 pass.

| Primary status | Items / all planned |
|---|---:|
| ambiguous_unresolved | 2 / 200 |
| resolved | 180 / 200 |
| resolved_ambiguous | 15 / 200 |
| technical_unresolved | 3 / 200 |

| Machine consensus role | Items / all planned |
|---|---:|
| problem_formulation | 17 / 200 |
| planning | 26 / 200 |
| deduction_computation | 93 / 200 |
| exploration | 6 / 200 |
| verification | 18 / 200 |
| uncertainty | 7 / 200 |
| backtracking_correction | 1 / 200 |
| conclusion | 12 / 200 |
| ambiguous_other | 15 / 200 |

| Phase | Planned | Technical status counts |
|---|---:|---|
| round1 | 1000 | {"invalid": 6, "valid": 994} |
| round2 | 1000 | {"not_scheduled_by_fixed_condition": 975, "valid": 25} |
| audit | 100 | {"valid": 100} |

Второй semantic раунд разрешён только после пяти технически valid голосов без majority. Неполная панель не повторяется семантически; результаты раундов не объединяются. Все ненужные conditional и заблокированные audit slots остаются в знаменателях. Audit сравнивает исходный round1 с одним повтором тех же seeds и никогда не исправляет primary consensus.

Общий ledger: 2038.3174633704220 RUB charged-or-reserved; reported cost 61.0338606323081489197 RUB, резерв сверх reported 1772.3752250166326510803 RUB; без reported cost удерживается 204.9083777214812 RUB. Все 984 старые строки сохранены. Это не окончательный биллинг.

JSON сохраняет per-role counts, entropy, полные/неполные панели, same-model Cohen/Fleiss agreement и описательный task-root bootstrap с явными undefined случаями. Source-generator/domain/tier/length/root strata не означают естественную распространённость ролей. DeepSeek source-generator отдельно виден для generator=annotator bias.

Relative position — только retrospective координата в уже наблюдённой полной текстовой записи, не online feature; она не передавалась разметчику. Выбранные S2 segments разрежены: transitions/dwell здесь не оцениваются. Сравнение raw response SHA включает API-envelope поля; отличие hash само по себе не означает изменение роли.

Reasoning запрошен disabled; returned-reasoning flag присутствует у 0 votes. Для роли читался только завершённый content JSON. Эффективный внутренний режим не подтверждён независимо. Transport unknown и отсутствие reported billing учитываются раздельно.

E0 не пройден, human reference отложен, human gold не создан. Функциональная онтология и machine consensus не подтверждают H0–H7, stopping policy, научный review или будущий detector. Новый N/test не выбран. Этот consumer не выполняет API-запросов.
