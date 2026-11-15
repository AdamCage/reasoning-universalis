"""Flatten prespecified metrics into CSV, reusing the frozen root-bootstrap kernel."""
from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cross_model.common import read, write, sha
from cross_model.analysis import comparison
from cross_model_compat import ARTIFACT
from machine_development.annotation import ROLES


def save(path, rows):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def metric_row(model,sample,metrics):
    row={'annotator':model,'sample':sample,**{k:metrics[k] for k in ('planned_items','valid_pairs','matches','invalid_or_unresolved','raw_agreement','cohen_kappa','agreement_over_planned','majority_label_baseline')}}
    for key,value in metrics.get('root_bootstrap',{}).get('metrics',{}).items():
        bounds=value['interval95']
        row[key+'_ci95_low']=bounds[0] if bounds else None
        row[key+'_ci95_high']=bounds[1] if bounds else None
        row[key+'_defined_bootstrap']=value['defined_replicates']
    return row


def main():
    base=ROOT/ARTIFACT;out=base/'analysis'
    s=read(out/'summary.json');rows=read(out/'item-level.json')['rows']
    overall=[];role_rows=[];strata=[];sources=[]
    for model,values in s['cross_family'].items():
        for sample,metrics in values.items():
            selected=[r for r in rows if sample=='pooled' or r['sample']==sample]
            overall.append(metric_row(model,sample,metrics))
            for role,value in metrics['roles'].items():
                boot=metrics['root_bootstrap']['role_agreement'][role];bounds=boot['interval95']
                role_rows.append({'annotator':model,'sample':sample,'reference_role':role,
                    'planned_reference_role_n':sum(r.get('reference_role')==role for r in selected),
                    'valid_reference_role_n':value['reference_n'],'matches':value['matches'],'conditional_agreement':value['agreement_given_reference'],
                    'ci95_low':bounds[0] if bounds else None,'ci95_high':bounds[1] if bounds else None,'defined_bootstrap':boot['defined_replicates']})
            for field,groups in metrics['strata'].items():
                for group,m in groups.items():
                    strata.append({'annotator':model,'sample':sample,'field':field,'group':group,
                        **{k:m[k] for k in ('planned_items','valid_pairs','matches','raw_agreement','cohen_kappa','agreement_over_planned')}})
            # Source-model strata were prespecified. Reuse the EXACT frozen
            # estimator/bootstrap, never a new statistical method or selected CI.
            for generator in sorted({r['source_model'] for r in selected}):
                group=[{**r,'new_role':r[model.replace('/','_')]} for r in selected if r['source_model']==generator]
                m=comparison(group,replicates=2000)
                sources.append({'source_model':generator,'root_blocks':len({r['root_id'] for r in group}),**metric_row(model,sample,m)})
    save(out/'agreement-with-intervals.csv',overall)
    save(out/'role-agreement-with-intervals.csv',role_rows)
    save(out/'source-model-agreement-with-intervals.csv',sources)
    save(out/'prespecified-strata.csv',strata)
    write(out/'table-provenance.json',{'script_sha256':sha(Path(__file__).read_bytes()),'summary_sha256':sha((out/'summary.json').read_bytes()),
        'source_CI_method':'Same frozen cross_model.analysis.comparison; whole roots within each prespecified source-model group,2000draws,seed20261115',
        'rows':{'overall':len(overall),'roles':len(role_rows),'source':len(sources),'strata':len(strata)},'labels_changed':False,'network_calls':0})
    print({'tables':4,'rows':len(overall)+len(role_rows)+len(sources)+len(strata),'network_calls':0})


if __name__=='__main__':main()
