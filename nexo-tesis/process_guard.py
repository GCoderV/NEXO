"""Fase 0: no orphan Copilot/Edge windows after a failed connection.

`copilot_socket.launch_desktop()` / `launch_auth_window()` start browser-like
processes with a localhost debugging port. Their source is intentionally left
byte-identical to the shipped 0.3.1 functions (a legacy invariant test pins it),
because real Windows behaviour is not verifiable in this sandbox. Instead of
editing them, this module temporarily wraps `subprocess.Popen` while a
connection is attempted, records every child, and terminates them in a
`finally` block. No process is killed unless Nexo started it in this session.
"""
import subprocess
import threading

_lock = threading.RLock()
_tracked = []
_original = None


def start_tracking():
    """Begin recording Popen children. Idempotent, restores exactly once."""
    global _original
    with _lock:
        if _original is not None:
            return
        _original = subprocess.Popen

        def tracked(*args, **kwargs):
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            kwargs.setdefault('creationflags', flags)
            proc = _original(*args, **kwargs)
            with _lock:
                _tracked.append(proc)
            return proc

        subprocess.Popen = tracked


def stop_tracking():
    """Restore Popen WITHOUT terminating children (caller may need them)."""
    global _original
    with _lock:
        if _original is None:
            return
        subprocess.Popen = _original
        _original = None


def close_all():
    """Terminate only processes Nexo started in this session. Returns count."""
    with _lock:
        targets = list(_tracked)
        _tracked.clear()
    stop_tracking()
    closed = 0
    for proc in targets:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
            closed += 1
        except Exception:
            continue
    return closed


def count():
    with _lock:
        return len(_tracked)
