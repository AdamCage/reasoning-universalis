"""Deterministic 48-item core plus 24-item role-coverage challenge sample."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from machine_development.annotation import validate_item
from cross_model.common import ARTIFACT, PARENT, VERSION, canonical, immutable, rank, read, sha

PARENT_FILES = ("input-items.json", "machine-mapping.json", "codebook.json", "results.json", "summary.json",
                "source-inventory.json", "source-snapshot.zip")


def prepare(project, output_dir=None):
    project = Path(project)
    output = Path(output_dir) if output_dir is not None else project / ARTIFACT
    parent = project / PARENT
    pool = read(parent / "input-items.json")["items"]
    provenance = read(parent / "machine-mapping.json")["items"]
    reference = {r["item_id"]: r for r in read(parent / "results.json")["items"]}
    codebook = read(parent / "codebook.json")
    groups = defaultdict(list)
    for item in pool:
        validate_item(item)
        groups[provenance[item["item_id"]]["root_id"]].append(item["item_id"])
    if len(pool) != 200 or len(groups) != 24 or min(map(len, groups.values())) < 3:
        raise ValueError("Parent sampling frame differs")
    # 2 per root chosen without consulting any machine labels or outcomes.
    core = [i for root in sorted(groups) for i in sorted(groups[root], key=lambda i: (rank("core", i), i))[:2]]
    ablation = [min([i for i in core if i in groups[root]], key=lambda i: (rank("ablation", i), i)) for root in sorted(groups)]
    label = {i: reference[i]["primary"].get("role", "__unresolved__") for i in reference}
    counts = Counter(label[i] for i in core)
    pool_counts = Counter(label.values())
    candidates = {i for i in reference if i not in core}
    challenge, available_roots = [], set(groups)
    # Cover missing roles/unresolved first, then favor underrepresented roles.
    # All ties and all within-role decisions use fixed hashes, never new outputs.
    while available_roots:
        eligible = [i for i in candidates if provenance[i]["root_id"] in available_roots]
        def priority(i):
            role = label[i]
            return (counts[role] > 0, counts[role], pool_counts[role], rank("challenge", i), i)
        identity = min(eligible, key=priority)
        challenge.append(identity)
        available_roots.remove(provenance[identity]["root_id"])
        counts[label[identity]] += 1
    selected = core + challenge
    lookup = {i["item_id"]: i for i in pool}
    # Independently verify original Unicode offsets against the published full
    # traces. Full traces stay coordinator-side and are NEVER rendered to annotators.
    traces = {i["item_id"]: i["text"] for i in read(project / "artifacts/e0-human-development-2026-11-08/public-boundary/A/items.json")["items"]}
    mapping = {}
    for identity in selected:
        item, source = lookup[identity], provenance[identity]
        text = item["current_segment"]["text"]
        trace = traces[source["trace_item_id"]]
        start, end = source["char_start"], source["char_end"]
        context = "".join(v["text"] for v in item["previous_segments"])
        if (type(start) is not int or type(end) is not int or trace[start:end] != text
                or sha(text.encode("utf-8")) != source["text_sha256"] or not trace[:start].endswith(context)):
            raise ValueError("Parent original offsets or past context differ")
        r = reference[identity]
        votes = [v.get("vote") for v in r["round1"]]
        vote_labels = [v["primary_role"] if v else None for v in votes]
        mapping[identity] = {**source, "sample": "core" if identity in core else "challenge",
            "reference_role": r["primary"].get("role"), "reference_status": r["primary"]["status"],
            "reference_round": r["primary"].get("round_used"), "deepseek_round1_roles": vote_labels,
            "deepseek_round1_unanimous": len(vote_labels) == 5 and None not in vote_labels and len(set(vote_labels)) == 1,
            "segment_characters": len(text), "context_characters": len(context), "has_context": bool(context),
            "ablation": identity in ablation}
    protected = {f"{PARENT}/{n}": sha((parent / n).read_bytes()) for n in PARENT_FILES}
    for name in ("design/MACHINE_DEVELOPMENT_PROTOCOL_2026_11_08.json", "evidence/machine-annotation-development-2026-11-08/manifest.json",
                 "evidence/machine-annotation-development-2026-11-08/evidence.zip", "RESEARCH_SPECIFICATION.md"):
        protected[name] = sha((project / name).read_bytes())
    document = {"version": VERSION, "items": [lookup[i] for i in selected], "core_ids": core,
                "challenge_ids": challenge, "ablation_ids": ablation, "roots": 24, "planned_items": 72}
    inventory = {"version": VERSION, "files": protected, "input_text_normalized": False,
                 "offset_unit": "Python Unicode code points; original half-open [char_start,char_end)"}
    immutable(output / "input-items.json", document)
    immutable(output / "mapping.json", {"items": mapping})
    immutable(output / "codebook.json", codebook)
    immutable(output / "parent-integrity.json", inventory)
    descriptives = {s: {field: dict(Counter(str(mapping[i].get(field)) for i in ids)) for field in
                    ("root_id", "domain", "source_model", "reference_role", "reference_status", "has_context")}
                    for s, ids in (("core", core), ("challenge", challenge), ("pooled", selected))}
    immutable(output / "selection-summary.json", descriptives)
    return {"items": document["items"], "mapping": mapping, "core_ids": core, "challenge_ids": challenge,
            "ablation_ids": ablation, "output_dir": str(output), "parent_integrity": inventory}
