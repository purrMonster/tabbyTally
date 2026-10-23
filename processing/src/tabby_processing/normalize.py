"""Bounded email-to-text normalization. Never loads external resources."""
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import re

VERSION = 'email-text-v2'


@dataclass(frozen=True)
class Input:
    text: str
    sha256: str
    issues: tuple[str, ...]
    version: str = VERSION


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'template'):
            self.hidden.append(tag)
        elif not self.hidden and tag in ('br', 'p', 'div', 'tr', 'li', 'table', 'hr'):
            self.parts.append('\n')
        elif not self.hidden and tag in ('td', 'th'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag in ('p', 'div', 'tr', 'li', 'table'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def normalize(source, max_bytes=24000):
    issues = []
    if source.get('capture_status') != 'captured':
        issues.append('capture_incomplete')
    subject = source.get('subject') or ''
    plain = source.get('text_body') or ''
    html = source.get('html_body') or ''
    # Inspect limits before parsing or slicing. Never qualify truncated input.
    selected = plain if plain.strip() else html
    # HTML markup can dwarf visible content. Bound parser work separately; never
    # silently truncate the visible evidence to make a message qualify.
    source_limit = max_bytes if plain.strip() else max(max_bytes,1_000_000)
    if len((subject + selected).encode('utf-8')) > source_limit:
        text = ''
        issues.append('input_incomplete')
    else:
        if not plain.strip() and html:
            parser = VisibleText()
            parser.feed(html)
            parser.close()
            selected = ''.join(parser.parts)
        lines = [re.sub(r'[^\S\n]+', ' ', line).strip()
                 for line in selected.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
        body = '\n'.join(line for line in lines if line)
        text = ('Subject: ' + subject.strip() + '\n\n' if subject.strip() else '') + body
        if not body:
            issues.append('body_unavailable')
        if '\x00' in text:
            issues.append('input_invalid')
            text = text.replace('\x00', '\ufffd')
    if len(text.encode('utf-8')) > max_bytes:
        text = ''
        issues.append('input_incomplete')
    return Input(text, hashlib.sha256(text.encode('utf-8')).hexdigest(), tuple(sorted(set(issues))))
