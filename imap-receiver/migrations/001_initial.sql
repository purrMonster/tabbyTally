CREATE SCHEMA imap_receiver;





CREATE TABLE imap_receiver.accounts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    imap_host text NOT NULL,
    imap_port integer DEFAULT 993 NOT NULL,
    username text NOT NULL,
    credential_ref text NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT accounts_imap_port_check CHECK (((imap_port >= 1) AND (imap_port <= 65535)))
);



CREATE TABLE imap_receiver.attachments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email_id uuid NOT NULL,
    part_index integer NOT NULL,
    filename text,
    content_type text,
    size_bytes bigint NOT NULL,
    content_id text,
    sha256 text,
    CONSTRAINT attachments_part_index_check CHECK ((part_index >= 0)),
    CONSTRAINT attachments_sha256_check CHECK (((sha256 IS NULL) OR (sha256 ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT attachments_size_bytes_check CHECK ((size_bytes >= 0))
);



CREATE TABLE imap_receiver.emails (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    mailbox_id uuid NOT NULL,
    uid_validity bigint NOT NULL,
    uid bigint NOT NULL,
    message_id text,
    subject text,
    from_addresses jsonb DEFAULT '[]'::jsonb NOT NULL,
    to_addresses jsonb DEFAULT '[]'::jsonb NOT NULL,
    cc_addresses jsonb DEFAULT '[]'::jsonb NOT NULL,
    message_date timestamp with time zone,
    internal_date timestamp with time zone,
    captured_at timestamp with time zone DEFAULT now() NOT NULL,
    text_body text,
    html_body text,
    raw_email bytea,
    raw_sha256 text,
    size_bytes bigint NOT NULL,
    capture_status text NOT NULL,
    error_code text,
    parser_version text,
    CONSTRAINT emails_capture_status_check CHECK ((capture_status = ANY (ARRAY['captured'::text, 'parse_failed'::text, 'oversized'::text]))),
    CONSTRAINT emails_cc_addresses_check CHECK ((jsonb_typeof(cc_addresses) = 'array'::text)),
    CONSTRAINT emails_check CHECK (((capture_status = 'oversized'::text) OR ((raw_email IS NOT NULL) AND (raw_sha256 IS NOT NULL)))),
    CONSTRAINT emails_from_addresses_check CHECK ((jsonb_typeof(from_addresses) = 'array'::text)),
    CONSTRAINT emails_raw_sha256_check CHECK (((raw_sha256 IS NULL) OR (raw_sha256 ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT emails_size_bytes_check CHECK ((size_bytes >= 0)),
    CONSTRAINT emails_to_addresses_check CHECK ((jsonb_typeof(to_addresses) = 'array'::text)),
    CONSTRAINT emails_uid_check CHECK (((uid >= 1) AND (uid <= '4294967295'::bigint))),
    CONSTRAINT emails_uid_validity_check CHECK (((uid_validity >= 1) AND (uid_validity <= '4294967295'::bigint)))
);



CREATE TABLE imap_receiver.mailboxes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    account_id uuid NOT NULL,
    folder_path text DEFAULT 'INBOX'::text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    uid_validity bigint,
    last_uid bigint,
    initialized_at timestamp with time zone,
    last_scan_at timestamp with time zone,
    last_error_code text,
    CONSTRAINT mailboxes_check CHECK ((((uid_validity IS NULL) AND (last_uid IS NULL) AND (initialized_at IS NULL)) OR ((uid_validity IS NOT NULL) AND (last_uid IS NOT NULL) AND (initialized_at IS NOT NULL) AND ((uid_validity >= 1) AND (uid_validity <= '4294967295'::bigint)) AND ((last_uid >= 0) AND (last_uid <= '4294967295'::bigint)))))
);



ALTER TABLE ONLY imap_receiver.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (id);



ALTER TABLE ONLY imap_receiver.attachments
    ADD CONSTRAINT attachments_email_id_part_index_key UNIQUE (email_id, part_index);



ALTER TABLE ONLY imap_receiver.attachments
    ADD CONSTRAINT attachments_pkey PRIMARY KEY (id);



ALTER TABLE ONLY imap_receiver.emails
    ADD CONSTRAINT emails_mailbox_id_uid_validity_uid_key UNIQUE (mailbox_id, uid_validity, uid);



ALTER TABLE ONLY imap_receiver.emails
    ADD CONSTRAINT emails_pkey PRIMARY KEY (id);



ALTER TABLE ONLY imap_receiver.mailboxes
    ADD CONSTRAINT mailboxes_account_id_folder_path_key UNIQUE (account_id, folder_path);



ALTER TABLE ONLY imap_receiver.mailboxes
    ADD CONSTRAINT mailboxes_pkey PRIMARY KEY (id);



CREATE INDEX emails_captured_at_idx ON imap_receiver.emails USING btree (captured_at, id);



CREATE INDEX emails_message_id_idx ON imap_receiver.emails USING btree (message_id) WHERE (message_id IS NOT NULL);



ALTER TABLE ONLY imap_receiver.attachments
    ADD CONSTRAINT attachments_email_id_fkey FOREIGN KEY (email_id) REFERENCES imap_receiver.emails(id);



ALTER TABLE ONLY imap_receiver.emails
    ADD CONSTRAINT emails_mailbox_id_fkey FOREIGN KEY (mailbox_id) REFERENCES imap_receiver.mailboxes(id);



ALTER TABLE ONLY imap_receiver.mailboxes
    ADD CONSTRAINT mailboxes_account_id_fkey FOREIGN KEY (account_id) REFERENCES imap_receiver.accounts(id);
