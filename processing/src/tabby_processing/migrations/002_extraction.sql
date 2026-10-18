ALTER TABLE processing.pipeline_versions DROP CONSTRAINT pipeline_versions_mode_check;
ALTER TABLE processing.pipeline_versions ADD CONSTRAINT pipeline_versions_mode_check CHECK (mode IN ('fake','extract'));
ALTER TABLE processing.job_results DROP CONSTRAINT job_results_kind_check;
ALTER TABLE processing.job_results ADD CONSTRAINT job_results_kind_check
 CHECK (kind IN ('fake_success','fake_review_required','extracted','ignored','review_required'));

CREATE TABLE processing.logical_accounts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), label text NOT NULL,
 currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE processing.account_mappings (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 account_id uuid NOT NULL REFERENCES processing.logical_accounts(id),
 bank text NOT NULL, product text NOT NULL, account_identifier text NOT NULL,
 version text NOT NULL, enabled boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(account_id,bank,product,account_identifier,version)
);
CREATE TABLE processing.extraction_results (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 job_id uuid NOT NULL UNIQUE REFERENCES processing.email_jobs(id),
 attempt_id uuid NOT NULL,
 source_sha256 text, input_sha256 text NOT NULL, normalizer_version text NOT NULL,
 normalized_text text NOT NULL CHECK (octet_length(normalized_text)<=24000),
 schema_version text NOT NULL, rule_version text NOT NULL,
 model_metadata jsonb NOT NULL, raw_output text CHECK (octet_length(raw_output)<=65536),
 facts jsonb, reasons jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(job_id,attempt_id) REFERENCES processing.job_attempts(job_id,id)
);
CREATE TABLE processing.transaction_candidates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 extraction_id uuid NOT NULL REFERENCES processing.extraction_results(id),
 event_index integer NOT NULL CHECK (event_index>=0 AND event_index<10),
 facts jsonb NOT NULL, validation jsonb NOT NULL,
 disposition text NOT NULL CHECK (disposition IN ('ready','needs_review','duplicate_suspected')),
 account_id uuid REFERENCES processing.logical_accounts(id),
 identity_key text, duplicate_of uuid REFERENCES processing.transaction_candidates(id),
 revision integer NOT NULL DEFAULT 1 CHECK (revision>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(extraction_id,event_index)
);
CREATE INDEX candidates_identity ON processing.transaction_candidates(identity_key) WHERE identity_key IS NOT NULL;
