"""Inspect explicit provider fields, never reconstruct reasoning from answers."""
import math
import re


def inspect_trace(response):
    choices = response.get('choices', [])
    if not choices:
        return {'status': 'unavailable', 'trace': '', 'answer': '', 'source': None,
                'full_visible_trace': False, 'finish_reason': None}
    choice = choices[0]
    message = choice.get('message') or {}
    answer = message.get('content') or ''
    text, source = '', None
    details = message.get('reasoning_details') or []
    has_summary = any('summary' in str(d.get('type', '')) for d in details)
    for key in ('reasoning', 'reasoning_content'):
        if isinstance(message.get(key), str) and message[key].strip():
            text, source = message[key], key
            break
    if not text:
        chunks = [d['text'] for d in details if d.get('type') == 'reasoning.text' and d.get('text')]
        if chunks:
            text, source = '\n'.join(chunks), 'reasoning_details.reasoning.text'
    # An explicit delimited stream is distinguishable from post-hoc explanation.
    if not text and isinstance(answer, str):
        match = re.search(r'<think>(.*?)</think>', answer, re.S)
        if match:
            text, source = match.group(1), 'content.think_tags'
            answer = answer[match.end():].strip()
    finish = choice.get('finish_reason')
    encrypted = any(d.get('type') == 'reasoning.encrypted' for d in details)
    if text and finish == 'stop' and not has_summary and not encrypted:
        status = 'visible_trace_candidate'
    elif text:
        status = 'summary_or_truncated_or_unfinished'
    elif has_summary:
        status = 'summary_only'
    elif encrypted:
        status = 'encrypted_only'
    else:
        status = 'answer_only'
    # Human inspection + provider evidence must separately establish completeness.
    return {'status': status, 'trace': text, 'answer': answer, 'source': source,
            'finish_reason': finish, 'full_visible_trace': False,
            'trace_characters': len(text), 'summary_present': has_summary}


def inspect_embeddings(response, model, count):
    if model not in ('baai/bge-m3', 'qwen/qwen3-embedding-8b') or str(response.get('model', '')).casefold() != model.casefold():
        return {'valid': False, 'dimensions': [], 'reason': 'embedding model mismatch'}
    if response.get('error') is not None:
        return {'valid': False, 'dimensions': [], 'reason': 'API error'}
    data = response.get('data', [])
    if not isinstance(data, list) or count < 1 or len(data) != count or any(
            not isinstance(d, dict) or type(d.get('index')) is not int for d in data) or sorted(d['index'] for d in data) != list(range(count)):
        return {'valid': False, 'dimensions': [], 'reason': 'missing or duplicate rows'}
    vectors = [d.get('embedding') for d in data]
    if any(not isinstance(v, list) or not v or any(isinstance(x, bool) or
           not isinstance(x, (int, float)) or not math.isfinite(x) for x in v) for v in vectors):
        return {'valid': False, 'dimensions': [], 'reason': 'non-finite or invalid vectors'}
    dimensions = [len(v) for v in vectors]
    valid = len(set(dimensions)) == 1 and (dimensions[0] == 1024 if model == 'baai/bge-m3'
                                         else 0 < dimensions[0] <= 4096)
    return {'valid': valid, 'dimensions': dimensions}


def segment(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]
