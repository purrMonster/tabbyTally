ALTER TABLE processing.transaction_candidates DROP CONSTRAINT transaction_candidates_disposition_check;
ALTER TABLE processing.transaction_candidates ADD CONSTRAINT transaction_candidates_disposition_check
 CHECK (disposition IN ('ready','needs_review','duplicate_suspected','ignored'));
CREATE TABLE processing.reviews (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 extraction_id uuid NOT NULL REFERENCES processing.extraction_results(id),
 candidate_id uuid UNIQUE REFERENCES processing.transaction_candidates(id),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 state text NOT NULL DEFAULT 'open' CHECK(state IN ('open','resolved')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX review_source_only ON processing.reviews(extraction_id) WHERE candidate_id IS NULL;
CREATE TABLE processing.review_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), review_id uuid NOT NULL REFERENCES processing.reviews(id),
 actor text NOT NULL, action text NOT NULL, previous_revision integer NOT NULL,
 before_facts jsonb, after_facts jsonb, reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE processing.action_receipts (
 id text PRIMARY KEY, actor text NOT NULL, digest text NOT NULL, result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE processing.notification_outbox (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), review_id uuid NOT NULL REFERENCES processing.reviews(id),
 revision integer NOT NULL, payload jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','leased','sent','dead')),
 attempts integer NOT NULL DEFAULT 0, due_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 token uuid, lease_expires_at timestamptz, last_error text,
 UNIQUE(review_id,revision),
 CHECK((state='leased')=(token IS NOT NULL AND lease_expires_at IS NOT NULL))
);
