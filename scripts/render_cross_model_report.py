"""Render a three-page English report and standalone figures from keyless analysis."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cross_model.common import read, write, rank, sha
from cross_model_compat import ARTIFACT, PROTOCOL
from machine_development.annotation import ROLES

NAMES = {"qwen/qwen3-32b": "Qwen3-32B", "openai/gpt-oss-20b": "GPT-OSS-20B"}
ABBR = dict(zip(ROLES, ("PF", "PL", "DC", "EX", "VE", "UN", "BC", "CO", "AO")))
SHORT = dict(zip(ROLES, ("Formulation", "Planning", "Deduction", "Exploration", "Verification", "Uncertainty", "Correction", "Conclusion", "Ambiguous")))
COLORS = ("#176b87", "#b3562d")


def fmt(value, digits=3):
    return f"{value:.{digits}f}" if value is not None else "undefined"


def pct(value):
    return f"{value*100:.1f}%" if value is not None else "undefined"


def ci(metrics, key):
    interval = metrics["root_bootstrap"]["metrics"][key]["interval95"]
    return f"[{fmt(interval[0])}, {fmt(interval[1])}]" if interval else "undefined"


def short_interval(value):
    return '['+fmt(value[0])+', '+fmt(value[1])+']' if value else 'undefined'


def figures(summary, rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.facecolor": "white"})
    output.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.5), layout="constrained")
    for ax, key, title in zip(axes, ("raw_agreement", "cohen_kappa"), ("Agreement with DeepSeek consensus", "Chance-corrected agreement")):
        for index, model in enumerate(NAMES):
            values=summary["cross_family"][model]
            for y, sample in enumerate(("core", "challenge", "pooled")):
                m = values[sample]
                value = m[key]
                interval = m["root_bootstrap"]["metrics"][key]["interval95"]
                if value is not None:
                    error = np.array([[value-interval[0]], [interval[1]-value]]) if interval else None
                    ax.errorbar(value, y+(index-.5)*.2, xerr=error, fmt="o", color=COLORS[index], capsize=3,
                                label=NAMES[model] if y==0 else None)
                if key=="raw_agreement" and m["majority_label_baseline"] is not None:
                    ax.scatter(m["majority_label_baseline"], y+(index-.5)*.2, marker="x", color=COLORS[index], alpha=.55)
        ax.set_yticks(range(3), ("Core (48)", "Challenge (24)", "Enriched pool (72)"))
        ax.invert_yaxis(); ax.set_xlim(-.05 if key=="cohen_kappa" else 0, 1.04)
        ax.grid(axis="x", alpha=.2); ax.set_title(title, fontsize=10)
        ax.set_xlabel("Cohen's kappa" if key=="cohen_kappa" else "Both-valid-pair proportion (x: majority baseline)")
    axes[0].legend(loc="lower left", fontsize=8)
    fig.savefig(output / "agreement.png", dpi=220); fig.savefig(output / "agreement.pdf"); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.3), layout="constrained")
    for ax, model in zip(axes, NAMES):
        values=summary["cross_family"][model]
        m = values["pooled"]
        matrix = np.array([[m["confusion_matrix"][r][c] for c in ROLES] for r in ROLES])
        ax.imshow(matrix, cmap="Blues", vmin=0, vmax=max(1, matrix.max()))
        for y in range(9):
            for x in range(9):
                if matrix[y,x]:
                    ax.text(x,y,str(matrix[y,x]),ha="center",va="center",fontsize=8,color="white" if matrix[y,x]>matrix.max()*.6 else "#152b3c")
        ax.set_xticks(range(9), [ABBR[r] for r in ROLES]); ax.set_yticks(range(9), [ABBR[r] for r in ROLES])
        ax.set_xlabel(NAMES[model]+" role"); ax.set_ylabel("DeepSeek reference role")
        ax.set_title(f"{NAMES[model]}: {m['matches']}/{m['valid_pairs']} pairs",fontsize=10)
    fig.savefig(output / "confusion.png", dpi=220); fig.savefig(output / "confusion.pdf"); plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(9.2, 2.9), layout="constrained")
    for i,model in enumerate(NAMES):
        values=summary["cross_family"][model]
        name, color = NAMES[model], COLORS[i]
        a=summary["context_ablation"][model]
        change=a["changed_labels"]/a["paired_valid"] if a["paired_valid"] else 0
        axes[0].barh(i,change,color=color,height=.5)
        axes[0].text(change+.02,i,f"{a['changed_labels']}/{a['paired_valid']}",va="center",fontsize=8)
        gap=summary["paired_instrument_gap"][model]["core"]
        point, interval=gap["same_minus_cross_agreement"],gap["root_bootstrap"]["interval95"]
        if point is not None:
            axes[1].errorbar(point,i,xerr=[[point-interval[0]],[interval[1]-point]] if interval else None,fmt="o",color=color,capsize=3)
        strata=values["pooled"]["strata"]["length_bin"]
        for x,k in enumerate(("01:<=50","02:51-150","03:>150")):
            m=strata.get(k,{})
            if m.get("raw_agreement") is not None:
                axes[2].plot(x,m["raw_agreement"],"o",color=color)
                axes[2].annotate(str(m["valid_pairs"]),(x,m["raw_agreement"]),xytext=(3,4 if i==0 else -10),textcoords="offset points",fontsize=7,color=color)
    for ax in axes[:2]:
        ax.set_yticks(range(2), list(NAMES.values()),fontsize=8); ax.invert_yaxis(); ax.grid(axis="x",alpha=.2)
    axes[0].set_xlim(0,1.1);axes[0].set_title("Label change without context",fontsize=9);axes[0].set_xlabel("Changed / paired valid (24 planned)",fontsize=8)
    axes[1].axvline(0,color="grey",ls="--",lw=.8);axes[1].set_title("Same-minus-cross agreement",fontsize=9);axes[1].set_xlabel("Held-out DeepSeek comparator, core",fontsize=8)
    axes[2].set_xticks(range(3),("<=50","51-150",">150"));axes[2].set_ylim(-.02,1.05);axes[2].set_title("Segment-length dependence",fontsize=9);axes[2].set_xlabel("Unicode characters (labels: valid N)",fontsize=8)
    fig.savefig(output / "sensitivity.png",dpi=220);fig.savefig(output / "sensitivity.pdf");plt.close(fig)


def examples(summary, rows, base):
    inputs={i['item_id']:i for i in read(base/'input-items.json')['items']}
    chosen=[]
    for model in NAMES:
        key=model.replace('/','_')
        mismatches=[r for r in rows if r.get('reference_role') in ROLES and r.get(key) in ROLES and r['reference_role']!=r[key]]
        transitions=Counter((r['reference_role'],r[key]) for r in mismatches)
        ordered=sorted(transitions,key=lambda pair:(-transitions[pair],ROLES.index(pair[0]),ROLES.index(pair[1])))[:3]
        for pair in ordered:
            item=min((r for r in mismatches if (r['reference_role'],r[key])==pair),key=lambda r:(rank('disagreement-example',r['item_id']),r['item_id']))
            chosen.append({'model':model,'item_id':item['item_id'],'root_id':item['root_id'],'sample':item['sample'],
                'reference_role':pair[0],'new_role':pair[1],'transition_count':transitions[pair],
                'current_text':inputs[item['item_id']]['current_segment']['text'],
                'past_context':inputs[item['item_id']]['previous_segments'],
                'char_start':item['char_start'],'char_end':item['char_end']})
    write(base/'analysis/disagreement-examples.json',{'selection':'Top 3 off-diagonal transitions/model by count, ties ontology order; versioned hash minimum within transition','examples':chosen})
    return chosen


def markdown(summary, rows, base, selected):
    quote=read(base/'cost-quote.json');budget=read(base/'budget-final.json')
    lines=['# Cross-family portability of visible-reasoning role labels', '',
           'Exploratory measurement pilot | 15 November 2026 | 24 development task roots', '',
           '## Question and design', '',
           'Do functional role labels survive a change of annotation instrument? We reuse a frozen nine-role ontology and 72 published segments: a label-blind 48-item core (two per root) plus a separately reported 24-item challenge sample (one per root) enriched for rare prior machine labels and unresolved cases. The pool covers four task domains and two source-generator models. Existing DeepSeek multiseed consensus is a comparison instrument, never ground truth.', '',
           'Qwen3-32B and GPT-OSS-20B are pinned to DeepInfra through RouterAI. Each receives the original task, current segment and allowed past context, without source identity, previous labels, correctness or future text. A paired context-removal condition uses one hash-selected core segment per root (24 per model). All 200 parent items contain context; there is no observational no-context comparison.', '',
           '## Results', '',
           '| Instrument | Sample | Matches / valid / planned | Raw agreement [95% root CI] | Cohen kappa [95% root CI] | Majority baseline |',
           '|---|---|---:|---|---|---:|']
    for model in NAMES:
        values=summary['cross_family'][model]
        for sample in ('core','challenge','pooled'):
            m=values[sample]
            lines.append(f"| {NAMES[model]} | {sample} | {m['matches']} / {m['valid_pairs']} / {m['planned_items']} | {fmt(m['raw_agreement'])} {ci(m,'raw_agreement')} | {fmt(m['cohen_kappa'])} {ci(m,'cohen_kappa')} | {fmt(m['majority_label_baseline'])} |")
    lines += ['', 'The primary result is limited transfer of this measurement configuration: both new instruments fall below their descriptive majority-label baseline on the core, despite positive chance-corrected agreement. The enriched challenge reverses the apparent ranking of the instruments, showing why a single pooled headline would be misleading.', '',
              '![Agreement](../'+ARTIFACT+'/figures/agreement.png)', '',
              'Intervals resample complete task-root blocks with replacement (2,000 draws; seed 20261115). Invalid/new-missing and unresolved-reference cases remain in the planned denominator; both-valid agreement is accompanied by matches/all-planned in the machine-readable tables. `ambiguous_other` is a valid ninth category. Challenge and pooled estimates describe an enriched sample, not natural role prevalence.', '',
              '## Role sensitivity and disagreements', '',
              '![Confusion matrices](../'+ARTIFACT+'/figures/confusion.png)', '',
              '| Prior machine role | Qwen matches / valid reference-role N | GPT-OSS matches / valid reference-role N |', '|---|---:|---:|']
    for role in ROLES:
        vals=[summary['cross_family'][model]['pooled']['roles'][role] for model in NAMES]
        planned=sum(r.get('reference_role')==role for r in rows)
        lines.append(f"| {role} (planned N={planned}) | {vals[0]['matches']} / {vals[0]['reference_n']} | {vals[1]['matches']} / {vals[1]['reference_n']} |")
    lines += ['', 'The largest Qwen transition is prior deduction/computation to ambiguous/other (12/28 valid reference-deduction cases). GPT-OSS retains none of five valid prior exploration labels. These are instrument-dependent boundaries, not adjudicated annotation errors. Role-specific missingness matters: for example, only three of six prior verification items are valid GPT-OSS pairs; all six are valid Qwen pairs.']
    lines+=['','Examples are chosen mechanically from the three most frequent off-diagonal transitions per instrument; within each transition the lowest versioned hash is shown. They illustrate instrument disagreement and do not adjudicate which label is correct.','']
    for e in selected:
        text=e['current_text'].replace('\r','\\r').replace('\n','\\n')
        lines.append(f"- {NAMES[e['model']]}: `{e['reference_role']}` -> `{e['new_role']}` (transition N={e['transition_count']}; item `{e['item_id']}`): {text}")
    lines+=['','## Context and same-model controls','','![Sensitivity](../'+ARTIFACT+'/figures/sensitivity.png)','']
    for model in NAMES:
        a=summary['context_ablation'][model];g=summary['paired_instrument_gap'][model]['core']
        lines.append(f"{NAMES[model]} changes {a['changed_labels']}/{a['paired_valid']} paired-valid labels without past context (24 planned); full-minus-ablated agreement with the prior machine reference is {fmt(a['full_minus_ablated_reference_agreement'])}. On {g['matched_valid']} common valid core rows, held-out DeepSeek vote0 versus the other-four majority exceeds new-instrument agreement with that same reference by {fmt(g['same_minus_cross_agreement'])} (95% root CI {short_interval(g['root_bootstrap']['interval95'])}).")
    pair=summary['cross_family_pair']['core']
    lines += ['',f"Direct Qwen/GPT-OSS agreement on the core is {pair['matches']}/{pair['valid_pairs']} valid pairs, kappa {fmt(pair['cohen_kappa'])}. The held-out comparator excludes vote 0 from its own reference and requires at least 3 of 4 other votes; incomplete or tied panels stay unresolved. This avoids the circular control of comparing a vote with a consensus that includes it. It does not equate single-call and multiseed instruments.", '',
              'Source-model, domain, segment-length, context-length and original-unanimity strata, per-role intervals, undefined bootstrap counts, all planned cells and exact quotes are supplied in the JSON/CSV artifacts. There is only one segment longer than 150 characters and neither instrument produces a valid pair for it; 71 of 72 contexts are at most 250 characters. Consequently length/context-length dependence is weakly identified here. One draw per context condition confounds context sensitivity with sampling variation.', '',
              '## Technical outcome and limitations', '',
              'The initial two constructed schema probes failed before any study segment was sent: DeepInfra Qwen rejected `uniqueItems` in its grammar; GPT-OSS rejected disabled reasoning. One immutable premeasurement transport addendum removed only the unsupported grammar keyword while retaining the complete local schema, and enabled mandatory low-effort GPT-OSS reasoning. The first scheduled study item admitted each route. No unsuccessful study item was repeated, no segment was added, and the original 194-call ceiling includes the failed probes. Raw error responses are retained.', '',
              'A separate post-run output-contract audit finds that all 26 invalid outputs pass the supplied JSON schemas but fail additional unchanged local rules: 13 repeat the primary role in secondary_roles (Qwen 5, GPT 8), 12 quote text absent from the current segment (Qwen 5, GPT 7), and 1 uses the wrong evidence source ID (Qwen). The primary/secondary exclusion is not expressed in the supplied schema or explicitly stated in the system prompt; exact evidence matching is explicitly stated. This separates structured JSON compliance from admissible measurement evidence. No label is repaired or rescued from these invalid objects. All 192 raw-response replays reproduce the recorded status and vote exactly.', '',
              f"Active-condition technical statuses: {summary.get('technical_status_counts')}. Qwen has 65/72 valid full-context outputs and 20/24 valid ablations; GPT-OSS has 60/72 and 21/24, respectively. Four of 72 prior references are unresolved. Additional active-condition charged-or-reserved commitments: {float(budget['additional_charged_or_reserved_rub']):.2f} RUB; plus the initial 0.91 RUB failed-probe reserve. Combined shared ledger: {float(budget['charged_or_reserved_rub']):.2f} RUB. These conservative commitments retain unknown charges and exceed API-reported costs; they are not a final billing statement.", '',
              'This is an exposed development sample with 24 root clusters, sparse roles and an enriched challenge portion. Estimates cannot establish ontology validity, correctness, human agreement, faithful internal states or broad model universality. There is no human gold and E0 remains unpassed. Qwen and GPT-OSS share a provider; DeepSeek used BytePlus. Provider weight revisions/quantization are unknown. Structured decoding differs from the parent transport; GPT-OSS mandatory reasoning and model family are confounded. A weak result is evidence against immediate portability of this measurement configuration, not proof that functional structure does not exist.', '',
              '## Reproduction and next study', '',
              'Run `python scripts/reproduce_cross_model_compat.py` without an API key to check immutable inputs/raw responses and regenerate the primary analysis; `python scripts/tabulate_cross_model.py` writes the overall, role, source-model and prespecified-strata CSV tables, including intervals. `python scripts/audit_cross_model_outputs.py` reproduces the output-contract audit. Run `python scripts/render_cross_model_report.py` for figures and the three-page PDF. Tests cover unchanged parent data, Unicode offsets, whole-root bootstrap, invalid outputs, label leakage, reservations and no-repeat behavior.', '',
              'The next study should first make every local output constraint explicit to all instruments, then freeze disputed role boundaries and collect genuinely independent human judgments plus repeated full/ablated annotations on the same roots. This separates contract compliance, instrument stochasticity, context sensitivity and codebook ambiguity before a larger confirmatory corpus. No E0 acceptance or generation-stage release follows from this pilot.', '',
              'Model-license receipts: [Qwen official Apache 2.0 license](https://huggingface.co/Qwen/Qwen3-32B/raw/main/LICENSE), [GPT-OSS official Apache 2.0 license](https://huggingface.co/openai/gpt-oss-20b/raw/main/LICENSE). RouterAI route/capability/pricing receipts and the exact versioned source are archived.', '',
              f"Frozen scientific protocol: `design/CROSS_MODEL_PROTOCOL_2026_11_15.json`; transport addendum: `{PROTOCOL}`. Complete inputs, raw calls, run metadata and tables: `{ARTIFACT}`."]
    (ROOT/'reports/CROSS_MODEL_MEASUREMENT_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def pdf(summary, rows, base, selected):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from matplotlib import font_manager
    font=font_manager.findfont('DejaVu Sans')
    bold=font_manager.findfont(font_manager.FontProperties(family='DejaVu Sans',weight='bold'))
    pdfmetrics.registerFont(TTFont('DejaVu',font));pdfmetrics.registerFont(TTFont('DejaVuBold',bold))
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyPilot',fontName='DejaVu',fontSize=8.5,leading=11.8,spaceAfter=6,textColor=colors.HexColor('#203044')))
    styles.add(ParagraphStyle(name='SmallPilot',parent=styles['BodyPilot'],fontSize=7.1,leading=9.5,spaceAfter=4))
    styles.add(ParagraphStyle(name='TitlePilot',fontName='DejaVuBold',fontSize=19,leading=23,spaceAfter=9,textColor=colors.HexColor('#123a53')))
    styles.add(ParagraphStyle(name='HeadingPilot',fontName='DejaVuBold',fontSize=10.5,leading=14,spaceBefore=7,spaceAfter=6,textColor=colors.HexColor('#123a53')))
    p=lambda text,small=False:Paragraph(text,styles['SmallPilot' if small else 'BodyPilot'])
    h=lambda text:Paragraph(text,styles['HeadingPilot'])
    def table(data,widths):
        data=[[p(escape(str(v)),True) for v in row] for row in data]
        t=Table(data,colWidths=widths,hAlign='LEFT',repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf0f4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#7595aa')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#dce5ec')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        return t
    fig=base/'figures';story=[];width=A4[0]-76
    story += [Paragraph('Cross-family portability of visible-reasoning role labels',styles['TitlePilot']),
              p('EXPLORATORY MEASUREMENT PILOT  |  15 NOVEMBER 2026  |  24 DEVELOPMENT ROOTS',True),
              p('We test whether a frozen functional-role codebook transfers from a multiseed DeepSeek annotation instrument to Qwen3-32B and GPT-OSS-20B. Agreement measures portability of observable-text labels; the old consensus is not ground truth. There is no human gold, and E0 remains unpassed.'),
              h('1  Primary comparison: core and enriched sample kept separate')]
    data=[['Instrument / sample','Match / valid / plan','Raw [95% root CI]','Kappa [95% root CI]','Majority']]
    for model in NAMES:
        values=summary['cross_family'][model]
        for sample in ('core','challenge','pooled'):
            m=values[sample]
            data.append([NAMES[model]+' / '+sample,f"{m['matches']} / {m['valid_pairs']} / {m['planned_items']}",fmt(m['raw_agreement'])+' '+ci(m,'raw_agreement'),fmt(m['cohen_kappa'])+' '+ci(m,'cohen_kappa'),fmt(m['majority_label_baseline'])])
    story += [table(data,[116,86,126,126,width-454]),Spacer(1,7),Image(str(fig/'agreement.png'),width=width,height=width*3.5/9.2),
              p('Bars: 95% percentile intervals from 2,000 whole-root bootstrap draws. Crosses: descriptive majority-reference-label baseline on valid pairs. Pairwise agreement excludes invalid/unresolved pairs only from its valid-pair denominator; matches/all-planned is also retained in the artifact tables.',True),
              p('<b>Negative portability result:</b> on the core, both instruments fall below the descriptive majority-label baseline, despite positive kappa. The challenge reverses their apparent ranking; pooling alone would obscure the selection effect. High same-DeepSeek agreement does not establish transfer across these measurement configurations.'),
              h('Design before new study outputs'),
              p('The 72 unique segments contain three per original task root: 48 core items selected by a fixed hash without labels (two/root), and 24 challenge items chosen for rare prior roles and unresolved cases (one/root). All nine roles, four domains and both source generators are covered. Challenge and pooled results are enriched-sample summaries, not prevalence estimates.'),
              p('The task, current segment and permitted past context are copied exactly, with original Unicode offsets kept coordinator-side. No old labels, correctness, generator identity or future segments are shown. One stateless call per model/item/condition; strict JSON and literal current-segment quotes; no unsuccessful study-case repeats.',True),PageBreak()]
    story += [h('2  Where labels change between instruments'),Image(str(fig/'confusion.png'),width=width,height=width*4.3/9.2),
              p('Enriched pool; numbers are counts on both-valid pairs, not accuracy. PF formulation; PL planning; DC deduction/computation; EX exploration; VE verification; UN uncertainty; BC correction; CO conclusion; AO ambiguous/other.',True)]
    roledata=[['Prior machine role','Qwen match / role N','GPT-OSS match / role N']]
    for role in ROLES:
        vals=[summary['cross_family'][model]['pooled']['roles'][role] for model in NAMES]
        planned=sum(r.get('reference_role')==role for r in rows)
        roledata.append([SHORT[role]+f' (planned {planned})',f"{vals[0]['matches']} / {vals[0]['reference_n']}",f"{vals[1]['matches']} / {vals[1]['reference_n']}"])
    story += [table(roledata,[width*.43,width*.285,width*.285]),Spacer(1,6),
              p('Qwen moves 12/28 valid prior deduction cases to ambiguous/other; GPT-OSS retains 0/5 prior exploration labels. These are disputed boundaries, not adjudicated errors. Per-role intervals and undefined draws are in JSON. N=1 cannot support a general portability claim.',True),h('Mechanically selected disagreements')]
    # One example per instrument in the short report; all six in the appendix.
    for model in NAMES:
        example=next((e for e in selected if e['model']==model),None)
        if example:
            text=example['current_text'].strip().replace('\n',' ')
            if len(text)>190:text=text[:190]+'...'
            story.append(p(f"<b>{NAMES[model]}</b>, {ABBR[example['reference_role']]} to {ABBR[example['new_role']]} (transition N={example['transition_count']}): &quot;{escape(text)}&quot;",True))
    story += [p('Selection: most frequent off-diagonal transition per model, then lowest fixed hash; all top-three transitions/model and full exact texts are archived. Examples show disagreement, not which annotator is right.',True),PageBreak()]
    story += [h('3  Context sensitivity and a non-circular control'),Image(str(fig/'sensitivity.png'),width=width,height=width*2.9/9.2)]
    for model in NAMES:
        a=summary['context_ablation'][model];g=summary['paired_instrument_gap'][model]['core']
        story.append(p(f"<b>{NAMES[model]}:</b> {a['changed_labels']}/{a['paired_valid']} paired-valid labels change when past context is removed (24 planned). Full-minus-ablated agreement with the machine reference: {fmt(a['full_minus_ablated_reference_agreement'])}. Held-out same-minus-cross agreement on {g['matched_valid']} core rows: {fmt(g['same_minus_cross_agreement'])}; 95% root CI {short_interval(g['root_bootstrap']['interval95'])}.",True))
    pair=summary['cross_family_pair']['core']
    story += [p(f"Direct Qwen/GPT-OSS core agreement: {pair['matches']}/{pair['valid_pairs']}, kappa {fmt(pair['cohen_kappa'])}. The held-out control compares vote 0 with at least 3 of 4 other DeepSeek votes; vote 0 never contributes to its reference. Tied/incomplete panels stay unresolved. All 200 parent items contain context; one call/condition confounds context removal with sampling variation. Length support is limited: only 1 segment exceeds 150 characters (no valid pair), and 71/72 contexts are at most 250 characters.",True),
              h('Technical outcome and scientific limits'),
              p('The 192 study calls produce 166 valid and 26 invalid outputs: Qwen 65/72 full-context and 20/24 ablated; GPT-OSS 60/72 and 21/24. Four prior references are unresolved. Two initial probes failed before study dispatch: unsupported uniqueItems grammar for Qwen, and mandatory reasoning for GPT-OSS. An immutable premeasurement addendum retains complete local validation and enables mandatory low-effort GPT-OSS reasoning. First study items admit each route. The total 194-call ceiling includes failed probes; no failed study case is repeated.',True),
              p('<b>Output-contract finding:</b> all 26 invalid objects pass the supplied JSON schemas but violate unchanged local rules: 13 repeat primary in secondary roles, 12 have a nonliteral current-segment quote, and 1 has the wrong quote source. The primary/secondary exclusion is absent from the supplied schema and not explicit in the system prompt. Evidence matching is explicit. Thus JSON compliance and admissible measurement evidence are distinct. No invalid label is repaired or rescued.',True),
              p('This is an exposed development sample with only 24 root clusters and sparse roles. Machine agreement cannot establish ontology validity, correctness, independent human agreement, internal cognitive states or broad model universality. E0 remains unpassed. Shared provider infrastructure, unverified weight revisions/quantization, parent-versus-new structured decoding, and mandatory GPT-OSS reasoning are instrument confounds. Length associations and enriched role comparisons are descriptive.',True)]
    budget=read(base/'budget-final.json')
    story += [p(f"Shared charged-or-reserved ledger: {float(budget['charged_or_reserved_rub']):.2f} RUB; active-condition increase {float(budget['additional_charged_or_reserved_rub']):.2f} RUB plus initial failed-probe reserve 0.91 RUB. These are conservative commitments, not final billing. API-reported active cost: {float(budget['reported_new_cost_rub']):.2f} RUB.",True),
              h('Reproduction and next experiment'),
              p('python scripts/reproduce_cross_model_compat.py regenerates the primary analysis without API access and validates original inputs/raw responses. scripts/tabulate_cross_model.py writes the CSV tables and source/role intervals; scripts/audit_cross_model_outputs.py repeats the contract audit. All outputs, exact disagreements and run metadata are in artifacts/cross-model-compat-2026-11-15. Protocols are immutable; old experiments are unchanged.',True),
              p('Next: state every local output constraint explicitly, freeze disputed role boundaries, obtain independent human judgments, and repeat matched full/ablated calls on the same roots. This separates contract compliance, codebook ambiguity, stochasticity and context dependence before a confirmatory corpus. No E0 or generation stage is released.',True),
              p('Sources: official Qwen3-32B and openai/gpt-oss-20b Apache 2.0 LICENSE pages (Hugging Face); archived RouterAI endpoint/capability/pricing receipts. Full links and protocol hashes are in the accompanying Markdown report.',True)]
    output=ROOT/'output/pdf/cross-model-measurement-pilot.pdf';output.parent.mkdir(parents=True,exist_ok=True)
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#b8c9d5'));canvas.line(38,34,A4[0]-38,34)
        canvas.setFont('DejaVu',7);canvas.setFillColor(colors.HexColor('#5a6e7e'))
        canvas.drawString(38,23,'Reasoning Universalis | Exploratory instrument portability | No human gold')
        canvas.drawRightString(A4[0]-38,23,str(doc.page))
    doc=SimpleDocTemplate(str(output),pagesize=A4,rightMargin=38,leftMargin=38,topMargin=34,bottomMargin=44,
                          title='Cross-family portability of visible-reasoning role labels',author='Reasoning Universalis')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    import fitz
    check=fitz.open(output)
    if len(check)!=3:
        raise ValueError(f'Report must have3pages; got{len(check)}')
    preview=ROOT/'tmp/pdfs/cross-model';preview.mkdir(parents=True,exist_ok=True)
    for i,page in enumerate(check):page.get_pixmap(matrix=fitz.Matrix(1.35,1.35)).save(preview/f'page-{i+1}.png')
    print({'pdf':str(output),'pages':len(check),'preview':str(preview)})


def main():
    base=ROOT/ARTIFACT
    summary=read(base/'analysis/summary.json');rows=read(base/'analysis/item-level.json')['rows']
    if not summary.get('cross_family'):
        raise ValueError('No measured cross-family analysis available; do not fabricate a report')
    figures(summary,rows,base/'figures')
    selected=examples(summary,rows,base)
    markdown(summary,rows,base,selected)
    pdf(summary,rows,base,selected)


if __name__=='__main__':main()
