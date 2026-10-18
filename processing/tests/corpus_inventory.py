"""Local-only corpus inventory. Raw sources/derived text are written only to ignored exports."""
import argparse
from collections import Counter
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re

from tabby_processing import normalize


def read(path):
    raw=path.read_bytes()
    msg=BytesParser(policy=policy.default).parsebytes(raw)
    bodies={}
    for kind,key in [('plain','text_body'),('html','html_body')]:
        part=msg.get_body(preferencelist=(kind,))
        bodies[key]=part.get_content() if part else None
    source={'subject':str(msg.get('Subject','')),'message_date':str(msg.get('Date','')),'capture_status':'captured',**bodies}
    if any(p.defects for p in msg.walk()): source['capture_status']='parse_failed'
    normalized=normalize.normalize(source)
    # Unbounded only for local inspection of why a bounded processor refuses a file.
    preview=normalize.normalize(source,max_bytes=2_000_000)
    family=re.sub(r'\d+','N',source['subject'])
    family=re.sub(r'(?i)dear\s+[^,]+,','Dear NAME,',family)
    return {'id':hashlib.sha256(raw).hexdigest(),'family':family,'source':source,
            'normalized':normalized.text,'issues':normalized.issues,'preview':preview.text,
            'raw_bytes':len(raw),'html_bytes':len((bodies['html_body'] or '').encode()),
            'visible_bytes':len(preview.text.encode())}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory'); parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output).resolve()
    if 'exports' not in output.parts: raise ValueError('Private output must be inside ignored exports directory')
    rows=[read(p) for p in sorted(Path(args.directory).glob('*.eml'))]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(rows,ensure_ascii=True),encoding='utf-8')
    counts=Counter(r['family'] for r in rows)
    print(json.dumps({'count':len(rows),'unique_raw':len({r['id'] for r in rows}),
                      'normalization_issues':dict(Counter(i for r in rows for i in r['issues'])),
                      'families':[{'index':i,'count':n,'subject':re.sub(r'\b\d+\b','N',s)}
                                  for i,(s,n) in enumerate(counts.most_common())]},ensure_ascii=True))


if __name__=='__main__': main()
