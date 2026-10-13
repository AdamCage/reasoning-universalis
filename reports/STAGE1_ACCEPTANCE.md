# Stage 1 — приёмка G1 v1.1

14 октября 2026, Europe/Istanbul. **Stage 1 принят как научный дизайн; G1 approved.** Утверждающий — AdamCage, назначенный пользователем владелец репозитория. В ответ на предъявленный пакет и запрос version-bound approval пользователь написал дословно: «ок утверждаю». Контекст решения и время фиксации сохранены в [G1.json](../design/G1.json); исходный timestamp сообщения интерфейс не предоставляет.

Утверждён **review snapshot** `68fc12da05000674e3d770a07e449c37a4fbc119`, версия `stage1-design-v1.1`, PR #4. Payload SHA-256: `04988a3ec82db073a04a71519e35f91740398d9a66636dc2935ce3377c079963`. Manifest находится в этом commit по `design/STAGE1_APPROVAL_MANIFEST.json`; полный inventory и hashes сохраняют утверждённый вопрос, исходную онтологию H0–H7 и дизайн. Commit с настоящим receipt документирует последующее решение и не заменяет approved snapshot.

До approval пользователь подтвердил закрытие P2 и отсутствие новых замечаний по `68fc12d`, 43/43 tests, проверку exact snapshot, offline demo, Stage 0 audit и diff checks. После approval ещё раз проверены exact snapshot и связь receipt с manifest/source hashes; существующий suite 43/43 и diff checks прошли. Научная спецификация, EpistemeOS и все 27 файлов утверждённого payload сохранены байт-в-байт; README, mutable G1 receipt и этот итог находятся вне payload.

Девять критериев §7 RESEARCH_PLAN закрыты для дизайна: пункты 1–8 подготовлены и проверены в [исторической матрице](STAGE1_REPORT.md); пункт 9 закрыт явным решением AdamCage с approved commit, artifact hashes, дословным statement и контекстом. Исторические pending записи в preregistration, report и manifest остаются частью неизменяемого review snapshot. Verifier возвращает `pending_in_review_snapshot` именно для этого исторического пакета; текущий gate status читается из отдельного `G1.json`.

Проверка утверждённого содержимого:

```bash
python3 design/verify_stage1.py --commit 68fc12da05000674e3d770a07e449c37a4fbc119
```

E0 **не пройден**, независимая человеческая валидация отложена, G2 не заморожен, G3/G4 не выполнены. G1 утверждает вопрос/исходную онтологию и конкретный Stage 1 дизайн; он не устанавливает научный результат и не создаёт scientifically approved claim в EpistemeOS. Следующие этапы и платные эксперименты требуют своих условий и отдельного разрешения; в этой записи они не начаты. PR не слит автоматически.
