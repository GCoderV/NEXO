"""Durable Copilot conversation link: one chat per project and Microsoft account.

0.4.1-dev changes (diagnosis in contexto/CONTINUIDAD-COPILOT-DIAGNOSTICO.md):
  * persistence is the DEFAULT, not an experimental opt-in that had to be found;
  * the local 40-turn rotation is gone: turns are metadata, never a reason to restart;
  * uncertain results keep their identifiers and require an explicit user decision;
  * the link depends on the signed-in account (oid/tid), not on the credential
    generation, so renewing the captured session does not lose the chat;
  * revoking/retiring material no longer starts another chat silently.

A WebSocket is transport, not a conversation. Nothing here persists tokens, URLs,
cookies, authenticated headers or message bodies: PERSISTED is the complete whitelist.
"""
from datetime import datetime, timezone
import copy
from diagnostics import as_key, as_text
import hashlib
import json
import re

ID = re.compile(r'[a-fA-F0-9-]{32,36}')
ACTIVE = 'active'
UNCERTAIN = 'uncertain'
REBIND = 'rebind_required'
MAX_TURNS = 10_000_000  # sanity bound only; NOT a rotation threshold
PERSISTED = ('conversation', 'session', 'turns', 'status', 'verified', 'server_turn', 'regression')


class ContinuityPending(ValueError):
    """Raised before any request when the user must decide about the current chat."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _digest(parts):
    return hashlib.sha256(json.dumps(list(parts), separators=(',', ':')).encode('utf-8')).hexdigest()


def _accounts(api):
    value = (getattr(getattr(api, 'config', None), 'data', {}) or {}).get('accounts', {}) or {}
    return value if isinstance(value, dict) else {}


def _routes(api):
    value = getattr(api, 'routes', None) or []
    return [r for r in value if isinstance(r, dict)] if isinstance(value, (list, tuple)) else []


def _account_id(route):
    return as_key(route.get('account_id'), 'route.account_id')


def routes(api):
    return [r for r in _routes(api)
            if as_text(r.get('provider'), 'route.provider') == 'Copilot365' and _account_id(r)]


def account_identity(api, aid):
    """Stable account scope. Never returns a token; falls back to the account id."""
    aid = as_key(aid, 'account_identity.aid')
    if not aid:return ''
    record = _accounts(api).get(aid, {}) or {}
    if not isinstance(record, dict):record = {}
    stored = record.get('identity')
    if isinstance(stored, str) and re.fullmatch(r'[a-f0-9]{64}', stored):
        return stored
    getter = getattr(getattr(api, 'config', None), 'secret', None)
    if callable(getter):
        try:
            from copilot_socket import identity_fingerprint
            found = identity_fingerprint(as_text(getter(aid), 'secret'))
            if found:
                return found
        except Exception:
            pass
    return str(aid)


def keys(api):
    """Current keys: identity of the account + endpoint, never the credential generation."""
    return {aid: _digest(['m365-thread-v2', account_identity(api, aid),
                          as_text(r.get('endpoint', ''), 'route.endpoint')])
            for r in routes(api) for aid in [_account_id(r)] if aid}


def legacy_keys(api):
    """0.4.0 keys (generation-based), only used to migrate existing threads."""
    accounts = _accounts(api)
    out = {}
    for r in routes(api):
        aid = _account_id(r)
        if not aid:continue
        record = accounts.get(aid, {}) or {}
        generation = as_text(record.get('generation', ''), 'account.generation') if isinstance(record, dict) else ''
        out[aid] = _digest([aid, generation, as_text(r.get('endpoint', ''), 'route.endpoint')])
    return out


def _slots(p):
    threads = p.get('copilot_threads') if isinstance(p, dict) else None
    return threads if isinstance(threads, dict) else {}


def _migrate(p, api, current, old):
    """Existing 0.4.0 threads survive the key change instead of being orphaned."""
    threads = _slots(p)
    if not threads:
        return
    for aid, key in current.items():
        if key in threads:
            continue
        previous = old.get(aid)
        if previous and valid(threads.get(previous)):
            moved = copy.deepcopy(threads.pop(previous))
            moved.setdefault('status', ACTIVE)
            moved.setdefault('verified', False)
            threads[key] = moved


def valid(slot):
    if not isinstance(slot, dict):
        return False
    if not all(isinstance(slot.get(k), str) and ID.fullmatch(slot[k]) for k in ('conversation', 'session')):
        return False
    turns = slot.get('turns')
    if type(turns) is not int or not 0 <= turns <= MAX_TURNS:
        return False
    if slot.get('status', ACTIVE) not in (ACTIVE, UNCERTAIN, REBIND):
        return False
    if 'verified' in slot and type(slot['verified']) is not bool:
        return False
    server = slot.get('server_turn')
    if server is not None and (type(server) is not int or not 0 <= server <= MAX_TURNS):
        return False
    if 'regression' in slot and type(slot['regression']) is not bool:
        return False
    return True


def load(p, api):
    """Return {account_id: slot}. No opt-in gate, no turn rotation, no silent reset."""
    current = keys(api)
    if not current:
        return {}
    _migrate(p, api, current, legacy_keys(api))
    threads = _slots(p)
    affinity = bool(p.get('copilot_affinity', True))
    out = {}
    for aid, key in current.items():
        slot = threads.get(key)
        if not valid(slot):
            continue
        value = copy.deepcopy({k: slot[k] for k in PERSISTED if k in slot})
        value.setdefault('status', ACTIVE)
        value.setdefault('verified', False)
        value['affinity'] = affinity  # transient protocol flag, never persisted by save()
        out[aid] = value
    return out


def save(p, api, remote, uncertain=False):
    """Persist the link. `uncertain` marks a decision, it does NOT discard identifiers."""
    current = keys(api)
    if not current:
        return
    threads = p.setdefault('copilot_threads', {})
    for aid, key in current.items():
        slot = (remote or {}).get(aid) if isinstance(remote, dict) else None
        if not isinstance(slot, dict) or not all(
                isinstance(slot.get(k), str) and ID.fullmatch(slot[k]) for k in ('conversation', 'session')):
            # No usable ids from a failed attempt: keep the stored link and flag it,
            # rather than deleting it and silently starting another chat next turn.
            stored = threads.get(key)
            if valid(stored):
                if uncertain:stored['status'] = UNCERTAIN
                elif p.get('copilot_rebind'):stored['status'] = REBIND
            continue
        if uncertain or slot.get('uncertain') or slot.get('status') == UNCERTAIN:
            status = UNCERTAIN
        elif slot.get('status') == REBIND:
            status = REBIND
        else:
            status = slot.get('status', ACTIVE)
        record = {k: copy.deepcopy(slot[k]) for k in PERSISTED if k in slot and k != 'status'}
        record['turns'] = slot.get('turns', 0)
        record['status'] = status
        record.setdefault('verified', False)
        if not valid(record):
            continue
        threads[key] = record
    if uncertain or p.get('copilot_rebind'):
        # A loss of continuity (or a revocation) invalidates incremental assumptions.
        p.pop('copilot_ledger', None)


def flag_rebind(p, reason):
    """Revocation/retirement: require a visible decision; do not pop the thread here."""
    slots = [s for s in _slots(p).values() if valid(s)]
    p.pop('copilot_ledger', None)
    if not slots:
        # No remote chat exists yet: nothing to rebind, no decision to ask for.
        p.pop('copilot_rebind', None)
        return None
    p['copilot_rebind'] = {'reason': str(reason)[:400], 'time': _now()}
    for slot in slots:
        slot['status'] = REBIND
    return p['copilot_rebind']


def resolve(p, api=None, mode='keep'):
    """Explicit decision after uncertainty or revocation.

    keep   -> retain ids, continuity unconfirmed, force a full context next turn;
    verify -> retain ids and record the user's own acceptance test as verified;
    rebind -> drop local ids; the next turn starts a new, explained chat.
    """
    if mode not in ('keep', 'verify', 'rebind'):
        raise ValueError('Decisión de continuidad no válida.')
    threads = _slots(p)
    needs_clean = p.get('copilot_rebind') or any(
        s.get('status') == REBIND for s in threads.values() if valid(s))
    if mode == 'verify' and needs_clean:
        raise ValueError('Hay una revocación pendiente. Decide «Iniciar un hilo limpio» o conserva el hilo de forma explícita; no se puede marcar como verificado sin esa decisión.')
    if mode == 'rebind':
        p.pop('copilot_threads', None)
        p.pop('copilot_ledger', None)
        p.pop('copilot_rebind', None)
        return {'mode': mode, 'threads': 0}
    count = 0
    for key, slot in list(threads.items()):
        if not valid(slot):
            continue
        was_rebind = slot.get('status') == REBIND
        slot['status'] = ACTIVE
        slot['verified'] = True if mode == 'verify' else (False if was_rebind else bool(slot.get('verified')))
        threads[key] = slot
        count += 1
    p.pop('copilot_rebind', None)
    if mode == 'keep':
        p.pop('copilot_ledger', None)
    return {'mode': mode, 'threads': count}


def pending(p, api=None):
    """A decision required before sending anything else, or None."""
    threads = _slots(p)
    # With an explicit api that has no Copilot route, another provider's turn is
    # unrelated to the pending Copilot decision. The UI (api=None) still shows it.
    candidates = [as_key(k) for k in (keys(api).values() if api is not None else threads.keys())]
    candidates = [k for k in candidates if k]
    for key in candidates:
        slot = threads.get(key)
        if not valid(slot):
            continue
        if slot.get('status') == UNCERTAIN:
            return {'kind': 'uncertain', 'turns': slot['turns'], 'message':
                    'La última petición pudo llegar a Microsoft sin confirmación. Para no duplicar ni '
                    'abrir otro chat en silencio, abre «Hilo Copilot» y elige: conservar este hilo y '
                    'reenviar el contexto completo, o iniciar un hilo limpio. No se envió nada nuevo.'}
        if slot.get('status') == REBIND or p.get('copilot_rebind'):
            return {'kind': 'rebind', 'reason': (p.get('copilot_rebind') or {}).get('reason', ''), 'message':
                    'Se revocó o retiró material. Lo ya enviado permanece en el chat de Microsoft; '
                    'revocar no borra su memoria. Abre «Hilo Copilot» y decide explícitamente si '
                    'necesitas un hilo limpio por privacidad o si conservas el actual. No se envió nada nuevo.'}
    return None


def can_increment(p, api):
    """Incremental messages only on a verified, healthy, Copilot-only thread."""
    if pending(p, api):
        return False
    configured = getattr(api, 'routes', None)
    if configured is not None:
        if not configured or any(r.get('provider') != 'Copilot365' for r in configured):
            return False
    elif getattr(api, 'provider', '') != 'Copilot365':
        return False
    threads = _slots(p)
    slots = [threads.get(k) for k in keys(api).values()]
    if not slots or not all(valid(s) and s.get('status') == ACTIVE and s.get('verified')
                            and not s.get('regression') for s in slots):
        return False
    ledger = p.get('copilot_ledger')
    return isinstance(ledger, dict) and isinstance(ledger.get('snapshot'), dict)


def summary(p, api=None):
    """UI-facing metadata only: masked id, counters and state. No secrets, no URLs."""
    threads = _slots(p)
    current = keys(api) if api is not None else {}
    chosen = list(current.items()) if current else list(threads.items())
    out = []
    for aid, key in chosen:
        slot = threads.get(key, {}) or {}
        linked = valid(slot)
        conversation = slot.get('conversation', '') if linked else ''
        out.append({'account': aid, 'link': linked,
                    'conversation': conversation[:8] + '…' if conversation else '',
                    'turns': slot.get('turns', 0) if linked else 0,
                    'status': slot.get('status', 'new') if linked else 'new',
                    'verified': bool(slot.get('verified')) if linked else False,
                    'server_turn': slot.get('server_turn') if linked else None,
                    'regression': bool(slot.get('regression')) if linked else False})
    return out
