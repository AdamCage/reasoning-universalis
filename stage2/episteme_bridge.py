"""Explicit external pack registration and real kernel workflow, without kernel edits."""
import argparse
import copy
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT/'EpistemeOS'/'src') not in sys.path:
    sys.path.insert(0, str(ROOT/'EpistemeOS'/'src'))

from episteme.domains import registry
from episteme import domain_packs
from episteme.store import Store
from episteme.kernel import Actor, Kernel
from episteme.planning import Planning
from episteme.commands import CommandService
from episteme.search import Search, COMPONENTS
from episteme.batch_controller import advance_batch
from episteme.analysis_controller import advance_pack_analysis
from episteme.execution_locked import freeze_closure
from .historical import prepare
from .observations import canonical

PACK = 'reasoning_universalis_v1'
PLANNER = Actor('stage2-planner', 'planner')
ANALYST = Actor('stage2-analyst', 'analyst')
STUDY = 'reasoning-universalis-stage2-development'


def register():
    existing = registry.PACKS.get(PACK)
    if existing not in (None, PACK):
        raise ValueError('Conflicting explicit pack registration')
    registry.PACKS[PACK] = PACK  # Explicit application allowlist; no source patch or discovery.
    return registry.load_pack(PACK)


def command(store, action, payload, actor=PLANNER):
    return CommandService(store).execute({'context': {'command_id': uuid.uuid4().hex,
           'expected_revision': len(store.events()), 'actor': actor.id, 'role': actor.role,
           'study_id': STUDY, 'correlation_id': 'stage2-workflow', 'causation_id': None},
           'request': {'version': 1, 'action': action, 'payload': copy.deepcopy(payload)}})


def run(root, source, contrast='S2-S1'):
    loaded = register()
    source = Path(source); bundle = json.loads((source/'bundle.json').read_bytes())
    with Store(root) as store:
        planner = Planning(store, PLANNER); scope = {'population': 'observed development roots only'}
        question = planner.question(study_id=STUDY, statement='Do measured count deltas recompute from original reasoning observations?',
                                    objective='Validate Stage 2 provenance, not H0-H7.', scope=scope,
                                    constraints=['E0 not passed', 'No scientific approval', 'External historical inference'],
                                    stopping_criteria=['Complete frozen primary/reanalysis roster then human review'])
        hypotheses = [Kernel(store, PLANNER).hypothesis(text, prediction, falsifier, scope)
                      for text, prediction, falsifier in [('Features match saved observations', 'Counts agree', 'Bytes/count mismatch'),
                                                          ('Features are corrupted', 'Counts disagree', 'All bytes/counts agree')]]
        explanation = planner.explanation_set(question=question, hypotheses=hypotheses, comparison_plan='Preserve both explanations, check exact raw binding.')
        captured = domain_packs.store_capture(store, PACK, source)
        import reasoning_universalis_v1 as pack
        environment = freeze_closure(store, {'pyproject.toml': pack.programs.PYPROJECT, 'uv.lock': pack.programs.UV_LOCK}, set_variables={'PYTHONHASHSEED': '0'})
        import hashlib
        bound = command(store, 'pack.preregister', {'explanation_set': explanation, 'pack_id': PACK,
                        'pack_version': loaded.pack_version, 'pack_code_digest': loaded.pack_code_digest,
                        'parameters': {'contrast': contrast, 'bundle_digest': hashlib.sha256((source/'bundle.json').read_bytes()).hexdigest(),
                                       'method_digest': bundle['method_digest']}, 'host_inputs': {},
                        'capture': captured['capture'], 'environment': environment})
        search = Search(store, PLANNER); count = 2*len(bundle['roots'])
        tree = search.register_tree(weights={k: 1 for k in COMPONENTS}, cost_weight=0, budget=count,
                                    cost_unit='enqueued_attempt', max_nodes=1, max_depth=0, max_width=1, max_selections=1, max_retries=0)
        search.add_node(tree, protocol=bound['protocol'], action='discriminate', estimated_cost=count,
                        components={'discrimination': 0, 'uncertainty': 0, 'coverage': 1, 'invalidity_risk': .5},
                        rationale='Technical raw-linked development count; no scientific outcome.')
        selected = search.select_next(tree)
        binding = Kernel._get(store.events(), bound['binding'], 'pack_binding')
        batch = command(store, 'batch.plan', {'selection': selected['id'], 'executor': 'stage2-offline-executor',
                         'replicator': 'stage2-same-author-reanalysis', **domain_packs.execution_fields(store, binding)})
        settlement = advance_batch(store, batch)
        if settlement['status'] != 'completed':
            raise RuntimeError('Offline batch incomplete: '+str(settlement))
        analysed = advance_pack_analysis(store, batch, planner=PLANNER, analyst=ANALYST, reviewer_actor='future-human-reviewer')
        claim = Kernel._get(store.events(), analysed['claim'], 'claim')
        gate = Kernel(store, Actor('stage2-observer', 'observer')).gate(analysed['claim'])
        result = {'pack': PACK, 'pack_code_digest': loaded.pack_code_digest, 'protocol': bound['protocol'],
                  'binding': bound['binding'], 'batch': batch, 'claim': analysed['claim'],
                  'outcome': claim['payload']['outcome'], 'inference_mode': claim['payload']['inference_mode'],
                  'scientific_validity': 'not_assessed', 'gate': gate, 'network_calls': 0,
                  'attempts': len(bundle['observations']), 'segments': len(bundle['segments']), 'E0': 'not_passed'}
        (Path(root).parent/'workflow-result.json').write_bytes(canonical(result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contrast', choices=['S2-S1', 'S1-S2', 'S2-S2'], default='S2-S1')
    args = parser.parse_args(); source = prepare(args.output/'import')
    print(json.dumps(run(args.output/'store', source, args.contrast), indent=2))


if __name__ == '__main__':
    main()
