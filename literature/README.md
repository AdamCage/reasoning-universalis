# Обзор литературы этапа 0 спецификации

**Статус: Этап 0 спецификации принят 12 октября 2026 с утверждённым пользователем ограничением: журнальная версия Levy не проверена.**

Пользователь разрешил закрыть чтение Levy по полному препринту arXiv:2512.12777v1. Это уточнение критерия доступа к источнику записано в `RESEARCH_PLAN.md`; содержание гипотез сохранено. Поля, взятые из препринта, не приписываются журнальному тексту. Историческое состояние обзора и попытки доступа 11 октября ниже сохранены; фразы «приёмка не объявляется» в них описывают состояние до этого решения. Повторная проверка 12 октября: Nature HTML и PDF снова требуют авторизацию, открытого журнального тела не найдено. [Отчёт приёмки](../reports/STAGE0_REPORT.md).

Дата доступа к источникам: 11 октября 2026. Гипотезы не подтверждаются этим обзором. Источник гипотез — [RESEARCH_SPECIFICATION.md](../RESEARCH_SPECIFICATION.md), §3, §4, §15 и §21 (Task 1). Текст H0–H7 в этом обзоре не изменялся.

Приёмка не объявляется. Полный текст журнальной статьи Levy et al. по-прежнему не прочитан. Публичная страница Nature отдаёт аннотацию, метаданные, подпись Fig. 1 и список литературы и прямо называет дальнейшее содержимое превью подписки. PDF без логина уходит на авторизацию издателя. Ни Unpaywall, ни репозиторные API, ни страницы авторов не дали документ, который страница журнала называет версией статьи. Подробное чтение этой работы остаётся препринтом arXiv:2512.12777. Поля, которых нет в прочитанном тексте, не заполнялись догадкой. Журнал попыток — в секции ниже.

Остальные семь работ §4.1 прочитаны по первичному тексту. Пункты §4.2 прочитаны по указанным ниже первичным страницам и документам. RouterAI не вызывался. Модели эксперимента не вызывались.

## Что прочитано

| Работа §4.1 | Доступ | Что открыто |
|---|---|---|
| Yu et al. 2025 | открыта | arXiv HTML `2509.00190` (v2, обновление 29 января 2026), включая приложение; страница ACL Anthology |
| Wu et al. 2026 | открыта | arXiv HTML `2507.08182` (v2, обновление 29 января 2026), включая приложения |
| Shahariar et al. 2026 | открыта | arXiv HTML `2510.22437` (v2, обновление 28 мая 2026), включая приложения |
| Arcuschin et al. 2026 | открыта | arXiv HTML `2503.08679` (v6, обновление 16 июня 2026), включая приложения |
| Levy et al. 2026 | страница журнала открыта частично; полный текст журнала не получен | публичная HTML-страница Nature (аннотация, подпись Fig. 1, список литературы, превью подписки); полный препринт arXiv HTML `2512.12777` v1. Журнальный текст после аннотации не прочитан |
| Caldarella et al. 2026 | открыта | arXiv HTML `2606.02835` (v1, 1 июня 2026), включая приложения |
| OpenAI 2025 | открыта | страница `https://openai.com/index/chain-of-thought-monitoring/` |
| OpenAI 2026 | открыта | страница `https://openai.com/index/evaluating-chain-of-thought-monitorability/` и статья, на которую страница отсылает: arXiv HTML `2512.18311` |

## Что не удалось открыть

- Полный текст *Nature Machine Intelligence* для Levy et al. Журнал попыток ниже. Страница журнала не называет препринт arXiv:2512.12777 версией статьи. Приёмка по одному препринту не объявляется.
- Отдельные страницы PMLR для Wu, Shahariar и Arcuschin не подменяют собой прочитанный arXiv HTML. Идентификаторы площадок взяты из спецификации и из шапок прочитанных версий. Повторная проверка 11 октября 2026: эти три страницы открываются и несут те же названия, что в §4.1.

## Журнал попыток доступа к полному тексту Levy et al.

Дата всех строк: 11 октября 2026. Искали в порядке: страница Nature и её HTML, PDF без логина, Unpaywall, OpenAlex, Semantic Scholar, PubMed Central, Europe PMC, OpenAIRE, страницы авторов и их ссылка на рукопись, все версии arXiv. Чужие учётные данные не использовались. Пейволл не обходился.

| URL | Что вернулось |
|---|---|
| https://www.nature.com/articles/s42256-026-01303-y | HTML страницы статьи. Публично: Perspective; получена 22 декабря 2025; принята 20 августа 2026; опубликована 7 октября 2026; version of record 7 октября 2026; DOI `10.1038/s42256-026-01303-y`. Аннотация, подпись Fig. 1 («Illustration of token generation across cycles 0, 1, …, n, where the final answer is produced in the last cycle»), список литературы, аффилиации, contributions, заявление об отсутствии competing interests, имена рецензентов Wenxiang Jiao и Jingcheng Niu плюс анонимные. Сразу после аннотации страница пишет: «This is a preview of subscription content, access via your institution». В данных страницы `authorization.status` равен false. Тело после аннотации не отдано. |
| https://www.nature.com/articles/s42256-026-01303-y.pdf | Без логина: HTTP 303 на `https://idp.nature.com/authorize` с `redirect_uri` на тот же PDF, затем 302. Файл статьи не получен. |
| https://api.unpaywall.org/v2/10.1038/s42256-026-01303-y | `is_oa` false, `oa_status` closed, `best_oa_location` null, `has_repository_copy` false, список `oa_locations` пуст. |
| https://api.openalex.org/works/https://doi.org/10.1038/s42256-026-01303-y | `open_access.is_oa` false, `oa_url` null, `has_fulltext` false, `pdf_url` null. Одна локация — сам DOI. |
| https://api.semanticscholar.org/graph/v1/paper/DOI:10.1038/s42256-026-01303-y | `isOpenAccess` false, `openAccessPdf.status` CLOSED. Аннотацию издатель в этом ответе скрыл. |
| https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:10.1038/s42256-026-01303-y&format=json | `hitCount` 0. |
| https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/?ids=10.1038/s42256-026-01303-y&format=json | `Identifier not found in PMC`. |
| https://api.openaire.eu/search/publications?doi=10.1038/s42256-026-01303-y&format=json | `total` 0. |
| https://api.crossref.org/works/10.1038/s42256-026-01303-y | Ссылки только на тот же HTML и PDF nature.com, `content-version` vor. Ссылки на accepted manuscript нет. |
| https://export.arxiv.org/api/query?id_list=2512.12777 и https://arxiv.org/abs/2512.12777 | Одна версия, v1, 14 декабря 2025. История подач на странице arXiv указывает размер 53 KB. В истории и в записи API нет `journal-ref` и нет пометки, что это версия журнала. Лицензия препринта на странице arXiv — CC BY 4.0. Прочитан arXiv HTML v1. Это не журнальный текст. |
| https://huggingface.co/papers/2512.12777.md и https://huggingface.co/api/papers/2512.12777 | Markdown страницы Hugging Face собран из arXiv HTML того же препринта (`URL Source: https://arxiv.org/html/2512.12777`). `publishedAt` 14 декабря 2025. В JSON API нет полей project page и GitHub. Журнальной версии там нет. |
| https://mosh0110.github.io/ | Ссылка «Paper» ведёт на https://doi.org/10.1038/s42256-026-01303-y . Файла рукописи на странице нет. |
| https://mosh0110.github.io/blog/state-over-tokens/ | Автор называет текст краткой адаптированной версией статьи, не самой статьёй. Ссылка «Full paper» — тот же DOI. Журнальный текст на странице не размещён. Блог не использовался как источник полей таблицы. |
| https://shauli-ravfogel.netlify.app/ | В HTML страницы ссылки на эту статью нет. |
| https://shauli-ravfogel.netlify.app/cv/cv.pdf | Библиографическая строка: State over Tokens, Nature Machine Intelligence, 2026. Среди ссылок PDF есть https://arxiv.org/abs/2512.12777 . URL accepted manuscript и DOI журнала в извлечённых ссылках PDF не найдены. |
| https://u.cs.biu.ac.il/~yogo/ | Страница Yoav Goldberg не ссылается на эту статью и не содержит файла рукописи. |

## Состав каталога

- [comparative-table.md](comparative-table.md) — поля §4.3 по каждой работе §4.1.
- [novelty-memo.md](novelty-memo.md) — ответ относительно Yu et al. и Shahariar et al.
- [methods-reading.md](methods-reading.md) — чтение пунктов §4.2.

Каталог записей литературы внутри EpistemeOS — это журнал событий ядра, а не место этого обзора. Исходники EpistemeOS не изменялись.
