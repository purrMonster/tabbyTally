"""Build a private, reproducible review sample without treating generated labels as truth."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path
import re
from tabby_processing.parties import describe

LABEL_STATUS = 'unverified (model-generated)'


def choose(rows, count=25):
    selected=[]; used=set()
    def take(row):
        if row['id'] not in used and len(selected)<count:
            selected.append(row); used.add(row['id'])
    ordered=sorted(rows,key=lambda r:r['id'])
    for rule in sorted({r['template_rule'] for r in rows if r['template_rule']}):
        take(next(r for r in ordered if r['template_rule']==rule))
    missing=next((r for r in ordered if r['model_status']=='input_review'),None)
    if missing: take(missing)
    # Include operational, promotional, OTP and statement negatives explicitly.
    negatives=[r for r in ordered if r['expected_classification']=='non_transaction']
    for pattern in ('OTP','Statement','SmartEMI','No Dues','Reminder','pre-approved','Application','Account update'):
        row=next((r for r in negatives if r['id'] not in used and re.search(pattern,r['subject'],re.I)),None)
        if row: take(row)
    for row in negatives+ordered: take(row)
    return selected


def build(directory):
    directory=Path(directory)
    if 'exports' not in directory.resolve().parts: raise ValueError('Use private exports directory')
    rows=json.loads((directory/'output-map.json').read_text(encoding='utf-8'))
    selected=choose(rows)
    if len(selected)!=25: raise ValueError('Expected 25 distinct review rows')
    responses=directory/'review-sample-responses.json'
    previous=json.loads(responses.read_text(encoding='utf-8')) if responses.exists() else []
    confirmations={r['source_id']:r for r in previous}
    labels=[]; blocks=[]
    esc=lambda value:html.escape(str(value))
    for i,row in enumerate(selected,1):
        current=row['validation'][0] if row['validation'] else None
        effective=current['effective_facts'] if current else None
        fields={key:effective.get(key) for key in ('transaction_amount','transaction_date','bank','product','account_identifier','direction','event_type')} if effective else {'classification':(row.get('model_output') or {}).get('classification',row['model_status'])}
        fields.update(describe(effective))
        if effective: fields['merchant_counterparty_raw']=effective.get('merchant')
        labels.append({'row':i,'source_id':row['id'],'label_status':LABEL_STATUS,
                       'user_checked':False,'user_agrees':None,'corrections':None})
        status='User checked previously displayed fields; recipient/sender awaiting verification' if confirmations.get(row['id'],{}).get('user_checked') else LABEL_STATUS
        blocks.append(f'<section><h2>Row {i}: {esc(row["subject"])}</h2><p>{esc(row["template_rule"] or "model / input review")} · {status}</p>'
            +'<div class="pair"><div><h3>Source email</h3><pre>'+esc(row['email_body'] or '[No readable body]')+'</pre></div>'
            +'<div><h3>Current extracted fields</h3><pre>'+esc(json.dumps(fields,ensure_ascii=False,indent=2))+'</pre>'
            +'<h3>Labelled fallbacks</h3><pre>'+esc(json.dumps(current.get('fallbacks',[]) if current else [],indent=2))+'</pre>'
            +'<h3>Saved model fields (separate)</h3><pre>'+esc(json.dumps(row['model_fields'],ensure_ascii=False,indent=2))+'</pre></div></div>'
            +'<details><summary>Saved model JSON</summary><pre>'+esc(json.dumps(row.get('model_output'),ensure_ascii=False,indent=2))+'</pre></details>'
            +'<p>Reply: “Row '+str(i)+' correct”, or specify corrected fields. Nothing is pre-approved.</p></section>')
    template_matches=sum(bool(r['template_rule']) for r in rows)
    metrics={'format_coverage':{'template_matches':template_matches,'all_emails':len(rows)},
             'agreement_with_unverified_labels':{'label_status':LABEL_STATUS,'source':'validation-summary.json'},
             'agreement_with_user_checked_labels':{'checked':0,'agreement':None,'status':'not measured'},
             'sample':{'rows':len(selected),'template_rules':len({r['template_rule'] for r in selected if r['template_rule']}),
                       'classifications':dict(Counter(r['expected_classification'] for r in selected))}}
    (directory/'review-sample-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    # Never overwrite a user's saved review decisions on regeneration.
    responses=directory/'review-sample-responses.json'
    if not responses.exists(): responses.write_text(json.dumps(labels,indent=2),encoding='utf-8')
    else:
        previous=json.loads(responses.read_text(encoding='utf-8'))
        if [r['source_id'] for r in previous]!=[r['source_id'] for r in labels]:
            raise ValueError('Sample changed; preserve existing responses and choose a new report directory')
        metrics['agreement_with_user_checked_labels']={'checked':sum(r.get('user_checked') is True for r in previous),
            'agreed':sum(r.get('user_checked') is True and r.get('user_agrees') is True for r in previous),
            'scope':'previously displayed sample fields only; recipient/sender not yet verified'}
        (directory/'review-sample-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    page='<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\';style-src \'unsafe-inline\'"><title>25-email review sample</title><style>body{font:16px system-ui;max-width:1450px;margin:24px auto;padding:12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:12px}section{border-top:2px solid #ddd;margin-top:32px}h2{font-size:20px}@media(max-width:800px){.pair{grid-template-columns:1fr}}</style><h1>25-email review sample</h1><p>Review the source beside the current extracted fields. Saved model output is separate. Generated expectations are <b>unverified (model-generated)</b>. This sample is deliberately diverse, not a random estimate of inbox accuracy.</p><p>Format coverage: '+str(template_matches)+'/'+str(len(rows))+' total emails. Agreement with generated labels is reported separately in validation-summary.json. User-checked agreement: not measured. Confirm rows in chat by number; specify any corrected fields. Your existing account/policy confirmations are preserved but do not count as checking these extraction rows.</p>'+''.join(blocks)
    if any(r.get('user_checked') for r in previous):
        page=page.replace('User-checked agreement: not measured.',
            'User feedback: previously displayed samples look good. Recipient/sender are newly added and await verification.')
    (directory/'review-sample.html').write_text(page,encoding='utf-8')
    return metrics


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('directory')
    print(json.dumps(build(parser.parse_args().directory)))
