"""Fase 0: crash diagnostics and type-safe dictionary boundaries.

The user's screenshot showed the RAW Python 3.14 message
"cannot use 'dict' as a dict key (unhashable type: 'dict')" in a modal, with no
traceback. This module gives the host three things it did not have:

* a redacted, on-disk traceback (never project text, keys or tokens);
* a friendly UI message pointing at that file instead of a raw exception;
* `as_key()` / `as_text()` helpers used at EVERY dict-key boundary so a
  malformed config value can never be hashed as a dict again.

Python 3.14 changed the wording of `unhashable type` (CPython gh-132825), which
is why a 3.11-only test matrix missed this. Type validation is version-proof;
message matching is not.
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

MAX_LOG_CHARS = 20000
MAX_LOGS = 12

_SECRETISH = re.compile(
    r'(?i)(?:access_token|refresh_token|api[_-]?key|authorization|bearer|cookie|'
    r'sk-[A-Za-z0-9]{12,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})')
_URL_QUERY = re.compile(r'(https?://[^\s\'"<>]+)')


def log_dir(root=None):
    base = Path(root) if root else (Path.home() / '.nexo-tesis' / 'logs')
    return base


def as_key(value, field='clave', fallback=''):
    """Return a hashable, bounded dict key. NEVER let a dict/list reach a lookup.

    Accepts str/int/float/bool/None. Anything else (dict, list, object, set) is
    replaced with `fallback` and recorded in `last_rejection`, so the host can
    report a corrupt config value without crashing.
    """
    if value is None:
        return fallback
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (str, int, float)):
        text = str(value)
        return text[:300] if len(text) > 300 else text
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)[:300]
    except Exception:
        text = repr(value)[:300]
    _LAST_REJECTION.append({'field': field, 'type': type(value).__name__, 'shape': text})
    del _LAST_REJECTION[:-20]
    return fallback


def as_text(value, field='valor', limit=12000):
    """Coerce a value that must be a bounded string."""
    if isinstance(value, str):
        return value[:limit]
    if value is None:
        return ''
    if isinstance(value, (int, float, bool)):
        return str(value)[:limit]
    as_key(value, field)
    return json.dumps(value, ensure_ascii=False, default=str)[:limit]


_LAST_REJECTION = []


def rejections():
    return list(_LAST_REJECTION)


def clear_rejections():
    _LAST_REJECTION.clear()


def redact(text, config=None):
    """Remove credential-shaped content. No project prose is logged."""
    out = str(text or '')[:MAX_LOG_CHARS]
    if config is not None:
        try:
            out = config.redact(out)
        except Exception:
            pass
    out = _SECRETISH.sub('[OMITIDO]', out)
    out = _URL_QUERY.sub(lambda m: m.group(1).split('?')[0] + '[CONSULTA OMITIDA]'
                         if '?' in m.group(1) else m.group(1), out)
    return out


def project_shape(p):
    """Structural summary only: counts and types, never thesis text."""
    if not isinstance(p, dict):
        return {'present': False}
    def shape(v):
        if isinstance(v, dict):
            return {'type': 'dict', 'size': len(v), 'keys': [as_key(k) for k in list(v)[:12]]}
        if isinstance(v, list):
            return {'type': 'list', 'size': len(v)}
        return {'type': type(v).__name__}
    return {
        'present': True,
        'schema': p.get('schema'),
        'fields': {as_key(k): shape(v) for k, v in list(p.items())[:40]},
        'routes_shape': [_route_shape(r) for r in (p.get('config_routes') or [])[:10]],
    }


def _route_shape(r):
    if not isinstance(r, dict):
        return {'type': type(r).__name__}
    return {as_key(k): (type(v).__name__ if not isinstance(v, (str, int, float, bool)) else 'scalar')
            for k, v in list(r.items())[:12]}


def environment():
    info = {
        'python': platform.python_version(),
        'python_implementation': platform.python_implementation(),
        'platform': platform.system(),
        'release': platform.release(),
        'frozen': bool(getattr(sys, 'frozen', False)),
        'pid': os.getpid(),
        'thread': threading.current_thread().name,
        'time': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    try:
        import tkinter
        info['tk'] = str(tkinter.TkVersion)
    except Exception:
        info['tk'] = 'no disponible'
    return info


def log_exception(error, tb=None, context=None, config=None, root=None):
    """Write a redacted crash record. Returns (path, record). Never raises."""
    folder = log_dir(root)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None, {}
    raw = ''.join(traceback.format_exception(type(error), error, tb)) if tb else \
        ''.join(traceback.format_exception_only(type(error), error))
    record = {
        'kind': type(error).__name__,
        'message': redact(str(error), config),
        'traceback': redact(raw, config),
        'context': {as_key(k): redact(str(v)[:400], config)
                    for k, v in (context or {}).items() if isinstance(k, (str, int))},
        'environment': environment(),
        'type_rejections': rejections(),
    }
    name = 'error-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + \
           '-' + str(os.getpid()) + '.json'
    path = folder / name
    try:
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), 'utf-8')
        _prune(folder)
    except Exception:
        return None, record
    return path, record


def _prune(folder):
    files = sorted(folder.glob('error-*.json'), key=lambda f: f.stat().st_mtime, reverse=True)
    for old in files[MAX_LOGS:]:
        try:
            old.unlink()
        except Exception:
            pass


def recent(n=5, root=None):
    folder = log_dir(root)
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob('error-*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:n]:
        try:
            out.append(json.loads(path.read_text('utf-8')))
        except Exception:
            continue
    return out


def friendly(error, path=None, config=None):
    """UI text: actionable, no raw interpreter message, no project content."""
    # The raw interpreter message is in the log, never in the modal: on 3.14
    # it is "cannot use 'dict' as a dict key (unhashable type: 'dict')", which
    # tells the student nothing. Only our own controlled ValueError messages
    # (short, Spanish, actionable) are shown.
    message = redact(str(error), config)
    lines = ['Nexo encontró un error y lo registró sin incluir el contenido de tu tesis.',
             '', 'Tipo: ' + type(error).__name__]
    controlled = isinstance(error, ValueError) and len(message) <= 220 and 'unhashable' not in message
    if controlled:
        lines.append('Motivo: ' + message)
    if path:
        lines += ['', 'Diagnóstico: ' + str(path)]
    lines += ['', 'Pulsa «Copiar diagnóstico» en la pestaña Documento para compartirlo.',
              'No se envió nada a Internet.']
    return '\n'.join(lines)


def wrap_excepthook(config=None, root=None):
    """Install a process-wide hook. Returns the previous hook for tests."""
    previous = sys.excepthook
    def hook(kind, value, tb):
        try:
            log_exception(value, tb, {'origin': 'sys.excepthook'}, config, root)
        except Exception:
            pass
        previous(kind, value, tb)
    sys.excepthook = hook
    return previous


def tk_callback(error, tb=None, config=None, root=None, context=None):
    """Tk `report_callback_exception` replacement. Returns the log path."""
    path, _record = log_exception(error, tb, context, config, root)
    return path
