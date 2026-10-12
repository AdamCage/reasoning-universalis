"""Strict, non-interpolating environment contract. Never display secret values."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

MODELS = ('qwen/qwen3-8b', 'qwen/qwen3.8-27b', 'openai/gpt-oss-20b',
          'meta/muse-glimmer-30b', 'google/gemma-4-31b-it', 'nvidia/nemotron-3-nano-30b-a3b')
EMBEDDERS = ('baai/bge-m3', 'qwen/qwen3-embedding-8b')
BASE_URL = 'https://routerai.ru/api/v1'


class ConfigurationError(ValueError):
    pass


def parse_env(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in values:
            raise ConfigurationError('Invalid or duplicate environment assignment')
        if value[:1] in ('"', "'"):
            if len(value) < 2 or value[-1] != value[0]:
                raise ConfigurationError('Unclosed environment quote')
            value = value[1:-1]
        if any(c in value for c in ('\x00', '\r', '\n')):
            raise ConfigurationError('Invalid environment control character')
        values[key] = value
    return values


@dataclass(frozen=True)
class Config:
    key: str = field(repr=False)
    values: dict = field(repr=False)
    budget: Decimal
    max_tokens: int
    timeout: int
    seed: int
    temperature: float
    top_p: float
    root: Path
    store_root: Path

    @classmethod
    def load(cls, path='.env', contract='env.example'):
        v = parse_env(path)
        required = parse_env(contract)
        if set(v) != set(required):
            raise ConfigurationError('Environment keys differ from env.example')
        if not v['ROUTERAI_API_KEY'].strip() or any(c.isspace() for c in v['ROUTERAI_API_KEY']):
            raise ConfigurationError('ROUTERAI_API_KEY is empty or malformed')
        if v['ROUTERAI_BASE_URL'] != BASE_URL:
            raise ConfigurationError('Only the prescribed RouterAI URL is allowed')
        if tuple(v['RU_MODELS'].split(',')) != MODELS:
            raise ConfigurationError('The exact six candidate identifiers are required')
        if tuple(v['RU_EMBEDDING_MODELS'].split(',')) != EMBEDDERS:
            raise ConfigurationError('Only the exact two embedders are allowed')
        flags = ['RU_INCLUDE_REASONING', 'RU_REQUIRE_VISIBLE_REASONING',
                 'RU_REJECT_REASONING_SUMMARIES', 'RU_PREFLIGHT_EACH_MODEL', 'RU_SAVE_RAW_RESPONSES']
        if any(v[k] != 'true' for k in flags) or v['RU_AUTO_MODEL_SUBSTITUTION'] != 'false':
            raise ConfigurationError('Required trace and provenance safeguards are disabled')
        if v['RU_PHASE'] != 'pilot' or v['RU_SEGMENTATION'] != 'sentence':
            raise ConfigurationError('Stage zero only supports pilot/sentence')
        if v['RU_DOMAINS'] != 'math,logic,algorithms,planning':
            raise ConfigurationError('Unexpected domains')
        try:
            integers = {k: int(v[k]) for k in ('RU_TASKS_PER_DOMAIN', 'RU_SAMPLES_PER_TASK',
                       'RU_SEED', 'RU_MAX_OUTPUT_TOKENS', 'RU_MAX_CONCURRENT_REQUESTS',
                       'RU_REQUEST_TIMEOUT_SECONDS')}
            numbers = {k: Decimal(v[k]) for k in ('RU_TEMPERATURE', 'RU_TOP_P', 'RU_MAX_SPEND_RUB')}
        except (ValueError, InvalidOperation):
            raise ConfigurationError('Invalid numeric configuration') from None
        if any(not x.is_finite() for x in numbers.values()):
            raise ConfigurationError('Non-finite configuration')
        if any(x < 1 for k, x in integers.items() if k != 'RU_SEED') or integers['RU_SEED'] < 0:
            raise ConfigurationError('Invalid integer range')
        if not 0 <= numbers['RU_TEMPERATURE'] <= 2 or not 0 < numbers['RU_TOP_P'] <= 1:
            raise ConfigurationError('Invalid sampling range')
        if numbers['RU_MAX_SPEND_RUB'] <= 0 or integers['RU_MAX_OUTPUT_TOKENS'] > 8192:
            raise ConfigurationError('Invalid budget or stage-zero output ceiling')
        paths = {}
        base = Path(path).resolve().parent
        allowed = (base / '.research').resolve()
        for k in ('RU_RESEARCH_ROOT', 'RU_EPISTEME_ROOT', 'RU_CHECKPOINT_DIR'):
            target = (base / v[k]).resolve()
            if target == allowed or not target.is_relative_to(allowed):
                raise ConfigurationError('Research paths must be inside .research')
            paths[k] = target
        return cls(v['ROUTERAI_API_KEY'], v, numbers['RU_MAX_SPEND_RUB'],
                   integers['RU_MAX_OUTPUT_TOKENS'], integers['RU_REQUEST_TIMEOUT_SECONDS'],
                   integers['RU_SEED'], float(numbers['RU_TEMPERATURE']), float(numbers['RU_TOP_P']),
                   paths['RU_RESEARCH_ROOT'], paths['RU_EPISTEME_ROOT'])

    def public(self):
        return {k: v for k, v in self.values.items() if k != 'ROUTERAI_API_KEY'}
