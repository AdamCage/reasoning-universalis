# Бесплатное воспроизведение машинной разметки

**Фактическая проверка прошла 8 ноября 2026, 22:05:33 UTC / 9 ноября 01:05:33 по Москве.** Отдельный Python-процесс восстановил закрытые observations и повторил проверки без ключа, `.env` или сетевых обращений. Это воспроизведение сохранённых ответов тем же кодом, а не новая выборка ответов модели или независимая валидация ролей.

Пакет: [manifest.json](../evidence/machine-annotation-development-2026-11-08/manifest.json), [evidence.zip](../evidence/machine-annotation-development-2026-11-08/evidence.zip), [машиночитаемая квитанция](../artifacts/machine-annotation-development-2026-11-08/reproduction-check.json).

| Проверка | Фактический результат |
|---|---|
| Исходный R1, включённый в пакет | Старый R1 replay прошёл первым |
| Машинная матрица | 200 items, 2100 максимальных slots, 1125 фактических вызовов |
| Frozen source | Все 26 файлов совпали по точным raw bytes, включая унаследованные CRLF |
| Запросы и ответы | Проверены identities, seeds, body hashes, schema/evidence, стоимость и условия второго раунда/аудита |
| Результаты и summary | Побайтно совпали с опубликованными JSON |
| Ledger | Сохранены 984 родительские строки; закрытый ledger содержит 2109 строк |
| Общие обязательства с резервами | 2038.3174633704220 RUB |
| Сетевые обращения | 0 |

Новый consumer дополнительно проверяет raw API cost, state и commitment каждой из 1125 записей и порядок vote indexes, чтобы same-seed audit не сравнивал чужие seeds. Эти усиления не изменили results, summary, budget или текст основного отчёта. Audit не меняет primary consensus. Все 975 ненужных conditional slots сохранены в матрице.

SHA-256 manifest: `be1f842baf2fbf071d822b57760a47d892177eef1f46de3e2b1e893f9b0031a6`. Размер ZIP — 23 675 674 bytes. SHA квитанции: `bb58042253b2bf020690397f06a12a903c8dc51d1113c01c01203b0c75bb0769`. Protocol SHA: `0d53274f64e17249611815abe5bb380f5779818bde5545b5732315127bb1fb5e`; source-inventory SHA: `942e6a58acc19649cc5407e94acfbd72eed4f2944d4ffae441de624fc41c6f0e`.

## Команда переноса

Для строгого совпадения численных bytes использовать reference CPython **3.12.11** и зависимости из `requirements-resumption.txt`; выходной каталог должен быть новым:

```powershell
python -X utf8 scripts/reproduce_machine_development.py --manifest evidence/machine-annotation-development-2026-11-08/manifest.json --output .research/new-machine-offline-replay
```

Старые платные команды не повторяются. Сырые модельные ответы не генерируются заново. Фактический same-seed model audit — отдельная часть исходного прогона: 20/20 совпавших consensus roles, 92/100 совпавших primary-role votes и 58/100 полностью совпавших parsed votes. Он не доказывает детерминизм провайдера или правильность роли.

### Ограничение численной переносимости

В CI `42531390470` общий набор тестов прошёл на Linux Python3.11/3.13, а полный опубликованный replay — на Windows Python3.12. Linux3.11 остановился на строгом сравнении `summary.json`. Реальный отдельный запуск на Windows3.11.13 воспроизвёл ровно одно различие JSON: `/round1_agreement/root_bootstrap/metrics/fleiss_kappa/interval95/0` равно `0.7060296279441571` вместо сохранённого `0.706029627944157`, то есть 1ULP. В Python3.12 [изменён алгоритм `sum(float)`](https://docs.python.org/3.12/library/functions.html#sum); frozen `annotation.py` использует его для ожидаемого совпадения Fleiss κ. In-memory воспроизведение старого суммирования подтвердило ту же единственную разницу.

Дополнительный запуск архивного worker на Ubuntu/WSL Python3.12.3 повторил точные results, summary, budget и26source bytes с0сетевых обращений. Он использовал уже проверенный родительский R1 из Windows replay и сам по себе не является полным свежим Linux replay. Для окончательной полной CI-проверки опубликованного архива закреплён CPython3.12.11; общий suite продолжает работать на3.11/3.13. Строгое побайтовое сравнение сохраняется, численная tolerance не введена. Frozen26, исходный архив, статистика, метки и финансовые файлы не изменены. Это ограничение runtime-переносимости, не изменение научного результата.

Проверены четыре вложенных ZIP: 8240 members, 8085 JSON и 2660 декодированных HTTP bodies. Настроенный credential не найден; секретные значения и reserved holdout seed не публикуются, seed не читался. E0 не пройден, human gold отсутствует, научная валидность не оценена.


Позднее, в22:52:33 UTC, **полный свежий replay на Ubuntu/WSL CPython3.12.3** также прошёл: parentR1 был восстановлен заново из архива, results/summary/budget/source26 совпали, network_attempts0. [Отдельная Linux-квитанция](../artifacts/machine-annotation-development-2026-11-08/reproduction-linux-check.json) сохраняет этот результат. Она получена после закрытия EpistemeOS integrity stage и не входит в его48индексированных inputs; исходная Windows-квитанция и все запечатанные пакеты сохранены.
