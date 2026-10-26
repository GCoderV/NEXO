"""Host-side task capabilities, separate from model-provided prose.
The prose plan describes intent; it is NOT a semantic sandbox.
"""
import copy

class Authorization:
    def __init__(self,mode,policy,enabled,workspace,review,broad=False,max_calls=16,max_actions=48):
        if policy not in ('step','plan','auto'):raise ValueError('Política desconocida.')
        self.mode=mode;self.policy=policy;self.enabled=frozenset(enabled);self.workspace=str(workspace)
        self.review=review;self.broad=broad is True;self.granted=False;self.denied=False;self.last_plan=None
        self.limits={'model_requests':max_calls,'tool_actions':max_actions}
    @staticmethod
    def wide(name,args):
        return name in ('powershell','desktop') or (name=='browser' and args.get('action') in ('click','fill'))
    def ask(self,name,details):
        return self.review is not None and self.review(name,copy.deepcopy(details)) is True
    def authorize(self,name,details):
        if name=='submit_plan':
            if self.mode!='ACT' or self.policy!='plan' or self.denied:return False
            args=details['arguments']
            if args==self.last_plan and self.granted:return True
            self.granted=False
            decision=self.ask('execution_plan',{
                'plan':args,'workspace':self.workspace,'tools':sorted(self.enabled-{'submit_plan'}),
                'limits':self.limits,'wide_tools_included':self.broad,
                'scope':'Una tarea, hasta terminar, detener o alcanzar límites. Archivos: toda la carpeta elegida y subcarpetas.',
                'warning':('También autoriza comandos y controles habilitados sin revisar cada paso. PowerShell/escritorio NO están aislados en la carpeta; navegador puede enviar datos.' if self.broad else 'PowerShell, escritorio y clics/rellenos del navegador se revisan individualmente. Puedes incluirlos expresamente desde Configuración > Permisos.'),
                'note':'El alcance se controla por herramientas, carpeta y presupuesto, no por comprensión perfecta del texto del plan. No se autorizan herramientas desactivadas.'})
            self.granted=decision;self.denied=not decision;self.last_plan=copy.deepcopy(args) if decision else None
            return decision
        if self.denied:return False
        if name not in self.enabled:return False
        if self.mode=='PLAN':
            if name not in ('read_file','list_files'):return False
            return self.ask(name,details) if self.policy=='step' else True
        if self.policy=='step':return self.ask(name,details)
        if self.policy=='plan' and name not in ('read_file','list_files') and not self.granted:
            raise ValueError('Primero presenta submit_plan y espera su aprobación. Si se rechaza, detén la tarea.')
        if self.wide(name,details['arguments']) and not self.broad:
            return self.ask(name,details)
        return True
