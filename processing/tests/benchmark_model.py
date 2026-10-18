"""Explicit private, resumable model-only corpus benchmark; no database writes."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from corpus_inventory import read
from tabby_processing import facts, model, normalize

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory'); parser.add_argument('--output',required=True)
    parser.add_argument('--ids',help='Private JSON list of source SHA-256 IDs for a targeted regression run')
    args=parser.parse_args()
    output=Path(args.output).resolve()
    if 'exports' not in output.parts: raise ValueError('Use ignored private exports directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    settings=model.config()
    done={}
    if output.exists():
        for line in output.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row['identity']!=settings['identity']: raise ValueError('Configuration changed; use new output')
            done[row['id']]=row
    files=sorted(Path(args.directory).glob('*.eml'))
    selected=set(json.loads(Path(args.ids).read_text())) if args.ids else None
    for index,path in enumerate(files,1):
        row=read(path)
        if selected is not None and row['id'] not in selected: continue
        if row['id'] in done: continue
        normalized=normalize.normalize(row['source'])
        result={'id':row['id'],'identity':settings['identity'],
                'input_sha256':hashlib.sha256(normalized.text.encode()).hexdigest(),
                'issues':normalized.issues,'status':'input_review'}
        start=time.monotonic()
        if not normalized.issues:
            try:
                response=model.call(normalized.text,timeout=1200)
                if response['metadata']['identity']!=settings['identity']:
                    raise RuntimeError('Model configuration changed during run; discard this attempt and restart')
                result['metadata']=response['metadata']
                result['facts']=facts.parse(response['raw'])
                result['status']='valid'
            except model.ModelError as error:
                result.update(status='model_error',code=error.code,metadata=error.metadata)
            except facts.InvalidOutput as error:
                result.update(status='invalid_output',code=str(error))
                # Private diagnostic only: never print source or invalid model content.
                result['raw_output']=response['raw']
        result['elapsed_seconds']=round(time.monotonic()-start,3)
        with output.open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(result,ensure_ascii=True)+'\n'); handle.flush()
        print(json.dumps({'completed':index,'total':len(files),'status':result['status'],
                          'elapsed_seconds':result['elapsed_seconds']}),flush=True)

if __name__=='__main__': main()
