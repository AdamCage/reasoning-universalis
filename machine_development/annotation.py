"""Finite machine role annotation using the existing strict Stage-2 semantics.

Rendering is value-only and uses an explicitly frozen UTF-8 codebook snapshot.
The legacy vote parser and panel rule remain the semantic implementation.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import random

from stage2.annotation import parse_vote, panel

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDER = "BytePlus"
PANEL_SIZE = 5
MAX_ROUNDS = 2
SEEDS = ((2026101201, 2026101202, 2026101203, 2026101204, 2026101205),
         (2026101211, 2026101212, 2026101213, 2026101214, 2026101215))
VERSION = "machine-development-annotation-v1"
ROLES = ("problem_formulation", "planning", "deduction_computation", "exploration", "verification",
         "uncertainty", "backtracking_correction", "conclusion", "ambiguous_other")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rank(purpose, item_id):
    return sha(canonical([VERSION, purpose, item_id]))


def validate_item(item):
    require(type(item) is dict and set(item) == {"item_id", "problem_statement", "current_segment", "previous_segments"},
            "Machine prompt item contains missing or forbidden metadata")
    require(isinstance(item["item_id"], str) and item["item_id"] and isinstance(item["problem_statement"], str),
            "Invalid anonymous item identity or problem text")
    current = item["current_segment"]
    require(type(current) is dict and set(current) == {"source_id", "text"}
            and current["source_id"] == item["item_id"] and isinstance(current["text"], str) and current["text"].strip(),
            "Current segment must be exact, nonempty, and anonymously identified")
    previous = item["previous_segments"]
    require(type(previous) is list and len(previous) <= 2, "At most two past segments are allowed")
    for segment in previous:
        require(type(segment) is dict and set(segment) == {"source_id", "text"}
                and isinstance(segment["source_id"], str) and isinstance(segment["text"], str),
                "Invalid past-only context")
    require(sum(len(segment["text"]) for segment in previous) <= 1000, "Past context exceeds 1000 Unicode code points")


def render_item(item, codebook, max_input_bytes=None):
    validate_item(item)
    require(codebook.get("version") == VERSION and codebook.get("roles") == list(ROLES)
            and isinstance(codebook.get("system"), str) and isinstance(codebook.get("ontology_definitions"), str)
            and type(codebook.get("response_schema")) is dict, "Invalid frozen machine codebook")
    payload = {"item_id": item["item_id"], "problem_statement": item["problem_statement"],
        "current_segment": item["current_segment"],
        "previous_segments": ["".join(segment["text"] for segment in item["previous_segments"])] if item["previous_segments"] else [],
        "ontology_definitions": codebook["ontology_definitions"], "response_schema": codebook["response_schema"]}
    messages = [{"role": "system", "content": codebook["system"]},
                {"role": "user", "content": canonical(payload).decode("utf-8")}]
    size = len(canonical(messages))
    require(max_input_bytes is None or type(max_input_bytes) is int and max_input_bytes > 0,
            "Input byte budget must be positive or explicitly unspecified")
    return {"item_id": item["item_id"], "messages": messages, "input_utf8_bytes": size,
        "oversized": max_input_bytes is not None and size > max_input_bytes,
        "input_sha256": sha(canonical(payload)), "prompt_sha256": sha(canonical(messages)),
        "schema_sha256": sha(canonical(codebook["response_schema"])),
        "codebook_sha256": sha(canonical(codebook)), "context_sha256": sha(canonical(payload["previous_segments"]))}


def request_body(item, codebook, round_number, vote_index, provider=PROVIDER):
    require(type(round_number) is int and round_number in (1, 2) and type(vote_index) is int and 0 <= vote_index < 5,
            "Vote is outside the fixed two-round five-seed schedule")
    require(provider == PROVIDER, "Only the pinned admitted BytePlus route is defined")
    return {"model": MODEL, "messages": render_item(item, codebook)["messages"], "max_tokens": 1024,
        "temperature": .7, "top_p": 1.0, "seed": SEEDS[round_number - 1][vote_index], "stream": False,
        "reasoning": {"enabled": False}, "include_reasoning": False,
        "provider": {"order": [provider], "allow_fallbacks": False}}


def parse_response(content, item):
    """Content-only validation; collector must first validate HTTP/route/stop."""
    validate_item(item)
    try:
        return parse_vote(content, item["item_id"], {item["item_id"]: item["current_segment"]["text"]})
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, UnicodeError) as error:
        raise ValueError("Invalid strict JSON/schema/current-segment evidence vote") from error


def panel_result(votes, round_number):
    require(type(round_number) is int and round_number in (1, 2), "Unknown semantic round")
    result = panel(votes, round_number)
    complete = len(votes) == 5 and all(vote is not None for vote in votes)
    return {**result, "complete": complete, "valid_votes": sum(vote is not None for vote in votes),
            "planned_votes": 5, "round_number": round_number}


def resolve_primary(round1, round2=None):
    first = panel_result(round1, 1)
    if first.get("next_round") == 2:
        if round2 is None:
            return first
        return {**panel_result(round2, 2), "first_round_counts": first["counts"], "pooled_rounds": False}
    require(round2 is None, "Technical or resolved first panels cannot open a semantic repeat")
    return {**first, "pooled_rounds": False}


def audit_item_ids(items):
    ids = [item["item_id"] for item in items]
    require(len(ids) == len(set(ids)), "Repeated audit candidate item")
    count = math.ceil(.1 * len(ids))
    return sorted(ids, key=lambda value: (rank("repeatability-audit", value), value))[:count]


def select_balanced(pool, mapping, count):
    require(type(count) is int and (count in range(24, 193, 24) or count == 200),
            "Prospective N must be a fixed24-root multiple up to192 or the complete200-item pool")
    require(len(pool) == 200 and len({item["item_id"] for item in pool}) == 200, "Use the original fixed200-item pool")
    grouped = {}
    for item in pool:
        validate_item(item)
        root = mapping[item["item_id"]]["root_id"]
        grouped.setdefault(root, []).append(item)
    require(len(grouped) == 24 and min(map(len, grouped.values())) >= count // 24,
            "The proposed count cannot retain equal items in all24 root blocks")
    selected = []
    roots = sorted(grouped, key=lambda value: (rank("root-allocation", value), value))
    ordered = {root: sorted(values, key=lambda item: (rank("segment-selection", item["item_id"]), item["item_id"]))
               for root, values in grouped.items()}
    for position in range(max(map(len, grouped.values())) if count == 200 else count // 24):
        selected.extend(ordered[root][position] for root in roots if position < len(ordered[root]))
    require(len(selected) == count, "Root-balanced selection changed the prospective count")
    return selected


def vote_entropy(votes):
    valid = [vote for vote in votes if vote is not None]
    counts = Counter(vote["primary_role"] for vote in valid)
    return {"valid_votes": len(valid), "counts": {role: counts[role] for role in ROLES},
        "entropy_bits": -sum((count / len(valid)) * math.log2(count / len(valid)) for count in counts.values()) if valid else None,
        "unanimous": len(valid) == 5 and len(counts) == 1}


def agreement_summary(panels, roots=None, bootstrap_replicates=0):
    """Complete-five same-round panels only; descriptive, never role accuracy."""
    complete = [values for values in panels if len(values) == 5 and all(value is not None for value in values)]
    pairs, agree, margins = 0, 0, Counter()
    for values in complete:
        labels = [value["primary_role"] for value in values]
        margins.update(labels)
        for left in range(5):
            for right in range(left + 1, 5):
                pairs += 1
                agree += labels[left] == labels[right]
    observed = agree / pairs if pairs else None
    expected = sum((count / (5 * len(complete))) ** 2 for count in margins.values()) if complete else None
    pairwise = []
    for left in range(5):
        for right in range(left + 1, 5):
            a, b = Counter(value[left]["primary_role"] for value in complete), Counter(value[right]["primary_role"] for value in complete)
            p0 = sum(value[left]["primary_role"] == value[right]["primary_role"] for value in complete) / len(complete) if complete else None
            pe = sum(a[role] * b[role] for role in ROLES) / len(complete) ** 2 if complete else None
            pairwise.append({"vote_indexes": [left, right], "complete_items": len(complete), "raw_agreement": p0,
                             "cohen_kappa": (p0 - pe) / (1 - pe) if pe is not None and pe < 1 else None})
    result = {"complete_five_panels": len(complete), "all_panels": len(panels), "unordered_vote_pairs": pairs,
        "raw_pairwise_agreement": observed, "fleiss_kappa": (observed - expected) / (1 - expected)
            if expected is not None and expected < 1 else None,
        "pairwise_cohen": pairwise,
        "degenerate_marginals": expected == 1 if expected is not None else None,
        "interpretation": "correlated same-model machine agreement, not human agreement or accuracy"}
    if roots is not None and bootstrap_replicates:
        require(len(roots) == len(panels), "Root bootstrap needs one original root for every planned panel")
        by_root = {}
        for root, values in zip(roots, panels):
            by_root.setdefault(root, []).append(values)
        root_ids, rng, samples = sorted(by_root), random.Random(20261012), []
        if len(root_ids) >= 2:
            for _ in range(bootstrap_replicates):
                selected = [values for __ in root_ids for values in by_root[rng.choice(root_ids)]]
                samples.append(agreement_summary(selected))
        interval = {}
        for key in ("raw_pairwise_agreement", "fleiss_kappa"):
            defined = sorted(value[key] for value in samples if value[key] is not None)
            interval[key] = {"interval95": [defined[int(.025 * (len(defined) - 1))], defined[int(.975 * (len(defined) - 1))]] if defined else None,
                             "defined_replicates": len(defined)}
        result["root_bootstrap"] = {"unit": "original_task_root", "root_blocks": len(root_ids),
            "replicates": bootstrap_replicates, "seed": 20261012, "metrics": interval,
            "scope": "descriptive root resampling of observed machine panels; no human validity or IID population claim"}
    return result


def summarize(items, primary_results, votes, mapping):
    """Simple immutable-label summaries; raw votes and audits stay separate.

    ``votes`` maps item IDs to {1: five parsed-or-null votes, 2: optional five}.
    Audit panels are deliberately not accepted by this primary-summary API.
    """
    ids = {item["item_id"] for item in items}
    require(set(primary_results) == set(votes) == ids and all(set(votes[identity]) <= {1, 2} and 1 in votes[identity] for identity in ids),
            "Primary summary must retain exactly planned items and only their two semantic panels")
    counts = Counter(primary_results[item["item_id"]]["status"] for item in items)
    roles, strata, entropy = Counter(), {}, []
    for item in items:
        identity = item["item_id"]
        result = primary_results[identity]
        role = result.get("role")
        if role is not None:
            roles[role] += 1
        source = mapping[identity]
        for field in ("root_id", "source_model", "domain", "tier"):
            key = field + ":" + str(source.get(field, "unknown"))
            group = strata.setdefault(key, Counter())
            group["planned_items"] += 1
            group[result["status"]] += 1
        entropy.append({"item_id": identity, "round1": vote_entropy(votes[identity][1]),
                        "round2": vote_entropy(votes[identity][2]) if 2 in votes[identity] else None})
    return {"version": VERSION, "planned_items": len(items), "distinct_root_blocks": len({mapping[item["item_id"]]["root_id"] for item in items}),
        "primary_status_counts": dict(sorted(counts.items())), "consensus_roles": {role: roles[role] for role in ROLES},
        "round1_agreement": agreement_summary([votes[item["item_id"]][1] for item in items],
            [mapping[item["item_id"]]["root_id"] for item in items], bootstrap_replicates=1000),
        "round2_conditional_agreement": agreement_summary([votes[item["item_id"]][2] for item in items if 2 in votes[item["item_id"]]],
            [mapping[item["item_id"]]["root_id"] for item in items if 2 in votes[item["item_id"]]], bootstrap_replicates=1000),
        "strata": {key: dict(sorted(value.items())) for key, value in sorted(strata.items())}, "vote_entropy": entropy,
        "human_gold": "not_created", "E0": "not_passed", "scientific_validity": "not_assessed",
        "accuracy_estimated": False, "audit_updates_primary": False}
