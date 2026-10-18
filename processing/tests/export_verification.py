"""Private, static HTML/JSON map of saved model outputs and current templates."""
import argparse
import hashlib
import html
import json
from pathlib import Path
from corpus_inventory import read
from tabby_processing import normalize, templates, accounts, validation, correlation
from collections import Counter
from score_benchmark import equivalent


def main():
    p=argparse.ArgumentParser()
    p.add_argument('directory'); p.add_argument('results'); p.add_argument('expectations')
    p.add_argument('--output',required=True)
    p.add_argument('--account-register')
    a=p.parse_args(); out=Path(a.output).resolve()
    if 'exports' not in out.parts: raise ValueError('Use private exports directory')
    models={r['id']:r for r in map(json.loads,Path(a.results).read_text().splitlines())}
    gold=json.loads(Path(a.expectations).read_text())
    mappings=accounts.compile_register(json.loads(Path(a.account_register).read_text(encoding='utf-8-sig'))) if a.account_register else []
    rows=[]
    for path in sorted(Path(a.directory).glob('*.eml')):
        row=read(path); n=normalize.normalize(row['source']); saved=models.get(row['id'],{})
        match=None if n.issues else templates.parse(n.text,row['source']['message_date'])
        events=saved.get('facts',{}).get('events',[])
        rows.append(dict(id=row['id'],filename=path.name,subject=row['source']['subject'],
            email_body=row['preview'].partition('\n\n')[2],
            expected_classification=gold[row['id']]['classification'],
            model_fields=[{k:e.get(k) for k in ('transaction_amount','transaction_date','bank','event_type')} for e in events],
            model_output=saved.get('facts'),invalid_raw_output=saved.get('raw_output'),
            model_status=saved.get('status','not_run'),model_metadata=saved.get('metadata'),
            model_input_matches_current=saved.get('input_sha256')==hashlib.sha256(n.text.encode()).hexdigest(),
            template_output=match[0] if match else None,template_rule=match[1] if match else None,
            validation=[validation.validate(e,n.text,mappings,message_date=row['source']['message_date']) for e in match[0]['events']] if match else []))
    out.mkdir(parents=True,exist_ok=True)
    candidates=[{'id':r['id'],'facts':r['validation'][0]['effective_facts'],
                 'account_id':r['validation'][0]['account_id']} for r in rows if r['template_output']]
    comparisons=[]; fields=Counter(); correct=Counter()
    for r in rows:
        if not r['template_output']: continue
        e=r['validation'][0]['effective_facts']; differences=[]
        for k,want in gold[r['id']].get('fields',{}).items():
            got=e['transaction_amount'].get(k) if k in ('amount','currency') else e.get(k)
            fields[k]+=1
            if equivalent(k,want,got): correct[k]+=1
            else: differences.append({'field':k,'expected':want,'actual':got})
        if differences: comparisons.append({'id':r['id'],'differences':differences})
        r['relationships']=correlation.suggest(e,r['validation'][0]['account_id'],[c for c in candidates if c['id']!=r['id']])
    summary={'financial_events':len(candidates),'mapped':sum(bool(c['account_id']) for c in candidates),
             'fields':{k:{'correct':correct[k],'total':v} for k,v in fields.items()},
             'differences_from_frozen_expectations':comparisons,
             'review_reasons':dict(Counter(reason for r in rows for v in r['validation'] for reason in v['reasons'])),
             'relationships':dict(Counter(x['relationship'] for r in rows for x in r.get('relationships',[])))}
    (out/'validation-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (out/'output-map.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda s:html.escape(str(s))
    blocks=[]
    for i,r in enumerate(rows,1):
        blocks.append('<details><summary>'+esc(f'{i}. {r["subject"]} — {r["model_status"]}')+'</summary>'
          +'<p>Source SHA-256: '+esc(r['id'])+'</p><h3>Model extracted fields</h3><pre>'
          +esc(json.dumps(r['model_fields'],ensure_ascii=False,indent=2))+'</pre><h3>Email body (visible text)</h3><pre>'
          +esc(r['email_body'])+'</pre><h3>Saved model JSON</h3><pre>'
          +esc(json.dumps(r['model_output'],ensure_ascii=False,indent=2) if r['model_output'] is not None else r['invalid_raw_output'] or 'No model JSON available: '+r['model_status'])
          +'</pre><h3>Model provenance</h3><pre>'+esc(json.dumps(r['model_metadata'],indent=2))
          +'</pre><h3>Current deterministic output (separate)</h3><pre>'+esc(json.dumps(r['template_output'],ensure_ascii=False,indent=2))
          +'</pre><h3>Validation with confirmed mappings</h3><pre>'+esc(json.dumps(r['validation'],indent=2))
          +'</pre><h3>Possible related emails (review required)</h3><pre>'+esc(json.dumps(r.get('relationships',[]),indent=2))+'</pre></details>')
    (out/'output-map.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Private email verification</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:16px}details{border-bottom:1px solid #ccc;padding:12px}summary{cursor:pointer}</style><h1>Private email verification — 264-email corpus</h1><p>Saved baseline model outputs, not a new model run. Valid JSON is reserialized from saved parsed output; original response whitespace was not retained. Missing/refused outputs are explicit. Deterministic results are shown separately. Bodies are visible text, without active HTML or attachments.</p>'+''.join(blocks),encoding='utf-8')
    print(json.dumps({'rows':len(rows),'template_matches':sum(bool(r['template_rule']) for r in rows),
        'negative_template_matches':sum(bool(r['template_rule']) and r['expected_classification']=='non_transaction' for r in rows),
        'financial_without_template':sum(not r['template_rule'] and r['expected_classification']=='transaction' for r in rows)}))

if __name__=='__main__': main()
