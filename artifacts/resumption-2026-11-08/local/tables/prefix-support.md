# Prefix class support

Raw label counts; repeated traces within a root are dependent.

| Words | Model | Split | Traces | Roots | Correct | Incorrect | Roots with error | Classes |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 128 | qwen/qwen3-32b | train | 0 | 0 | 0 | 0 | 0 | none |
| 128 | qwen/qwen3-32b | val | 0 | 0 | 0 | 0 | 0 | none |
| 128 | qwen/qwen3-32b | test | 0 | 0 | 0 | 0 | 0 | none |
| 128 | deepseek/deepseek-v4.1-flash | train | 44 | 18 | 43 | 1 | 1 | both_classes |
| 128 | deepseek/deepseek-v4.1-flash | val | 16 | 6 | 16 | 0 | 0 | single_class |
| 128 | deepseek/deepseek-v4.1-flash | test | 24 | 11 | 24 | 0 | 0 | single_class |
| 128 | openai/gpt-oss-20b | train | 77 | 23 | 75 | 2 | 2 | both_classes |
| 128 | openai/gpt-oss-20b | val | 26 | 7 | 26 | 0 | 0 | single_class |
| 128 | openai/gpt-oss-20b | test | 46 | 14 | 45 | 1 | 1 | both_classes |
| 256 | qwen/qwen3-32b | train | 0 | 0 | 0 | 0 | 0 | none |
| 256 | qwen/qwen3-32b | val | 0 | 0 | 0 | 0 | 0 | none |
| 256 | qwen/qwen3-32b | test | 0 | 0 | 0 | 0 | 0 | none |
| 256 | deepseek/deepseek-v4.1-flash | train | 25 | 14 | 25 | 0 | 0 | single_class |
| 256 | deepseek/deepseek-v4.1-flash | val | 11 | 5 | 11 | 0 | 0 | single_class |
| 256 | deepseek/deepseek-v4.1-flash | test | 20 | 9 | 20 | 0 | 0 | single_class |
| 256 | openai/gpt-oss-20b | train | 60 | 20 | 58 | 2 | 2 | both_classes |
| 256 | openai/gpt-oss-20b | val | 17 | 6 | 17 | 0 | 0 | single_class |
| 256 | openai/gpt-oss-20b | test | 34 | 11 | 33 | 1 | 1 | both_classes |
| 512 | qwen/qwen3-32b | train | 0 | 0 | 0 | 0 | 0 | none |
| 512 | qwen/qwen3-32b | val | 0 | 0 | 0 | 0 | 0 | none |
| 512 | qwen/qwen3-32b | test | 0 | 0 | 0 | 0 | 0 | none |
| 512 | deepseek/deepseek-v4.1-flash | train | 6 | 5 | 6 | 0 | 0 | single_class |
| 512 | deepseek/deepseek-v4.1-flash | val | 3 | 2 | 3 | 0 | 0 | single_class |
| 512 | deepseek/deepseek-v4.1-flash | test | 9 | 4 | 9 | 0 | 0 | single_class |
| 512 | openai/gpt-oss-20b | train | 32 | 13 | 30 | 2 | 2 | both_classes |
| 512 | openai/gpt-oss-20b | val | 8 | 4 | 8 | 0 | 0 | single_class |
| 512 | openai/gpt-oss-20b | test | 21 | 8 | 20 | 1 | 1 | both_classes |
