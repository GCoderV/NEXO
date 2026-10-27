"""Fase 2: continuous agent policy. Chat and Auto use the same bounded loop.

The user asked for an agent that "haga todas las investigaciones del lugar,
complete todos los pasos sin una cuota de pasos específica y repita el loop
hasta terminar el trabajo". So `max_passes=None` removes the STEP QUOTA. The
loop still has non-quota safety limits, all of them visible and configurable:

* wall clock (`max_seconds`) — a run cannot bill forever;
* `max_stalls` — consecutive passes with NO measurable state change, after the
  loop has tried different strategies (a stuck model is not "finished work");
* `hard_fuse` — an absolute ceiling on model calls, a fuse against a provider
  or tool bug, never presented as a step quota;
* a human boundary (`preguntar_usuario`) and the Detener button.

Completion is decided by `project_state.verify()` (content + deterministic
gates), never by the model saying "listo". Adapted from DoThesis's
`RunProfile` / `run_headless` and Loopy's receipt/stopping-reason pattern.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict

from project_state import MODULES, MODULE_LABELS

STRATEGIES = (
    'Cambia de estrategia: usa ver_documento/ver_pendientes y ataca el primer '
    'apartado pendiente con escribir_apartado; no repitas la herramienta anterior.',
    'Cambia de estrategia: si el apartado ya existe, usa editar_texto con un '
    'fragmento exacto para completar SOLO lo que falta; conserva el resto.',
    'Cambia de estrategia: simplifica las consultas y busca fuentes con otros '
    'términos; si no hay red, registra fuentes a mano con la herramienta disponible.',
    'Cambia de estrategia: divide el trabajo — redacta primero los apartados '
    'obligatorios cortos y deja los opcionales para el final.',
    'Cambia de estrategia: revisa las puertas duras (citas inexistentes, cifras '
    'sin datos, apartados incompletos) y corrígelas antes de seguir escribiendo.',
    'Cambia de estrategia: si falta información del usuario, llama '
    'preguntar_usuario con UNA pregunta concreta y espera su respuesta.',
)


@dataclass
class RunProfile:
    """Mode differences are DATA, not a second brain."""
    goal: str = 'Completar el trabajo de tesis pendiente'
    interactive: bool = False
    max_passes: int | None = None       # None => SIN CUOTA DE PASOS
    max_seconds: int = 3600             # tope de tiempo, no cuota
    max_stalls: int = 10                # tras agotar estrategias distintas
    hard_fuse: int = 300                # fusible absoluto de llamadas
    required_modules: tuple = tuple(MODULES)
    allow_research: bool = True
    auto_research: bool = True          # investiga en sitio sin esperar al modelo
    allow_export: bool = True
    include_optional: bool = True
    export_dir: str = ''
    producer: str = 'agente-continuo'

    def loop_config(self):
        """Dict consumed by Agent.turn(loop=...)."""
        return {'goal': self.goal, 'max_passes': self.max_passes,
                'max_seconds': self.max_seconds, 'max_stalls': self.max_stalls,
                'hard_fuse': self.hard_fuse, 'continuous': True,
                'auto_research': self.auto_research,
                'allow_research': self.allow_research,
                'allow_export': self.allow_export,
                'include_optional': self.include_optional,
                'export_dir': self.export_dir,
                'required_modules': list(self.required_modules),
                'producer': self.producer}

    def describe(self):
        return ('Sin cuota de pasos; se repite hasta que la verificación diga '
                '"trabajo terminado". Topes de seguridad: ' +
                str(self.max_seconds // 60) + ' min, ' + str(self.max_stalls) +
                ' pasos sin progreso tras cambiar de estrategia, fusible de ' +
                str(self.hard_fuse) + ' llamadas, y el botón Detener.')


def strategy_nudge(stalls, verification=None):
    """Change the approach instead of stopping at the first no-op."""
    index = min(max(stalls - 1, 0), len(STRATEGIES) - 1)
    text = STRATEGIES[index]
    if verification and verification.get('next', {}).get('reason'):
        text += '\nSiguiente paso derivado del estado: ' + verification['next']['reason']
    if verification and verification.get('blocked'):
        text += '\nBloqueos: ' + '; '.join(verification['blocked'][:3])
    if verification and verification.get('missing'):
        text += '\nPendientes: ' + '; '.join(verification['missing'][:5])
    return text


def evaluate(p, state, profile=None, now_monotonic=None):
    """Decide whether the loop should stop. Returns {'stop','verification','nudge'}."""
    from project_state import verify
    profile = profile or RunProfile()
    clock = now_monotonic if now_monotonic is not None else time.monotonic()
    verification = verify(p, profile.include_optional)
    result = {'stop': None, 'verification': verification, 'nudge': ''}
    if verification['done']:
        result['stop'] = 'trabajo_completado'
        return result
    started = state.get('started_at')
    if started is not None and clock - started >= profile.max_seconds:
        result['stop'] = 'tiempo_agotado'
        return result
    if state.get('passes', 0) >= profile.hard_fuse:
        result['stop'] = 'fusible_de_seguridad'
        return result
    if profile.max_passes is not None and state.get('passes', 0) >= profile.max_passes:
        result['stop'] = 'limite_de_pasos_configurado'
        return result
    if state.get('stalls', 0) >= profile.max_stalls:
        result['stop'] = 'sin_progreso_tras_cambiar_estrategia'
        return result
    if state.get('stalls', 0) > 0:
        result['nudge'] = strategy_nudge(state['stalls'], verification)
    return result


def receipt(p, state, profile=None, reason=''):
    """Auditable end-of-run record: actions, evidence, outcome, stop reason."""
    from project_state import status_map
    profile = profile or RunProfile()
    verification = state.get('verification') or {}
    actions = state.get('actions', [])[-60:]
    return {
        'goal': profile.goal,
        'profile': {k: v for k, v in asdict(profile).items() if k != 'goal'},
        'passes': state.get('passes', 0),
        'model_calls': state.get('passes', 0),
        'changes': state.get('changed', 0),
        'research_rounds': state.get('research_rounds', 0),
        'stopped': reason,
        'actions': actions,
        'verification': {
            'done': verification.get('done'),
            'score': verification.get('score'),
            'missing': verification.get('missing', [])[:20],
            'blocked': verification.get('blocked', [])[:20],
            'warnings': verification.get('warnings', [])[:20],
            'status': verification.get('status') or status_map(p),
        },
        'state': {'sections': len(p.get('drafts', {})),
                  'sources': len(p.get('sources', [])),
                  'modules': status_map(p)},
    }
