"""Limited admission plan. It does not dispatch and does not admit models."""
from decimal import Decimal

from stage3.pipeline import PUBLISHED_CAP_RUB, verify_published_ledger
from stage3.roster_v4 import build_tasks

CANDIDATES = ("qwen/qwen3-32b", "deepseek/deepseek-v4.1-flash")
ATTEMPTS_PER_TASK = 3
HISTORICAL_MAX_REPORTED_COST = Decimal("0.228401553432")
SAFETY_FACTOR = Decimal("5")


def admission_tasks():
    selected = []
    for domain in ("math", "logic", "algorithms", "planning"):
        for seed in (0, 1):
            matches = [task for task in build_tasks()
                       if task["domain"] == domain and task["difficulty"] == "hard" and task["seed"] == seed]
            if len(matches) != 1:
                raise ValueError("Admission task selection is not unique")
            selected.append(matches[0])
    return selected


def plan():
    ledger = verify_published_ledger()
    tasks = admission_tasks()
    requests = len(CANDIDATES) * len(tasks) * ATTEMPTS_PER_TASK
    remaining = Decimal(ledger["remaining_rub"])
    envelope = HISTORICAL_MAX_REPORTED_COST * requests * SAFETY_FACTOR
    per_call_cap = remaining / requests
    return {
        "dispatched": False,
        "models_admitted": False,
        "models": [
            {"model_id": model, "admitted": False, "long_visible_trace_checked": False}
            for model in CANDIDATES
        ],
        "tasks": [{"task_id": task["task_id"], "domain": task["domain"], "difficulty": task["difficulty"],
                   "seed": task["seed"]} for task in tasks],
        "attempts_per_task": ATTEMPTS_PER_TASK,
        "request_count": requests,
        "max_tokens": 4096,
        "automatic_retries": 0,
        "ledger": ledger,
        "cost": {
            "provider_quote": "not_read",
            "historical_extrapolation_rub": str(envelope),
            "extrapolation_basis": "max reported Stage 0 cost times request count times 5; not a provider quote",
            "hard_stop_remaining_rub": str(remaining),
            "refuse_call_if_reservation_above_rub": str(per_call_cap),
        },
        "stopping": [
            "Do not send a call unless its reservation fits under the published 900 RUB cap.",
            "Do not retry a failed or unknown call automatically.",
            "Keep the reservation if the provider omits the cost.",
            "A truncated, summary-only, or encrypted trace does not admit the model.",
            "A provider change is a new route and does not inherit admission.",
            "Stop the battery if two attempts for one model lack a full visible trace.",
            "Do not start the 1800-trace pilot from this battery.",
        ],
    }
