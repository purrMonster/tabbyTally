import argparse
import json
import signal
import threading

from .database import connect
from . import admin, discovery, jobs, migrate, worker, extraction, model, accounts, correlation, review, review_api


def main():
    parser = argparse.ArgumentParser(description='Durable email processing and review-only extraction')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('migrate','status','provision','health','inspect'):
        sub.add_parser(name)
    sub.add_parser('model-check', help='List configured backend aliases; sends no email')
    sub.add_parser('review-api',help='Serve authenticated review callbacks')
    sub.add_parser('reviews',help='List pending review IDs and revisions')
    show=sub.add_parser('review-show',help='Privately inspect one review, facts and evidence')
    show.add_argument('id')
    sub.add_parser('notifications',help='Inspect notification backlog without message content')
    decision=sub.add_parser('review-action',help='Apply an audited local review decision from private JSON')
    decision.add_argument('--file',required=True)
    register=sub.add_parser('install-account-register',help='Install a confirmed private account register, repeat safely')
    register.add_argument('--file',required=True)
    register.add_argument('--reason',required=True)
    mapping = sub.add_parser('map-account',help='Register an explicit logical account and mapping')
    for name in ('label','currency','bank','product','identifier','version','reason'):
        mapping.add_argument('--'+name,required=True)
    sub.add_parser('candidates',help='Show candidate IDs, dispositions and reasons, without raw evidence')
    sub.add_parser('correlations',help='Inspect relationships in the most recent 2000 candidates; no automatic merging')
    restore = sub.add_parser('invalidate-restored-leases')
    restore.add_argument('--reason', required=True)
    restore.add_argument('--old-workers-fenced', action='store_true', required=True)
    activation = sub.add_parser('activate')
    activation.add_argument('--version', required=True)
    activation.add_argument('--mode',choices=['fake','extract'],default='fake')
    activation.add_argument('--mailbox', action='append', default=[])
    activation.add_argument('--email', action='append', default=[])
    activation.add_argument('--scenario', choices=['success','review','transient','permanent','delay'], default='success')
    activation.add_argument('--failures', type=int, default=1)
    activation.add_argument('--delay', type=float, default=0)
    activation.add_argument('--reason', required=True)
    for name in ('pause','resume','retry','history'):
        command = sub.add_parser(name)
        command.add_argument('id')
        if name != 'history':
            command.add_argument('--reason', required=True)
        if name == 'retry':
            command.add_argument('--allowance', type=int, default=1)
    for name, interval in (('discover',60),('work',1),('recover',30)):
        command = sub.add_parser(name)
        command.add_argument('--loop', action='store_true')
        command.add_argument('--interval', type=float, default=interval)
        if name == 'work':
            command.add_argument('--lease-seconds', type=int, default=180)
            command.add_argument('--deadline', type=float, default=120)
    args = parser.parse_args()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        if args.command=='review-api':
            review_api.serve(stop); return 0
        if args.command=='model-check':
            model.config()
            print(json.dumps(model.call(action='models',timeout=30)))
            return 0
        if hasattr(args, 'interval') and args.interval <= 0:
            raise ValueError('Interval must be positive')
        while not stop.is_set():
            try:
                with connect() as db:
                    if args.command not in ('migrate','status','provision'):
                        migrate.compatible(db)
                    if args.command in ('migrate','status'):
                        result = migrate.migrate(db, status=args.command=='status')
                    elif args.command == 'provision':
                        admin.provision(db)
                        result = {'provisioned': True}
                    elif args.command == 'activate':
                        config = extraction.pipeline_config() if args.mode=='extract' else {
                            'scenario': args.scenario, 'failures': args.failures, 'delay': args.delay}
                        result = {'run_id': discovery.activate(db, args.version, args.mailbox, args.email,
                            config, args.reason,mode=args.mode)}
                    elif args.command=='review-show':
                        result=db.execute('SELECT r.*,c.facts,c.validation,e.reasons AS extraction_reasons,e.normalized_text FROM processing.reviews r LEFT JOIN processing.transaction_candidates c ON c.id=r.candidate_id JOIN processing.extraction_results e ON e.id=r.extraction_id WHERE r.id=%s',(args.id,)).fetchone()
                    elif args.command=='notifications':
                        result=db.execute('SELECT state,count(*) AS count,min(due_at) AS oldest FROM processing.notification_outbox GROUP BY state').fetchall()
                    elif args.command=='reviews':
                        result=db.execute("SELECT id,candidate_id,extraction_id,revision,state FROM processing.reviews WHERE state='open' ORDER BY created_at LIMIT 100").fetchall()
                    elif args.command=='review-action':
                        from pathlib import Path
                        actor=db.execute('SELECT session_user AS actor').fetchone()['actor']
                        result=review.decide(db,actor,json.loads(Path(args.file).read_text(encoding='utf-8-sig')))
                    elif args.command=='install-account-register':
                        from pathlib import Path
                        result=accounts.install(db,json.loads(Path(args.file).read_text(encoding='utf-8-sig')),args.reason)
                    elif args.command=='map-account':
                        result = extraction.register_mapping(db,args.label,args.currency,args.bank,args.product,
                                                             args.identifier,args.version,args.reason)
                    elif args.command=='correlations':
                        rows=db.execute('SELECT id,facts,account_id FROM processing.transaction_candidates ORDER BY created_at DESC LIMIT 2001').fetchall()
                        limited=len(rows)>2000; rows=rows[:2000]
                        result={'scope_truncated':limited,'suggestions':[
                            {'candidate_id':str(row['id']),'related':correlation.suggest(row['facts'],row['account_id'],rows[i+1:])}
                            for i,row in enumerate(rows)]}
                    elif args.command=='candidates':
                        result = db.execute("""SELECT id,extraction_id,event_index,disposition,
                            validation->'reasons' AS reasons FROM processing.transaction_candidates
                            ORDER BY created_at DESC LIMIT 100""").fetchall()
                    elif args.command in ('pause','resume'):
                        discovery.set_enabled(db, args.id, args.command=='resume', args.reason)
                        result = {'updated': True}
                    elif args.command == 'retry':
                        discovery.retry(db,args.id,args.allowance,args.reason)
                        result = {'updated': True}
                    elif args.command == 'discover':
                        result = discovery.reconcile(db)
                    elif args.command == 'work':
                        result = worker.once(db,args.lease_seconds,args.deadline)
                    elif args.command == 'invalidate-restored-leases':
                        result = {'invalidated': discovery.invalidate_leases(db,args.reason)}
                    elif args.command == 'recover':
                        result = {'recovered': jobs.recover(db)}
                    elif args.command == 'history':
                        result = {'job': db.execute('SELECT * FROM processing.email_jobs WHERE id=%s',(args.id,)).fetchone(),
                                  'attempts': db.execute('SELECT * FROM processing.job_attempts WHERE job_id=%s ORDER BY number',(args.id,)).fetchall()}
                    elif args.command == 'inspect':
                        result = db.execute('SELECT state,count(*) AS count,min(created_at) AS oldest FROM processing.email_jobs GROUP BY state').fetchall()
                    else:
                        result = {'database_ready': True, 'modes': ['fake','extract'], 'model_connectivity_checked':False}
                print(json.dumps(result, default=str), flush=True)
            except Exception as error:
                report = {'event': 'processing_error', 'error_class': type(error).__name__}
                if isinstance(error,model.ModelError):
                    report['code'] = error.code
                print(json.dumps(report), flush=True)
                # Connection errors may recover. Configuration/programming errors stop dispatch.
                import psycopg
                if not getattr(args,'loop',False) or not isinstance(error, psycopg.OperationalError):
                    return 1
            if not getattr(args,'loop',False):
                return 0
            stop.wait(args.interval)
    except Exception as error:
        print(json.dumps({'event':'configuration_error','error_class':type(error).__name__}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
