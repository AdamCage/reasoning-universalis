# Local collection results

Exploratory observable-text pilot. E0 remains unpassed.

Planned rows: 576; saved traces: 384; gradeable answers: 333; correct: 329.

Counts of unparseable output and truncation overlap other status counts.

| Model | Domain | Split | Planned | Saved | Unsent | Reserved without trace | Gradeable | Correct | Truncated | Complete roots |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek/deepseek-v4.1-flash | algorithms | test | 16 | 16 | 0 | 0 | 16 | 16 | 0 | 4 |
| deepseek/deepseek-v4.1-flash | algorithms | train | 24 | 24 | 0 | 0 | 24 | 24 | 0 | 6 |
| deepseek/deepseek-v4.1-flash | algorithms | val | 8 | 8 | 0 | 0 | 8 | 8 | 0 | 2 |
| deepseek/deepseek-v4.1-flash | logic | test | 16 | 16 | 0 | 0 | 7 | 7 | 9 | 1 |
| deepseek/deepseek-v4.1-flash | logic | train | 24 | 24 | 0 | 0 | 17 | 16 | 7 | 4 |
| deepseek/deepseek-v4.1-flash | logic | val | 8 | 8 | 0 | 0 | 6 | 6 | 2 | 1 |
| deepseek/deepseek-v4.1-flash | math | test | 16 | 16 | 0 | 0 | 16 | 16 | 0 | 4 |
| deepseek/deepseek-v4.1-flash | math | train | 24 | 24 | 0 | 0 | 24 | 24 | 0 | 6 |
| deepseek/deepseek-v4.1-flash | math | val | 8 | 8 | 0 | 0 | 8 | 8 | 0 | 2 |
| deepseek/deepseek-v4.1-flash | planning | test | 16 | 16 | 0 | 0 | 16 | 16 | 0 | 4 |
| deepseek/deepseek-v4.1-flash | planning | train | 24 | 24 | 0 | 0 | 23 | 23 | 1 | 5 |
| deepseek/deepseek-v4.1-flash | planning | val | 8 | 8 | 0 | 0 | 8 | 8 | 0 | 2 |
| openai/gpt-oss-20b | algorithms | test | 16 | 16 | 0 | 0 | 16 | 16 | 0 | 4 |
| openai/gpt-oss-20b | algorithms | train | 24 | 24 | 0 | 0 | 24 | 24 | 0 | 6 |
| openai/gpt-oss-20b | algorithms | val | 8 | 8 | 0 | 0 | 8 | 8 | 0 | 2 |
| openai/gpt-oss-20b | logic | test | 16 | 16 | 0 | 0 | 4 | 4 | 12 | 0 |
| openai/gpt-oss-20b | logic | train | 24 | 24 | 0 | 0 | 15 | 15 | 9 | 3 |
| openai/gpt-oss-20b | logic | val | 8 | 8 | 0 | 0 | 4 | 4 | 4 | 1 |
| openai/gpt-oss-20b | math | test | 16 | 16 | 0 | 0 | 15 | 15 | 0 | 4 |
| openai/gpt-oss-20b | math | train | 24 | 24 | 0 | 0 | 23 | 23 | 0 | 6 |
| openai/gpt-oss-20b | math | val | 8 | 8 | 0 | 0 | 8 | 8 | 0 | 2 |
| openai/gpt-oss-20b | planning | test | 16 | 16 | 0 | 0 | 16 | 15 | 0 | 4 |
| openai/gpt-oss-20b | planning | train | 24 | 24 | 0 | 0 | 21 | 19 | 3 | 3 |
| openai/gpt-oss-20b | planning | val | 8 | 8 | 0 | 0 | 6 | 6 | 2 | 1 |
| qwen/qwen3-32b | algorithms | test | 16 | 0 | 16 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | algorithms | train | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | algorithms | val | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | logic | test | 16 | 0 | 16 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | logic | train | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | logic | val | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | math | test | 16 | 0 | 16 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | math | train | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | math | val | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | planning | test | 16 | 0 | 16 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | planning | train | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| qwen/qwen3-32b | planning | val | 8 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |

## Primary BGE result at 256 words

Positive static-minus-dynamic log loss favors the dynamic predictor. Intervals are exploratory and conditional on fitted predictors.

Input: artifacts/resumption-2026-11-08/local/analysis-bge.json

| Target | Status | Roots | Traces | Root-weighted correct fraction | Log loss gain | 95% interval |
|---|---|---:|---:|---:|---:|---|
| deepseek/deepseek-v4.1-flash | evaluated | 9 | 20 | 1.0 | -0.0015393917352612627 | [-0.006687386286370183, 0.0028993240405904676] |
| openai/gpt-oss-20b | evaluated | 11 | 34 | 0.9772727272727273 | 0.0 | [0.0, 0.0] |

Direct refitted order contrasts are preserved, separately by target, in summary.json.

## Budget

Reported costs: 22.6763145487870164037 RUB. Charged or reserved: 651.5180250837596 RUB. Remaining after commitments: 2348.4819749162404 RUB.

Reported costs are observed charges; commitments also retain conservative and unknown reserves. Missing cost is not zero.
