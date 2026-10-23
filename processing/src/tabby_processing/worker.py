import time

from . import jobs


def once(db, lease_seconds=180, deadline=120):
    if deadline <= 0 or deadline >= lease_seconds:
        raise ValueError('Deadline must be positive and shorter than lease')
    job = jobs.claim(db, lease_seconds)
    if not job:
        return {'claimed': False}
    pipeline = db.execute('SELECT mode,config FROM processing.pipeline_versions WHERE id=%s',
                          (job['pipeline_version'],)).fetchone()
    config = pipeline['config']
    if pipeline['mode']=='extract':
        from . import extraction, model
        try:
            return extraction.process(db,job,config,deadline)
        except jobs.LostLease:
            return {'job_id':str(job['id']),'outcome':'lost_lease'}
        except model.ModelError as error:
            try:
                jobs.fail(db,job['id'],job['lease_token'],permanent=not error.transient,code=error.code)
            except jobs.LostLease:
                return {'job_id':str(job['id']),'outcome':'lost_lease'}
            if not error.transient:
                raise
            return {'job_id':str(job['id']),'outcome':'retry_wait'}
    status = db.execute('SELECT capture_status FROM imap_receiver.emails WHERE id=%s', (job['email_id'],)).fetchone()['capture_status']
    scenario = config['scenario']
    delay = config.get('delay', 0)
    time.sleep(min(delay, deadline))
    try:
        if delay >= deadline or (scenario == 'transient' and job['attempts'] <= config.get('failures', 1)):
            jobs.fail(db, job['id'], job['lease_token'])
        elif scenario == 'permanent':
            jobs.fail(db, job['id'], job['lease_token'], permanent=True)
        else:
            kind = 'fake_review_required' if scenario == 'review' or status != 'captured' else 'fake_success'
            jobs.complete(db, job['id'], job['lease_token'], kind, {'synthetic': True})
    except jobs.LostLease:
        return {'job_id': str(job['id']), 'outcome': 'lost_lease'}
    return {'claimed': True, 'job_id': str(job['id'])}
