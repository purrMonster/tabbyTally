"""Offline coverage and negative guard checks; not a model accuracy benchmark."""
import argparse
from collections import Counter
import json
from pathlib import Path
from corpus_inventory import read
from tabby_processing import normalize, templates

# Conservative negative cohorts independently identified during corpus inspection.
# Mixed account-update subjects deliberately excluded. These labels never drive
# production classification and are not a substitute for field-level gold labels.
NEGATIVE_PREFIXES=('OTP For online Ecom Transaction','Credit Card xx',
    'Credit 💳','Exclusive offer only for you','Reminder to Acknowledge CIS',
    'Deemed Acknowledgement of CIS','Your HDFC Bank -','AXIS BANK : Statement',
    'ICICI Bank Credit Card Statement','Email Account Statement',
    'Welcome to HDFC ERGO Family','Your pre-approved Credit Card upgrade',
    'Make big spends easier, convert them into EMIs!')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory')
    args=parser.parse_args()
    rows=[read(p) for p in Path(args.directory).glob('*.eml')]
    coverage=Counter(); issues=Counter(); negative_count=0; false_positive=0
    dates=Counter()
    for row in rows:
        normalized=normalize.normalize(row['source'])
        result=None if normalized.issues else templates.parse(normalized.text,row['source'].get('message_date'))
        if result:
            without_context=templates.parse(normalized.text)
            resolved=result[0]['events'][0]['transaction_date']
            dates['resolved']+=bool(resolved)
            dates['newly_resolved_with_header']+=bool(resolved and not without_context[0]['events'][0]['transaction_date'])
        coverage.update([result[1] if result else 'model_or_review_fallback'])
        issues.update(normalized.issues)
        if row['source']['subject'].startswith(NEGATIVE_PREFIXES):
            negative_count+=1
            false_positive+=bool(result)
    print(json.dumps(dict(emails=len(rows),unique_raw=len({r['id'] for r in rows}),
        template_coverage=dict(coverage),normalization_issues=dict(issues),
        negative_cohort=negative_count,negative_template_false_positives=false_positive,
        date_resolution=dict(dates),model_calls=0,field_accuracy_measured=False)))
    if false_positive: raise SystemExit(1)

if __name__=='__main__': main()
