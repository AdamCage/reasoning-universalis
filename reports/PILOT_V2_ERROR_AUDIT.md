# Диагностический аудит ответов pilot v2

Проверены 48 reference certificates и 192 ответов/диагностик из 192 строк. Primary gradeable: 97; записанных primary ошибок: 4.

Расхождений с сохранёнными labels/eligibility: 0. Labels исходного коллектора не изменялись; length и missing не превращались в неверные ответы.

Парсер ANSWER и проверки арифметики, доступных DAG-узлов и grid moves написаны отдельно. Все certificates проверены frozen независимыми Fraction/exhaustive/layer/replay алгоритмами. Это программная диагностика, не человеческая разметка, review или E0.

Машинный артефакт: `artifacts/pilot-v2-recovery-2026-11-08/error-audit.json`. Checker SHA-256: `323c7ba711fd0e88fc63820a662070fa8c41bfb413b4e2c059e3707248bb3d19`; frozen reference checker source: `fc3c355ab3a58fd9bf2d8b35e4770bcf8a2126184436c55b3b13ca61b29f1a37`.

| Task | Model/provider | Cap | Независимая причина |
|---|---|---:|---|
| pilot-v2-development-v1:dd8cd65b58ccdbe13c32dd2f:v1 | openai/gpt-oss-20b / AkashML | 8192 | wrong_exact_integer |
| pilot-v2-development-v1:ec007f1c45bf0137cdfd3f9e:v0 | openai/gpt-oss-20b / AkashML | 8192 | wrong_exact_integer |
| pilot-v2-development-v1:ec007f1c45bf0137cdfd3f9e:v1 | openai/gpt-oss-20b / AkashML | 8192 | wrong_exact_integer |
| pilot-v2-development-v1:ee1754acce0b8631bdf5d47f:v0 | openai/gpt-oss-20b / AkashML | 8192 | plan_leaves_grid |

Полные сведения о каждой проверенной ошибке, unparseable diagnostics и certificate hashes сохранены в JSON. Научная валидность остаётся `not_assessed`, review — `not_requested`, E0 — `not_passed`.
