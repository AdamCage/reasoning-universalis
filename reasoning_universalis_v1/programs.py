"""Frozen offline source trees; remote inference is never called by these programs."""
COMMON = '''import hashlib, json, pathlib, sys
if len(sys.argv) != 4 or sys.argv[2] != '--seed':
    raise SystemExit('expected INPUT --seed INDEX')
data=json.loads(pathlib.Path(sys.argv[1]).read_bytes())
index=int(sys.argv[3]); bundle=data['source_bundle']; root=bundle['roots'][index]
observations=[r for r in bundle['observations'] if next(t for t in bundle['tasks'] if t['task_id']==r['identity']['problem_id'])['root_id']==root]
segments=[s for s in bundle['segments'] if s['root_id']==root]
raw={'schema_version':1,'root_id':root,'roster_unit':index,'contrast':data['contrast'],
     'source_bundle_digest':data['source_bundle_digest'],'observations':observations,'segments':segments}
left,right=data['contrast'].split('-')
traces=sorted({s['trace_id'] for s in segments})
if not traces: raise SystemExit('missing eligible trace')
'''
PRIMARY = COMMON + '''values=[]
for trace in traces:
    rows=[s for s in segments if s['trace_id']==trace]
    if not {left,right}<={s['method'] for s in rows}: raise SystemExit('unpaired')
    values.append(sum(s['method']==left for s in rows)-sum(s['method']==right for s in rows))
value=sum(values)/len(values)
'''
REANALYSIS = """import json, pathlib, sys
from collections import Counter
if len(sys.argv)!=4 or sys.argv[2]!='--seed': raise SystemExit('expected INPUT --seed INDEX')
raw=json.loads(pathlib.Path(sys.argv[1]).read_bytes())
if raw['roster_unit']!=int(sys.argv[3]): raise SystemExit('foreign root index')
segments=raw['segments']; left,right=raw['contrast'].split('-')
traces=sorted({s['trace_id'] for s in segments})
if not traces: raise SystemExit('missing eligible trace')
counts={trace:Counter(s['method'] for s in segments if s['trace_id']==trace) for trace in traces}
if any(not {left,right}<=set(row) for row in counts.values()): raise SystemExit('unpaired')
value=float(sum(row[left]-row[right] for row in counts.values()))/len(traces)
"""
TAIL = '''pathlib.Path('raw.json').write_bytes(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
pathlib.Path('metrics.json').write_bytes(json.dumps({'segment_count_delta':value},sort_keys=True,separators=(',',':'),allow_nan=False).encode())
'''
PYPROJECT = b'[project]\nname = "reasoning-universalis-offline"\nversion = "0"\nrequires-python = ">=3.11"\ndependencies = []\n\n[tool.uv]\npackage = false\n'
UV_LOCK = b'version = 1\nrevision = 3\nrequires-python = ">=3.11"\n\n[[package]]\nname = "reasoning-universalis-offline"\nversion = "0"\nsource = { virtual = "." }\n'
