"""Strict JSON extraction contract. Model text is data, never executable code."""
import json

VERSION = 'bank-events-v1'
EVENT_TYPES = ['purchase','refund','income','transfer','card_repayment','cash_withdrawal',
               'loan_payment','fee','authorization','unknown']


class InvalidOutput(ValueError):
    pass


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def string(nullable=False, maximum=256):
    return {'type': ['string','null'] if nullable else 'string', 'maxLength': maximum}


def enum(values):
    return {'type': 'string', 'enum': values}


MONEY = obj({'amount': string(True,64), 'currency': string(True,3)})
EVIDENCE = obj({'field': string(maximum=40), 'quote': string(maximum=1024)})
EVENT = obj({
    'event_type': enum(EVENT_TYPES), 'bank': string(True,80), 'product': string(True,40),
    'account_identifier': string(True,40), 'transaction_amount': MONEY,
    'original_amount': MONEY, 'billed_amount': MONEY,
    'direction': enum(['debit','credit','unknown']), 'transaction_date': string(True,40),
    'merchant': string(True), 'reference': string(True,128),
    'lifecycle': enum(['authorized','posted','reversed','unknown']),
    'unresolved_fields': {'type':'array','items':string(maximum=80),'maxItems':30},
    'evidence': {'type':'array','items':EVIDENCE,'maxItems':30},
})
SCHEMA = obj({
    'schema_version': enum([VERSION]),
    'classification': enum(['transaction','non_transaction','ambiguous','unsupported']),
    'reason': string(maximum=256),
    'events': {'type':'array','items':EVENT,'maxItems':10},
})


def check(value, schema):
    types = schema['type'] if isinstance(schema['type'],list) else [schema['type']]
    actual = 'null' if value is None else {str:'string',dict:'object',list:'array'}.get(type(value))
    if actual not in types:
        raise InvalidOutput('schema_type')
    if value is None:
        return
    if 'enum' in schema and value not in schema['enum']:
        raise InvalidOutput('schema_enum')
    if actual == 'string' and (len(value)>schema['maxLength'] if 'maxLength' in schema else False):
        raise InvalidOutput('schema_length')
    if actual == 'string' and '\x00' in value:
        raise InvalidOutput('schema_nul')
    if actual == 'string':
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise InvalidOutput('schema_unicode') from None
    if actual == 'object':
        if set(value) != set(schema['properties']):
            raise InvalidOutput('schema_keys')
        for key, field in schema['properties'].items():
            check(value[key],field)
    if actual == 'array':
        if len(value)>schema['maxItems']:
            raise InvalidOutput('schema_length')
        for item in value:
            check(item,schema['items'])


def _pairs(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise InvalidOutput('duplicate_key')
        result[key] = value
    return result


def parse(raw):
    if not isinstance(raw,str) or len(raw.encode('utf-8'))>65536:
        raise InvalidOutput('output_limit')
    try:
        value = json.loads(raw,object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(InvalidOutput('nonfinite')))
        check(value,SCHEMA)
    except (ValueError,TypeError,RecursionError) as error:
        raise InvalidOutput('invalid_model_output') from None
    if value['classification'] != 'transaction' and value['events']:
        raise InvalidOutput('contradictory_classification')
    if value['classification'] == 'transaction' and not value['events']:
        raise InvalidOutput('missing_events')
    return value


def evidence_spans(event, text):
    spans, issues = [], []
    seen = set()
    for entry in event['evidence']:
        field, quote = entry['field'], entry['quote']
        if not quote or field in seen:
            issues.append('evidence_invalid')
            continue
        seen.add(field)
        start = text.find(quote)
        if start < 0 or text.find(quote,start+1)>=0:
            issues.append('evidence_missing_or_ambiguous')
            continue
        spans.append({'field':field,'quote':quote,'start':start,'end':start+len(quote)})
    return spans, sorted(set(issues))
