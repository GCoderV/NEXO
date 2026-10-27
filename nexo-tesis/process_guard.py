"""Fase 0: no orphan Copilot/Edge windows after a FAILED connection.

`copilot_socket.launch_desktop()` / `launch_auth_window()` start browser-like
processes with a localhost debugging port. Their source is intentionally left
byte-identical to the shipped 0.3.1 functions (a legacy invariant test pins it),
because real Windows behaviour is not verifiable in this sandbox. Instead of
editing them, this module temporarily wraps `subprocess.Popen` while a
connection is attempted and records every child Nexo started in this session.

POLICY (fix for "luego de capturar la sesión el bot cierra Copilot automáticamente"):

* On SUCCESS the browser MUST stay alive. Nexo keeps using that process's local
  CDP debugging port for every subsequent turn; killing it right after saving
  the session makes the very next request fail. `detach_all()` therefore only
  stops tracking and clears the registry, WITHOUT terminating anything.
* On FAILURE or cancellation `close_all()` terminates the tracked children, so
  a blank WebView2 / Edge window is not left behind.
* Closing the settings dialog NEVER closes Copilot: it only calls
  `stop_tracking()`. The user decides when to close their own app.

Never call `close_all()` from a `finally` block around a successful capture.
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


def detach_all():
    """Release tracked children WITHOUT killing them. Returns the count.

    Used after a SUCCESSFUL session capture: Copilot/Edge must remain open
    because Nexo reuses its local debugging port. This is deliberately not a
    synonym for `close_all()`.
    """
    with _lock:
        count = len(_tracked)
        _tracked.clear()
    stop_tracking()
    return count


def close_all():
    """Terminate tracked children. Call ONLY after a failed/cancelled attempt.

    Never on the success path: the captured session lives in that process.
    Returns the number of processes that were asked to terminate.
    """
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


def guarded_capture(launch, capture):
    """Launch Copilot/Edge, capture the session, and clean up only on failure.

    `launch()` starts the process (and returns a local debugging port);
    `capture(port)` returns the observed session secret. On success the
    processes are DETACHED, never terminated: Nexo needs them alive for every
    later turn. On error/cancellation they are terminated.

    This is the single place where the policy is enforced, so the Tk dialog
    does not have to remember to do the right thing in a `finally` block.
    Tested with synthetic Popen doubles; no Windows process is touched here.
    """
    start_tracking()
    try:
        port = launch()
        result = capture(port)
    except Exception:
        close_all()
        raise
    else:
        detach_all()
        return result


def count():
    with _lock:
        return len(_tracked)
