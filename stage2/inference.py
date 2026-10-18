"""RouterAI-only transport with a durable shared budget and no automatic retries."""
from decimal import Decimal
import os
from pathlib import Path
from stage0.config import BASE_URL, MODELS, EMBEDDERS
from stage0.runner import http, Ledger, estimate, encode, capture_body, validate_review, StopRun
from stage0.traces import inspect_trace
from .observations import ObservationStore, canonical


class RouterAITransport:
    """Explicitly constructed only for a separately admitted live development run.

    A reconciled existing shared ledger and immutable pricing snapshot are
    mandatory; an empty machine cannot silently reset historical reservations.
    Network authorization remains the selected cloud environment's policy.
    """
    def __init__(self, config, ledger_path, expected_ledger_sha256, pricing, journal_root, providers):
        import hashlib
        path = Path(ledger_path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_ledger_sha256:
            raise StopRun('Existing reconciled ledger does not match the approved snapshot')
        if config.values['ROUTERAI_BASE_URL'] != BASE_URL or not providers or not pricing:
            raise StopRun('Missing RouterAI identity or pricing admission')
        self.config=config;self.path=path;self.expected_snapshot=expected_ledger_sha256
        self.pricing=dict(pricing);self.providers=dict(providers);self.journal=ObservationStore(journal_root)

    def __call__(self, path, body):
        if path not in ('/embeddings','/chat/completions'):
            raise StopRun('Unexpected RouterAI endpoint')
        model=body.get('model');allowed=EMBEDDERS if path=='/embeddings' else MODELS
        if model not in allowed or model not in self.pricing or model not in self.providers:
            raise StopRun('Model/provider/pricing not admitted')
        price=tuple(Decimal(str(v)) for v in self.pricing[model])
        if len(price)!=2 or any(not v.is_finite() or v<0 for v in price):
            raise StopRun('Invalid token pricing')
        lock=self.config.root/'stage0.lock'
        try:
            descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:
            raise StopRun('Budget lock exists; reconcile unknown attempts first') from None
        os.close(descriptor)
        try:
            import hashlib
            if hashlib.sha256(self.path.read_bytes()).hexdigest()!=self.expected_snapshot:
                raise StopRun('Shared ledger changed; reconcile its current revision before dispatch')
            ledger=Ledger(self.path,self.config.budget)
            reservation=ledger.reserve(estimate(body,price),'stage2:'+path+':'+model)
            # Request bytes are persisted before dispatch. Credentials are only a header.
            req_key=self.journal.put(encode(body))
            self.journal.json({'phase':'reserved','reservation_id':reservation['id'],'request_digest':req_key,
                               'pricing':list(map(str,price)),'expected_provider':self.providers[model]})
            result=http(path,self.config.key,body,self.config.timeout)
            safe={k:v for k,v in result.items() if k!='headers'}
            response_key=self.journal.json(safe)
            ledger.finish(reservation,safe)
            self.expected_snapshot=hashlib.sha256(self.path.read_bytes()).hexdigest()
            self.journal.json({'phase':'finished_or_unknown','reservation_id':reservation['id'],
                               'request_digest':req_key,'response_digest':response_key})
            observed=safe.get('json',{})
            if observed.get('model','').casefold()!=model.casefold() or observed.get('provider')!=self.providers[model]:
                raise StopRun('Paid response has identity drift; raw and reservation retained')
            return safe
        finally:
            lock.unlink(missing_ok=True)


def generate_trace(config, task, review, transport):
    """A real full-trace admission is checked before any generation dispatch."""
    validate_review(config,review)
    model=next(iter(review['models']))
    if getattr(transport,'providers',{}).get(model) != review['models'][model].get('provider'):
        raise StopRun('Transport provider differs from the reviewed full-trace route')
    body={'model':model,'messages':[{'role':'user','content':task['prompt']}],
          'temperature':config.temperature,'top_p':config.top_p,'seed':config.seed,
          'max_tokens':config.max_tokens,'stream':False,'include_reasoning':True,'reasoning':{'enabled':True}}
    response=transport('/chat/completions',body)
    observation=inspect_trace(response.get('json',{}))
    return {'response':response,'observation':observation,'analysis_usable':observation['status']=='visible_trace_candidate',
            'model':model,'task_id':task['task_id'],'protocol_role':'development_not_confirmatory'}
