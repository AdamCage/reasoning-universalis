"""Prepare empty, masked development human-annotation packets; never pass E0."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from measurement.core import segments, previous_context
from measurement.lexical import ROLES

VERSION = "e0-human-development-handoff-v1"
SEED = "e0-human-development-2026-11-08-v1"
ROLE_ROUND = "roles_s2"
ATTESTATION = ("participant_pseudonym", "is_human", "independent_work", "no_llm_help",
               "not_segmenter_author", "no_other_response_access", "no_role_round_access_before_boundary",
               "training_completed", "completed_utc")


class HandoffError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise HandoffError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(HandoffError("Nonfinite JSON")))


def rank(*values):
    return sha(canonical([SEED, *values]))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def empty_form(packet):
    rows = []
    for item in packet["items"]:
        row = {"item_id": item["item_id"], "completed": None, "comment": None}
        if packet["round"] == "boundaries":
            row.update(boundaries=None, uncertain_boundaries=None)
        else:
            row.update(primary_role=None, secondary_roles=None, confidence=None, reason_code=None,
                       explanation=None, evidence_quotes=None, context_extended=None)
        rows.append(row)
    return {"schema_version": 1, "package_id": packet["package_id"], "slot": packet["slot"],
            "round": packet["round"], "packet_sha256": sha(canonical(packet) + b"\n"),
            "status": "pending_human_completion", "human_attestation": {key: None for key in ATTESTATION},
            "responses": rows}


def boundary_instructions():
    return """# Раунд 1: границы операций, без разметки ролей

Это development readiness, не независимая E0-валидация. Слоты A/B не являются именами людей.
Назначенные два человека сначала тренируются отдельно, затем работают независимо.
Не читать чужие ответы, координаторские ключи, role-round2, исходный репозиторий или отчёты.
Сейчас ответы и сведения об участниках пусты; код не подтверждает, что участник человек.
Скопируйте responses.empty.json за пределы пакета и заполняйте копию; исходный шаблон
и items.json входят в неизменный manifest. Сохраните completed_utc с часовым поясом.

Для каждой полной наблюдаемой трассы отметьте внутренние Unicode code-point offsets,
где меняется выполняемая операция или стратегия. Начало 0 и конец len(text) не границы.
CRLF считается двумя code points; не нормализуйте текст, пробелы или переводы строк.
Не делите формулу, код или одно вычисление ради словаря ролей. Сомнительные границы
сохраните отдельно в uncertain_boundaries. Пустой список [] допустим как явное решение
после чтения; null означает отсутствие ответа. completed должен быть true для каждой
завершённой записи. Не используйте LLM для разметки. Сначала сдайте оба файла отдельно.

Отдельный финальный API-ответ и проверенный ответ задачи скрыты. ANSWER внутри
reasoning остаётся частью исходного текста. Вывод мог быть обрезан API; разметка
описывает только показанный текст и не восстанавливает продолжение.
Проблемы ослепления/самоидентификацию в тексте отметьте в comment; текст не редактируйте.
Границы не означают проверенную корректность, внутренние состояния или полную трассу.
"""


def role_instructions(rubric):
    return """# Раунд 2: роли сегментов S2

Выполнять только после независимой сдачи обоих boundary-файлов и отдельного release.
Это собственная разметка фиксированных S2-сегментов, а не перенос ролей на human S1.
Не смотреть чужие ответы, исходные model/provider/correctness/cluster metadata или ключ.
Заполняйте отдельную копию responses.empty.json; не меняйте исходный frozen шаблон.
Аннотируется наблюдаемый текст, не внутреннее вычисление. Нельзя применять LLM.

На каждый item заполните primary_role, secondary_roles, confidence, reason_code,
explanation, evidence_quotes (дословные цитаты только CURRENT сегмента), context_extended,
completed и comment. Отсутствующий ответ остаётся null, а не ambiguous_other.
current_segment сохранён целиком; previous_segments — только два предыдущих сегмента
с общим пределом 1000 code points. Контекст не добавляется к текущему сегменту.
При нехватке контекста запросите полную видимую трассу у координатора, укажите
context_extended=true и опишите запрос в explanation. Такие ответы учитываются отдельно.
Не меняйте границы: используйте reason_code=boundary_problem при их недостаточности.
ANSWER внутри reasoning не удалён; отдельный финальный API-ответ не показан.

Ни разметка, ни её импорт не создают adjudicated gold, E0 pass или human scientific review.

## Унаследованная рубрика (без изменений)

""" + rubric


def build(results_path, tasks_path, proof_path, output, *, project=PROJECT, synthetic=False):
    results_path, tasks_path, proof_path = (Path(path).resolve(strict=True) for path in (results_path, tasks_path, proof_path))
    project, output = Path(project).resolve(strict=True), Path(output).absolute()
    require(not output.exists(), "Choose a new handoff output directory")
    result_bytes, task_bytes = results_path.read_bytes(), tasks_path.read_bytes()
    results, tasks, proof = load(results_path), load(tasks_path), load(proof_path)
    require(proof.get("status") == "passed" and proof.get("network_attempts") == 0
            and proof.get("results_sha256") == sha(result_bytes), "Closed raw replay proof does not bind these results")
    require(not proof.get("synthetic_fixture") or synthetic, "Synthetic input requires explicit synthetic build")
    require(results.get("phase") == "pilot_v2_provider_recovery_R1" and results.get("all_planned_cells") == 192
            and len(results["records"]) == 192, "Use the closed R1 all-planned-cell result")
    require(results.get("corpus_sha256") == sha(task_bytes), "Task corpus does not match the exact closed result context")
    task_index = {row["task_id"]: row for row in tasks["tasks"]}
    require(len(tasks["tasks"]) == len(task_index) == 48 and len({row["root_id"] for row in task_index.values()}) == 24,
            "The readiness package requires the original 48-task/24-root corpus")
    candidates = defaultdict(list)
    for row in results["records"]:
        task = task_index.get(row["task_id"])
        require(task and task["root_id"] == row["root_id"] and task.get("split") == "development"
                and task.get("confirmatory_excluded") is True, "Only exposed development roots are eligible")
        text = row.get("raw_reasoning_text")
        if isinstance(text, str) and text.strip():
            require(sha(text.encode("utf-8")) == row["raw_reasoning_sha256"], "Exact reasoning text hash differs")
            candidates[row["root_id"]].append(row)
    require(len(candidates) == 24, "All 24 roots need a visible-text candidate")
    selected = [min(values, key=lambda row: rank("trace", row["root_id"], row["trace_id"]))
                for root, values in sorted(candidates.items())]
    selected.sort(key=lambda row: rank("root", row["root_id"]))
    package_id = VERSION + "-" + rank("package", sha(result_bytes), sha(task_bytes),
        sha(Path(__file__).read_bytes()), sha(Path(__file__).with_name("import_e0_human.py").read_bytes()),
        sha((project / "design/E0_HUMAN_DEVELOPMENT_HANDOFF_2026_11_08.md").read_bytes()))[:16]
    trace_map, role_map, queues, trace_items = {}, {}, {}, {}
    for row in selected:
        task, text = task_index[row["task_id"]], row["raw_reasoning_text"]
        trace_id = rank("anonymous-trace", row["trace_id"])[:24]
        trace = {"trace_id": row["trace_id"], "task_id": row["task_id"], "root_id": row["root_id"],
                 "family": row["model"], "split": "development", "visible_reasoning": text,
                 "raw_response_sha256": row["response_sha256"]}
        rows = segments(trace, "S2")
        require(rows, "Selected trace has no nonempty S2 segment")
        trace_items[trace_id] = {"item_id": trace_id, "problem_statement": task["prompt"],
                                "text": text, "text_sha256": sha(text.encode("utf-8"))}
        trace_map[trace_id] = {"root_id": row["root_id"], "task_id": row["task_id"],
                             "physical_trace_id": row["trace_id"], "model": row["model"],
                             "provider": row["provider"], "source_text_sha256": row["raw_reasoning_sha256"],
                             "request_sha256": row["request_sha256"], "response_sha256": row["response_sha256"],
                             "source_protocol_sha256": row["protocol_sha256"], "source_status": row["status"],
                             "source_text_characters": len(text), "source_segment_count": len(rows),
                             "all_S2_boundaries": [r["char_end"] for r in rows[:-1]]}
        choices = []
        for index, segment in enumerate(rows):
            item_id = rank("anonymous-segment", segment["segment_id"])[:24]
            context = previous_context(rows, index)
            role_map[item_id] = {"trace_item_id": trace_id, "root_id": row["root_id"],
                                "physical_trace_id": row["trace_id"], "segment_id": segment["segment_id"],
                                "char_start": segment["char_start"], "char_end": segment["char_end"],
                                "text_sha256": sha(segment["text"].encode("utf-8")),
                                "previous_context_sha256": sha(context.encode("utf-8")),
                                "segmentation_version": segment["segmentation_version"]}
            choices.append({"item_id": item_id, "trace_item_id": trace_id,
                            "problem_statement": task["prompt"],
                            "current_segment": {"source_id": item_id, "text": segment["text"]},
                            "previous_segments": [{"source_id": item_id + "-context", "text": context}] if context else []})
        queues[trace_id] = sorted(choices, key=lambda item: rank("segment-selection", item["item_id"]))
    natural = []
    while len(natural) < 200 and any(queues.values()):
        for trace_id in trace_items:
            if queues[trace_id] and len(natural) < 200:
                natural.append(queues[trace_id].pop(0))
    require(len(natural) == 200, "Selected 24 traces have fewer than 200 available S2 segments")
    role_map = {item["item_id"]: role_map[item["item_id"]] for item in natural}
    rubric = (project / "design/ANNOTATION_PROTOCOL.md").read_text(encoding="utf-8")
    for slot in ("A", "B"):
        for round_name, items, directory in (
            ("boundaries", list(trace_items.values()), output / "public-boundary" / slot),
            (ROLE_ROUND, natural, output / "coordinator/role-round2-prepared" / slot),
        ):
            packet = {"schema_version": 1, "package_id": package_id, "slot": slot, "round": round_name,
                      "purpose": "development_readiness_not_independent_E0_validation",
                      "roles": list(ROLES) if round_name == ROLE_ROUND else None,
                      "items": sorted(items, key=lambda item: rank("presentation", round_name, slot, item["item_id"]))}
            write(directory / "items.json", packet)
            write(directory / "responses.empty.json", empty_form(packet))
            (directory / "INSTRUCTIONS.md").write_text(boundary_instructions() if round_name == "boundaries"
                                                      else role_instructions(rubric), encoding="utf-8", newline="\n")
    # Constructed controls remain separate and are never labelled human gold.
    practice = load(project / "design/HUMAN_REFERENCE_ITEMS.json")
    write(output / "practice/constructed-items.json", practice)
    write(output / "coordinator/constructed-control-key.json", load(project / "design/HUMAN_REFERENCE_CONSTRUCTED_KEY.json"))
    write(output / "coordinator/source-map.json", {"schema_version": 1, "traces": trace_map, "roles_s2": role_map})
    write(output / "coordinator/participants.empty.json", {"status": "no_humans_identified_or_verified",
        "annotators": [], "adjudicator": None, "identity_verification": "coordinator_pending"})
    write(output / "coordinator/gold.empty.json", {"status": "not_annotated_not_adjudicated",
        "labels": [], "annotators": [], "adjudicator": None, "E0": "pending"})
    write(output / "coordinator/role-schema-snapshot.json", load(project / "design/ANNOTATION_RESPONSE.schema.json"))
    sources = {}
    for label, path in {"results": results_path, "tasks": tasks_path, "raw_replay_proof": proof_path,
                        "annotation_protocol": project / "design/ANNOTATION_PROTOCOL.md",
                        "human_reference_protocol": project / "design/HUMAN_REFERENCE_PROTOCOL.md",
                        "preliminary_targets": project / "design/E0_PRELIMINARY.json",
                        "role_schema": project / "design/ANNOTATION_RESPONSE.schema.json",
                        "measurement_core": project / "measurement/core.py",
                        "measurement_evaluation": project / "measurement/evaluation.py",
                        "measurement_ontology": project / "measurement/lexical.py",
                        "handoff_creator": Path(__file__).resolve(),
                        "handoff_importer": Path(__file__).with_name("import_e0_human.py").resolve(),
                        "handoff_operational_note": project / "design/E0_HUMAN_DEVELOPMENT_HANDOFF_2026_11_08.md"}.items():
        sources[label] = {"path": path.relative_to(project).as_posix() if path.is_relative_to(project) else path.as_posix(),
                          "sha256": sha(path.read_bytes())}
    with zipfile.ZipFile(output / "coordinator/method-sources.zip", "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for label, source in sorted(sources.items()):
            if label in ("results", "tasks", "raw_replay_proof"):
                continue
            path = project / source["path"]
            data = path.read_bytes()
            source["snapshot_path"] = "methods/" + label + path.suffix
            info = zipfile.ZipInfo(source["snapshot_path"], (2026, 11, 8, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, data)
    write(output / "coordinator/source-provenance.json", {"sources": sources, "seed": SEED,
        "selection": "post-data minimum fixed hash per original root over all nonempty visible fragments; outcomes already available, no correctness/status ranking; round-robin hash-ranked S2 segments",
        "sample_kind": "root_balanced_observed_development_text_not_natural_prevalence_sample",
        "method_snapshot_scope": "exact original bytes/SHA in binary ZIP; inherited CRLF preserved, not a measured execution closure",
        "runtime_source_compatibility": "creator/importer and three measurement modules may differ only by CRLF-to-LF; no source rewriting",
        "synthetic_fixture": synthetic})
    (output / "README.md").write_text(
        "# Empty human development handoff\n\n"
        "Distribute only public-boundary/A or B to each separately assigned person, plus practice without its key. "
        "Coordinator files and prepared role-round2 must not be shown before both independent boundary submissions. "
        "Later distribute only the matching released role directory, never the private release receipt or the other person's submissions.\n\n"
        "All 24 roots are already exposed development data; 200 root-balanced S2 segments do not form a natural-prevalence or independent validation sample. "
        "There are no human names, labels, gold, agreement results or E0 approval in this package. "
        "Public source keys in the repository prevent any claim that its owner is blinded. Text may itself reveal identity cues.\n",
        encoding="utf-8", newline="\n")
    readiness = {"schema_version": 1, "package_id": package_id, "status": "prepared_awaiting_real_humans",
        "E0": "pending", "scientific_validity": "not_assessed", "human_gold": "not_annotated",
        "boundary_traces": 24, "role_segments_S2": 200, "exposed_development_roots": 24,
        "preliminary_root_minimum": 40, "root_shortfall_even_before_independence": 16,
        "independent_measurement_validation_roots": 0, "human_submissions": 0,
        "human_metrics": "not_evaluated", "per_role_gold_coverage": "unknown_until_humans_and_adjudication",
        "S1_role_labels": "not_prepared_pending_independent_boundaries", "S3": "unavailable_no_native_token_maps",
        "all_six_E0_checks": "not_completed", "natural_prevalence": "not_estimated",
        "blinding": "metadata_masking_and_separate_distribution_only_not_access_isolation",
        "owner_blinding": "not_claimed_public_source_keys_and_prior_exposure",
        "roles_released": False, "synthetic_fixture": synthetic}
    write(output / "readiness.json", readiness)
    manifest_files = [{"path": path.relative_to(output).as_posix(), "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}
                      for path in sorted(output.rglob("*")) if path.is_file()]
    write(output / "coordinator/package-manifest.json", {"schema_version": 1, "version": VERSION,
        "package_id": package_id, "files": manifest_files, "E0": "pending", "synthetic_fixture": synthetic})
    return readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(args.results, args.tasks, args.proof, args.output)
    except (HandoffError, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc) if isinstance(exc, HandoffError) else type(exc).__name__, "E0": "pending"}))
        raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
