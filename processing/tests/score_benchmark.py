"""Score private reviewed expectations against model-only benchmark output."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import statistics
from tabby_processing import facts, normalize

def equivalent(key, expected, actual):
    if key=='amount':
        try: return Decimal(expected)==Decimal(actual)
        except (InvalidOperation,TypeError): return expected==actual
    if key=='account_identifier' and actual is not None:
        # Allow only a masked number or a bare suffix, not an invented label.
        return bool(re.fullmatch(r'[0-9xX* .-]*[0-9]{4}',actual)) and actual[-4:]==expected[-4:]
    return expected==actual

def main():
    p=argparse.ArgumentParser(); p.add_argument('expectations'); p.add_argument('results'); p.add_argument('--output',required=True)
    p.add_argument('--inventory',help='Optional private corpus_inventory JSON for exact evidence checks')
    args=p.parse_args(); gold=json.loads(Path(args.expectations).read_text(encoding='utf-8'))
    rows=[json.loads(x) for x in Path(args.results).read_text(encoding='utf-8').splitlines()]
    if len({r['id'] for r in rows})!=len(rows): raise ValueError('Duplicate benchmark rows')
    confusion=Counter(); fields=defaultdict(Counter); errors=[]; complete=Counter(); profiles=Counter()
    sources={r['id']:normalize.normalize(r['source']).text for r in json.loads(Path(args.inventory).read_text(encoding='utf-8'))} if args.inventory else {}
    evidence=Counter()
    for row in rows:
        expected=gold[row['id']]; value=row.get('facts',{}); actual=value.get('classification',row['status'])
        confusion[(expected['classification'],actual)]+=1
        routing=(row.get('metadata') or {}).get('routing_before') or {}
        profiles[str(routing)]+=1
        if row['id'] in sources:
            for event in value.get('events',[]):
                spans,issues=facts.evidence_spans(event,sources[row['id']])
                evidence['events']+=1; evidence['events_with_quote_issues']+=bool(issues)
                evidence['quotes']+=len(event['evidence']); evidence['unique_exact_quotes']+=len(spans)
                for entry in event['evidence']:
                    occurrences=sources[row['id']].count(entry['quote']) if entry['quote'] else 0
                    evidence['absent_quotes']+=occurrences==0
                    evidence['repeated_quotes']+=occurrences>1
        mismatches=[]
        if expected['classification']=='transaction':
            events=value.get('events',[])
            if len(events)!=1: mismatches.append('event_count')
            event=events[0] if len(events)==1 else {}
            for key,want in expected.get('fields',{}).items():
                got=event.get('transaction_amount',{}).get(key) if key in ('amount','currency') else event.get(key)
                passed=equivalent(key,want,got) and len(events)==1
                fields[key]['total']+=1; fields[key]['correct']+=passed
                if not passed: mismatches.append(key)
            complete['total']+=1; complete['correct']+=not mismatches and actual=='transaction'
        elif expected['classification']=='non_transaction' and actual!='non_transaction':
            mismatches.append('classification')
        if mismatches: errors.append({'id':row['id'],'fields':mismatches,'family':expected['family']})
    timings=sorted(r['elapsed_seconds'] for r in rows if r['status']!='input_review')
    usages=[(r.get('metadata') or {}).get('usage',{}) for r in rows]
    ordered=[r['elapsed_seconds'] for r in rows if r['status']!='input_review']
    summary={'processed':len(rows),'expected':len(gold),'status':dict(Counter(r['status'] for r in rows)),
             'confusion':[{'expected':a,'actual':b,'count':n} for (a,b),n in sorted(confusion.items())],
             'fields':dict(fields),'all_checked_fields':dict(complete),
             'latency_seconds':{'total':sum(timings),'mean':statistics.mean(timings),'median':statistics.median(timings),
                 'p95':timings[max(0,__import__('math').ceil(.95*len(timings))-1)],'max':max(timings)},
             'tokens':{key:sum(u.get(key,0) for u in usages) for key in ('prompt_tokens','completion_tokens','total_tokens')},
             'startup_comparison':{'first_request_seconds':ordered[0],
                 'subsequent_request_median_seconds':statistics.median(ordered[1:]) if len(ordered)>1 else None,
                 'cold_start_verified':False},
             'profiles':dict(profiles),'evidence':dict(evidence),'errors':errors}
    Path(args.output).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='errors'}))

if __name__=='__main__': main()
