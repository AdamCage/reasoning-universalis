"""Explicit attempt conditions for a later pilot. This module does not dispatch."""

NOT_ADMITTED = ("qwen/qwen3-32b", "deepseek/deepseek-v4.1-flash")


def freeze_attempt(*, model_id, task_id, sample_index, seed, provider_id, protocol_digest):
    if any(not isinstance(value, str) or not value.strip()
           for value in (model_id, task_id, provider_id, protocol_digest)):
        raise ValueError("model_id, task_id, provider_id and protocol_digest must be explicit")
    if type(sample_index) is not int or sample_index < 0 or type(seed) is not int:
        raise ValueError("sample_index and seed must be explicit integers")
    return {
        "model_id": model_id,
        "task_id": task_id,
        "sample_index": sample_index,
        "seed": seed,
        "provider_id": provider_id,
        "protocol_digest": protocol_digest,
        "admitted_for_dispatch": model_id not in NOT_ADMITTED,
        "dispatch": False,
    }


def refuse_dict_order_model():
    raise ValueError("Refusing to choose a model with next(iter(models)); pass model_id on the attempt")


def bind_response(spec, request, response):
    if request.get("model") != spec["model_id"] or request.get("seed") != spec["seed"]:
        raise ValueError("Request does not match the frozen attempt")
    body = response.get("json") or {}
    if str(body.get("model", "")).casefold() != spec["model_id"].casefold():
        raise ValueError("Response model does not match the attempt")
    if body.get("provider") != spec["provider_id"]:
        raise ValueError("Response provider does not match the attempt")
    return {"admitted": False, "reason": "raw_retained_analysis_not_admitted" if not spec["admitted_for_dispatch"]
            else "response_bound_not_dispatched_here"}
