# Машинная разметка — Stage 1 v1

Дизайн для ревью; **нет разрешения на запуск RouterAI**. Пользователь выбрал единственный измеритель: multiseed ensemble `deepseek/deepseek-v4.1-flash`, 3–5 голосов и новые seeds при отсутствии большинства. Человеческая валидация отложена, **E0 не пройден**. Ни разметка, ни согласие модели не заменяют human gold или G3.

## Зафиксированная инженерная конфигурация

В `ANNOTATION_CONFIG.json`: пять голосов, majority 3/5, максимум два полных раунда; это выбранная здесь инженерная конкретизация допустимого диапазона, **не приписываемое пользователю прежнее утверждение чисел**. Она входит в предлагаемую версию G1. Seeds первого раунда `2026101201…2026101205`, второго `2026101211…2026101215`; temperature 0.7, top-p 1.0, output cap 1024, timeout 120 s, concurrency 1, automatic retries 0. Значения являются дизайном будущего измерителя, не final научными порогами §11.2. До платного исполнения отдельно проверить поддержку параметров, лицензию, provider и бюджет. Unsupported seed записать явно; seed requested не доказывает его применение. Нельзя молча переключиться на другой model, размер панели или маршрут.

Каждый голос видит один и тот же вход и определения, независимо от других ответов. Начальный role vocabulary сохраняет восемь ролей H1 плюс `ambiguous_other`; новые cluster-first states не принуждаются к этим восьми кластерам. Их mapping может быть many-to-one, mixed/unmapped. Если development обосновывает другую функциональную онтологию, создаётся новая revision/schema с таблицей соответствия исходным ролям; изменение только до независимой validation. Сохраняются отдельно cluster interpretation и segment labeling prompts, definitions hashes и тип задания.

## Вход, schema и валидность голоса

Точные шаблоны: `prompts/segment-role-v1.md`, `prompts/cluster-role-v1.md`; выход — `ANNOTATION_RESPONSE.schema.json`. Canonical serialization определён в prompts. Нельзя включать API final answer, gold, correctness, cluster role для сегмента, model/provider/family, split, future или голоса соседей. Контекст сегмента: неизменное условие без отдельного gold, текущий сегмент целиком, suffix не более 1000 code points от максимум двух предыдущих сегментов. Внешние IDs заменяются anonymous IDs в запросе с приватной таблицей provenance. Если полный текущий сегмент/представители не помещаются в подтверждённый context budget, `oversized_unresolved` без запроса; не урезать данные незаметно. Prompt/data separation и injection примеры требуют будущих offline renderer tests.

Голос допустим только при HTTP 200, отсутствии API error, совпадении admitted requested/returned model и provider, завершённом не-обрезанном ответе, strict JSON без duplicate keys/nonfinite, точном schema, совпадении item_id и дословных evidence_quotes в разрешённых source IDs. Primary не дублируется в secondary, `ambiguous_other` не используется как secondary; quotes проверяются в текущем тексте, а не в gold/контексте. Не исправлять JSON вторым LLM и не извлекать удобную метку из malformed prose. Правильная форма не доказывает правильную роль.

## Конечный автомат панели

1. Выполнить пять запланированных голосов первого раунда, сохраняя каждый dispatch до сети. При аварии процесса неизвестные попытки сохраняют резерв; resume сначала reconcile, не повторяет их. Ошибка отдельного голоса не прекращает учёт остальных запланированных голосов при доступном бюджете.
2. Если хотя бы один голос технически невалиден/неизвестен или не выполнен, результат `technical_unresolved`, панель incomplete. Семантический второй раунд запрещён: отсутствующий ответ не разногласие. Новый технический прогон только отдельной зарегистрированной попыткой после reconciliation и нового разрешённого бюджета; старая панель сохраняется.
3. Если полный первый раунд дал majority роли, сохранить consensus этого раунда. Confidence и secondary_roles не добавляют голосов. Majority `ambiguous_other` — `resolved_ambiguous`, не успешно определённая научная роль.
4. Только полный первый раунд без majority открывает второй полный раунд с другим schedule. Не сообщать его голосам первый раунд. Majority второго раунда определяет результат с `round_used=2`; первый не объединяется со вторым. Incomplete второй раунд — `technical_unresolved`; две полные панели без majority — `ambiguous_unresolved`.
5. Сохранять raw распределения обоих раундов, complete/incomplete, requested/resolved/ambiguous/unresolved denominators и долю repetitions. Post-hoc объединение 10 голосов допускается лишь как маркированная sensitivity, не смена основного результата. Unresolved не выбрасываются из dynamics и не склеивают соседние переходы.

Одна задача требует максимум десять semantic попыток, каждая оплаченная/failed/unknown остаётся в ledger. Нет retries до получения удобной метки.

## Provenance и повторяемость

Для каждой попытки: annotation ID/type, source root/trace/segment и offsets, blinded ID mapping digest, raw request/response bytes и SHA-256, prompt/schema/ontology/context digests, requested/returned model, provider, available revision/quantization, неизвестные fields, seed requested/confirmed/unsupported, decoding, panel/round/vote, start/end/latency, HTTP/API status, finish reason, parse error, parsed label, evidence quote validation, usage/cost/generation ID, budget reservation/reconciliation. HTTP headers/Authorization и ключ не сохраняются. Отражённый ключ редактируется **до** base64, с явным redaction marker: такие bytes не называются исходными без потерь. Parsing failure не удаляет безопасно сохранённый raw ответ.

После основной development-разметки заранее выбранные по SHA-256 item_id первые `ceil(0.10*N)` completed items (минимум один при N>0, без просмотра меток) получают ровно одну повторную панель **первого** раунда, тех же inputs/seeds/route. N и выбранные IDs фиксируются до просмотра согласия; audit не влияет на consensus и не запускает semantic round 2. Сравнить exact response hashes, parsed votes, distributions и label changes отдельно. Incomplete audits остаются в denominator. Это same-input/seed repeatability, а разные seeds — sensitivity, не независимая репликация. Route drift создаёт новый измерительный режим и separate admission, не объединяется в панель.

Machine raw agreement, pairwise Cohen kappa/Fleiss kappa и consensus agreement показываются с task-root uncertainty и prevalence/coverage; нельзя назвать их `human_cohen_kappa_primary` или true human macro-F1. Коррелированные голоса одной линии могут единогласно ошибаться. DeepSeek-generated traces анализируются отдельно для bias генератор=разметчик. Альтернативные эмбеддеры и будущий human gold всё равно нужны.

## Стоимость без выдуманного тарифа

N — число реальных annotation items (segment и cluster отдельно), D — полный первый раунд без majority, A — заранее выбранные repeatability items. Базовые attempts `5*N`, semantic extra `5*D`, audit `5*A`; максимум `10*N+5*A`. Невыполненные requests не оплачены, unknown attempts не считаются бесплатными. Для каждого запроса заранее посчитать input tokens подтверждённым tokenizer или консервативной верхней границей UTF-8 bytes с chat-template overhead; output cap 1024. При тарифах RUB/token `p_in,p_out` резерв: сумма консервативных input/output bounds по максимальным admitted endpoint rates с коэффициентом запаса 2 как в Stage 0, плюс объявленные доплаты. Цены, units, тарифный snapshot и fallback при неизвестном тарифе проверяются до запуска; неизвестный тариф запрещает dispatch.

Иллюстрация **не корпуса**: N=200, D=200, A=20 дают максимум 2100 attempts и 2 150 400 output tokens по cap; это символическая worst-case оценка, не измеренная цена или мощность. Фактический spend отделяется от reserved и unknown; budget требует общей истории Stage 0, не только 0.41653321870992 RUB подтверждённых receipts. Четыре unknown стоимости и незакрытые резервы из опубликованного ZIP сохраняют ограничение. Пустая `.research` этой машины не восстанавливает бюджет и не разрешает новый расход.

После human deferral машинный pipeline может служить development-инструментом по отдельному разрешению, но научная интерпретация E1–E8 остаётся закрыта до независимого E0; Stage 1 не выполняет этот pipeline.
