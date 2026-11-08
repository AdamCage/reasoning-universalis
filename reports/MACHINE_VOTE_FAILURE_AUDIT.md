# Machine vote technical-failure audit

Postcollection scripted diagnostics of the closed annotation condition. No API calls, output repair or label changes.

All **1125 physical calls** were checked against the unchanged frozen collector gate and content parser: **1119 valid / 6 invalid**, with **0 disagreements** with stored outcomes. The finite registry retains 2100 maximum slots; conditional unscheduled slots are not physical attempts.

Returned-reasoning flags: **0**. This describes returned fields only; effective internal mode remains unconfirmed.

| Exact diagnostic category | Invalid calls |
|---|---:|
| `evidence_quote_length_outside_1_to_400` | 4 |
| `forbidden_extra_field` | 2 |

All six observed failures were first-round HTTP 200 responses with the exact requested model/provider and `finish_reason=stop`. Two added a forbidden `reason_code_note` field. Four supplied an exact source substring longer than the permitted 400 Unicode code points (445, 445, 445 and 446). The inherited parser's combined message `Quote not present in supplied current source` therefore denotes the quote-length constraint in these four cases; it does not establish a fabricated quote.

| Call ID | Item ID | Diagnostic |
|---|---|---|
| `2126d2b200151c11b0cb76a8e959f763b48ac9b8f01a702f39f25d4a1d25c90d` | `2e78d7aff131aee15c95b196` | `forbidden_extra_field` |
| `ec84b23d1f119ee08a64eb7f8e3056e36a9c99821b63974b4f8ea69512a0a36d` | `e1964218a36b2a06d8bb8a9d` | `evidence_quote_length_outside_1_to_400` |
| `25fe39476c3c02f3677d2e21cce612e55d45a8caf1944af0023fd1df7403600a` | `e1964218a36b2a06d8bb8a9d` | `evidence_quote_length_outside_1_to_400` |
| `788f6607be12dbadb72eecd5bc0aaffe673295a80415ef28c40ebd2420336906` | `e1964218a36b2a06d8bb8a9d` | `evidence_quote_length_outside_1_to_400` |
| `48a814b5d607e7fd7cb2bcc6f12d8e860928d61a6879c24e45ca409436919bd2` | `e1964218a36b2a06d8bb8a9d` | `evidence_quote_length_outside_1_to_400` |
| `fc0bb5a56a4e7cf06f42a5395c25f16d73d848ca757f00a52c960e2f3c9ebb11` | `e2d98f14eae2730eb0b6aae6` | `forbidden_extra_field` |

The [machine-readable audit](../artifacts/machine-annotation-development-2026-11-08/failure-audit.json) records all checked call IDs and request/response/body hashes; invalid rows also retain original root IDs, parser exception chains, extra/missing fields and quote-length/exact-substring checks. These details explain technical exclusion, not the correctness of an accepted functional label. Six invalid votes still leave three primary items technically unresolved; neither their JSON nor consensus was repaired.

Frozen protocol SHA-256: `0d53274f64e17249611815abe5bb380f5779818bde5545b5732315127bb1fb5e`. Source inventory SHA-256: `942e6a58acc19649cc5407e94acfbd72eed4f2944d4ffae441de624fc41c6f0e`. Audit script SHA-256: `041e4fb29225e2927d2580440c70a6056a74cd36a51cd5aeb9520eb6342374e0`.

Human gold remains absent; E0 is not passed and scientific validity is not assessed.
