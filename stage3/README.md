# Регистрация списка пилота §5.5

Офлайн-команды. Модели не вызываются. `stage3_started` остаётся false.

```bash
python3 -m stage3.roster --check design/PILOT_SECTION_5_5_ROSTER.json
python3 -m unittest tests.test_stage3_roster -v
```

Повторная запись того же списка:

```bash
python3 -m stage3.roster --write design/PILOT_SECTION_5_5_ROSTER.json
```

Граница перехода к живому этапу 3 описана в [reports/STAGE3_READINESS.md](../reports/STAGE3_READINESS.md).
