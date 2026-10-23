import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def connect(**overrides):
    settings = dict(autocommit=True, row_factory=dict_row, connect_timeout=10,
                    options='-c statement_timeout=15000 -c lock_timeout=5000')
    if path := os.environ.get('PGPASSWORD_FILE'):
        password = Path(path).read_bytes().decode('utf-8')
        if not password:
            raise ValueError('Empty password file')
        settings['password'] = password
    settings.update(overrides)
    return psycopg.connect(**settings)
