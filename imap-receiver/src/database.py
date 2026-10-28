"""Shared database connection settings with file-mounted password support."""

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def connect(**overrides):
    settings = dict(connect_timeout=10, autocommit=True, row_factory=dict_row)
    if path := os.environ.get('PGPASSWORD_FILE'):
        password = Path(path).read_bytes().decode('utf-8')
        if not password:
            raise ValueError('Database password file is empty')
        settings['password'] = password
    settings.update(overrides)
    return psycopg.connect(**settings)
