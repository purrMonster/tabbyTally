CREATE SCHEMA processing;
REVOKE ALL ON SCHEMA processing FROM PUBLIC;
CREATE TABLE processing.schema_migrations (
 id integer PRIMARY KEY, sha256 text NOT NULL, schema_sha256 text NOT NULL,
 applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE processing.pipeline_versions (
 id text PRIMARY KEY, mode text NOT NULL CHECK (mode = 'fake'),
 config jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE processing.processing_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 pipeline_version text NOT NULL REFERENCES processing.pipeline_versions(id),
 enabled boolean NOT NULL DEFAULT true, kind text NOT NULL CHECK (kind IN ('live','sample')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE processing.run_mailbox_boundaries (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id uuid NOT NULL REFERENCES processing.processing_runs(id),
 mailbox_id uuid NOT NULL REFERENCES imap_receiver.mailboxes(id),
 uid_validity bigint NOT NULL, last_uid bigint NOT NULL,
 UNIQUE(run_id,mailbox_id)
);
CREATE TABLE processing.run_email_selections (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id uuid NOT NULL REFERENCES processing.processing_runs(id),
 email_id uuid NOT NULL REFERENCES imap_receiver.emails(id), UNIQUE(run_id,email_id)
);
CREATE TABLE processing.email_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 email_id uuid NOT NULL REFERENCES imap_receiver.emails(id),
 pipeline_version text NOT NULL REFERENCES processing.pipeline_versions(id),
 run_id uuid NOT NULL REFERENCES processing.processing_runs(id),
 state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','leased','retry_wait','completed','dead')),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 attempt_limit integer NOT NULL DEFAULT 5 CHECK (attempt_limit > 0 AND attempts <= attempt_limit),
 due_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 lease_token uuid, lease_expires_at timestamptz, last_error text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(email_id,pipeline_version),
 CHECK ((state = 'leased') = (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
 CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL))
);
CREATE INDEX jobs_due ON processing.email_jobs(state,due_at);
CREATE INDEX jobs_expiry ON processing.email_jobs(lease_expires_at) WHERE state='leased';
CREATE TABLE processing.job_attempts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 job_id uuid NOT NULL REFERENCES processing.email_jobs(id),
 number integer NOT NULL CHECK (number > 0), token uuid NOT NULL UNIQUE,
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(), finished_at timestamptz,
 outcome text CHECK (outcome IN ('completed','transient','permanent','abandoned')),
 error_code text, UNIQUE(job_id,number), UNIQUE(job_id,id),
 CHECK ((finished_at IS NULL) = (outcome IS NULL))
);
CREATE TABLE processing.job_results (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 job_id uuid NOT NULL UNIQUE REFERENCES processing.email_jobs(id), attempt_id uuid NOT NULL,
 kind text NOT NULL CHECK (kind IN ('fake_success','fake_review_required')),
 payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object' AND octet_length(payload::text)<=4096),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(job_id,attempt_id) REFERENCES processing.job_attempts(job_id,id)
);
CREATE TABLE processing.operator_actions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), actor text NOT NULL DEFAULT session_user,
 action text NOT NULL, target text NOT NULL, reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
