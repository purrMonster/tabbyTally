"""Independent, fenced notification retries; sender must honor bounded timeout."""
from uuid import uuid4


def once(db, sender):
    with db.transaction():
        db.execute("UPDATE processing.notification_outbox SET state=CASE WHEN attempts>=5 THEN 'dead' ELSE 'pending' END,token=NULL,lease_expires_at=NULL,last_error='lease_expired' WHERE state='leased' AND lease_expires_at<=clock_timestamp()")
        row=db.execute("SELECT * FROM processing.notification_outbox WHERE state='pending' AND due_at<=clock_timestamp() ORDER BY due_at,id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not row: return {'outcome':'idle'}
        token=uuid4()
        db.execute("UPDATE processing.notification_outbox SET state='leased',token=%s,lease_expires_at=clock_timestamp()+interval '60 seconds',attempts=attempts+1 WHERE id=%s",(token,row['id']))
    ok=True
    try: sender(row['payload'],str(row['id']),timeout=20)
    except Exception: ok=False
    with db.transaction():
        locked=db.execute('SELECT * FROM processing.notification_outbox WHERE id=%s FOR UPDATE',(row['id'],)).fetchone()
        valid=db.execute('SELECT %s::uuid=%s::uuid AND %s::timestamptz>clock_timestamp() AS valid',(locked['token'],token,locked['lease_expires_at'])).fetchone()['valid']
        if not valid: return {'outcome':'lost_lease'}
        state='sent' if ok else 'dead' if locked['attempts']>=5 else 'pending'
        db.execute('UPDATE processing.notification_outbox SET state=%s,token=NULL,lease_expires_at=NULL,due_at=clock_timestamp()+make_interval(secs=>%s),last_error=%s WHERE id=%s',
                   (state,min(3600,30*2**locked['attempts']),None if ok else 'delivery_failed',row['id']))
    return {'outcome':state}
