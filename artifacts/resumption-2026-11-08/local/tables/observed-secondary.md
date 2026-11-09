# Observed probability score contrasts

All saved observed-order contrasts are retained. Gains are static-minus-dynamic loss, equally weighted by original test root. Intervals are conditional pointwise 95% root-bootstrap intervals, without multiplicity correction. Raw error counts are not independent task counts. Constant fallback produces algebraic zero differences and does not establish equivalence.

| Representation | Words | Target | Test traces / roots | Target errors | Log-loss gain [95% interval] | Brier gain [95% interval] | Dynamic fit |
|---|---:|---|---:|---:|---|---|---|
| LEXICAL | 128 | DeepSeek | 24 / 11 | 0 | 0.01457 [0.00349, 0.02877] | 0.00636 [0.00128, 0.01299] | logistic |
| LEXICAL | 128 | GPT-OSS | 46 / 14 | 1 | 0.01073 [0.00273, 0.02027] | 0.00353 [0.00068, 0.00804] | logistic |
| LEXICAL | 256 | DeepSeek | 20 / 9 | 0 | -0.00863 [-0.02788, 0.00350] | -0.00013 [-0.00100, 0.00085] | logistic |
| LEXICAL | 256 | GPT-OSS | 34 / 11 | 1 | 0.00000 [0.00000, 0.00000] | 0.00000 [0.00000, 0.00000] | constant fallback |
| LEXICAL | 512 | DeepSeek | 9 / 4 | 0 | 0.01865 [-0.00130, 0.04295] | 0.00733 [-0.00084, 0.01571] | logistic |
| LEXICAL | 512 | GPT-OSS | 21 / 8 | 1 | 0.00000 [0.00000, 0.00000] | 0.00000 [0.00000, 0.00000] | constant fallback |
| BGE | 128 | DeepSeek | 24 / 11 | 0 | 0.00752 [0.00202, 0.01313] | 0.00313 [0.00086, 0.00572] | logistic |
| BGE | 128 | GPT-OSS | 46 / 14 | 1 | 0.00977 [-0.00282, 0.02353] | 0.00301 [-0.00001, 0.00718] | logistic |
| BGE | 256 | DeepSeek | 20 / 9 | 0 | -0.00154 [-0.00669, 0.00290] | -0.00050 [-0.00213, 0.00069] | logistic |
| BGE | 256 | GPT-OSS | 34 / 11 | 1 | 0.00000 [0.00000, 0.00000] | 0.00000 [0.00000, 0.00000] | constant fallback |
| BGE | 512 | DeepSeek | 9 / 4 | 0 | 0.03417 [0.01674, 0.05605] | 0.00371 [-0.00082, 0.00766] | logistic |
| BGE | 512 | GPT-OSS | 21 / 8 | 1 | 0.00000 [0.00000, 0.00000] | 0.00000 [0.00000, 0.00000] | constant fallback |
| QWEN | 128 | DeepSeek | 24 / 11 | 0 | 0.00707 [0.00376, 0.01053] | 0.00322 [0.00179, 0.00472] | logistic |
| QWEN | 128 | GPT-OSS | 46 / 14 | 1 | 0.01404 [-0.02282, 0.04559] | 0.00564 [-0.00103, 0.01336] | logistic |
| QWEN | 256 | DeepSeek | 20 / 9 | 0 | -0.00259 [-0.00700, 0.00138] | -0.00087 [-0.00238, 0.00041] | logistic |
| QWEN | 256 | GPT-OSS | 34 / 11 | 1 | 0.00000 [0.00000, 0.00000] | 0.00000 [0.00000, 0.00000] | constant fallback |
| QWEN | 512 | DeepSeek | 9 / 4 | 0 | -0.00625 [-0.04124, 0.03255] | -0.00022 [-0.01605, 0.01645] | logistic |
| QWEN | 512 | GPT-OSS | 21 / 8 | 1 | 0.00000 [0.00000, 0.00000] | 0.00000 [0.00000, 0.00000] | constant fallback |
