"""Same frozen rubric and content-only evidence validation across all routes."""
from __future__ import annotations

import copy
import json

from machine_development.annotation import render_item, validate_item, parse_response as legacy_parse
from cross_model.common import canonical, sha


def render(item, codebook):
    return render_item(item, codebook)


def parse_response(content, item):
    # The inherited parser rejects duplicate keys/non-finite JSON, enforces the
    # complete schema and checks exact quotes in the CURRENT segment only.
    if not isinstance(content, str):
        raise ValueError("Annotation content must be a JSON string")
    return legacy_parse(content, item)


def request_body(item, codebook, model, provider, condition="full_context"):
    validate_item(item)
    if condition not in ("full_context", "without_context", "schema_probe"):
        raise ValueError("Unknown frozen condition")
    supplied = copy.deepcopy(item)
    if condition == "without_context":
        supplied["previous_segments"] = []
    # Same rendered system/user messages as the parent; only transport settings
    # change. No old label, provenance, outcome or future text enters messages.
    schema = copy.deepcopy(codebook["response_schema"])
    for key in ("$id", "$schema", "title"):
        schema.pop(key, None)
    return {"model": model, "messages": render(supplied, codebook)["messages"],
            "max_tokens": 4096, "temperature": .7, "top_p": 1., "seed": 2026111501,
            "stream": False, "reasoning": {"enabled": False}, "include_reasoning": False,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "segment_role", "strict": True, "schema": schema}},
            "provider": {"order": [provider], "allow_fallbacks": False}}


def validate_envelope(response, item, model, provider):
    result = {"technical_status": "invalid", "vote": None, "invalid_reason": None,
              "returned_reasoning_present": False}
    try:
        payload = response["json"]
        if (response.get("http_status") != 200 or response.get("network_error")
                or type(payload) is not dict or payload.get("error") is not None
                or payload.get("model") != model or payload.get("provider") != provider):
            raise ValueError("transport_or_route_identity")
        choices = payload.get("choices")
        if type(choices) is not list or len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ValueError("incomplete_or_multiple_choices")
        message = choices[0]["message"]
        result["returned_reasoning_present"] = bool(message.get("reasoning") or message.get("reasoning_content") or message.get("reasoning_details"))
        result["vote"] = parse_response(message.get("content"), item)
        result["technical_status"] = "valid"
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        result["invalid_reason"] = "transport_identity_stop_json_schema_or_current_quote"
    return result


def probe_item():
    identity = "cross-model-structured-output-probe-v1"
    return {"item_id": identity, "problem_statement": "Compute 2 + 2.",
            "current_segment": {"source_id": identity, "text": "Therefore the answer is 4."},
            "previous_segments": []}
