"""Deterministic, inspectable routing. Classification is conservative, not a DLP guarantee."""
import re

RULES = [
    ('email address', re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')),
    ('credential', re.compile(r'(?i)\b(?:password|api[_ -]?key|secret|access[_ -]?token)\s*[:=]\s*\S+')),
    ('private identifier', re.compile(r'(?i)\b(?:ssn|aadhaar|passport)\s*[:=#]?\s*[\w-]{5,}')),
    ('phone number', re.compile(r'(?<!\w)(?:\+\d{1,3}[ -]?)?(?:\d[ -]?){10,13}(?!\w)')),
]

def routing(record):
    text = ' '.join([record.get('title', ''), record.get('body', ''), ' '.join(record.get('tags', [])), record.get('source', ''), record.get('site', '')])
    flags = [name for name, pattern in RULES if pattern.search(text)]
    if record.get('deleted'):
        return {'route': 'tombstone', 'reason': 'Deletion withdraws the shared copy while retaining revision history.', 'flags': [], 'priority': 100}
    if record.get('visibility') == 'local':
        return {'route': 'local', 'reason': 'You selected device-only storage.', 'flags': flags, 'priority': 0}
    if flags:
        return {'route': 'local', 'reason': 'Sensitive pattern detected: ' + ', '.join(flags) + '. Remove it before sharing.', 'flags': flags, 'priority': 0}
    priority = {'critical': 100, 'high': 70, 'normal': 40, 'low': 10}.get(record.get('priority'), 40)
    return {'route': 'cloud', 'reason': 'Team sharing selected; no configured sensitive patterns found.', 'flags': [], 'priority': priority}
