-- Example only: customize the address locally before executing once.
-- Schema installation is handled by python -m src.migrate apply.
BEGIN;

WITH new_account AS (
    INSERT INTO imap_receiver.accounts (
        name,
        imap_host,
        imap_port,
        username,
        credential_ref,
        enabled
    )
    VALUES (
        'Banking inbox',
        'imap.purelymail.com',
        993,
        'banking@example.com',
        'BANKING_IMAP_PASSWORD',
        false
    )
    RETURNING id
)
INSERT INTO imap_receiver.mailboxes (
    account_id,
    folder_path
)
SELECT id, 'INBOX'
FROM new_account;

COMMIT;
