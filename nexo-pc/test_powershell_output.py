"""PowerShell output regression tests; fixture tests do not execute PowerShell."""
import base64
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from adapters import Tools
from powershell_output import build_arguments, decode_output, NS

PROGRESS='<Obj S="progress" RefId="0"><TN RefId="0"><T>System.Management.Automation.PSCustomObject</T><T>System.Object</T></TN><MS><I64 N="SourceId">1</I64><PR N="Record"><AV>Preparando módulos para el primer uso.</AV><AI>0</AI><Nil /><PI>-1</PI><PC>-1</PC><T>Completed</T><SR>-1</SR><SD> </SD></PR></MS></Obj>'
def frame(records,prefix=''):
    return ('#< CLIXML\r\n'+prefix+f'<Objs Version="1.1.0.1" xmlns="{NS}">'+records+'</Objs>').encode('utf-8')

class DecodeTests(unittest.TestCase):
    def test_reported_true_and_progress(self):
        r=decode_output(frame(PROGRESS+PROGRESS,'True\r\n'))
        self.assertEqual(r['text'],'True');self.assertEqual(r['progress_omitted'],2);self.assertFalse(r['parse_warning'])
    def test_reported_progress_only(self):
        r=decode_output(frame(PROGRESS));self.assertEqual(r['text'],'');self.assertEqual(r['progress_omitted'],1)
    def test_error_not_hidden(self):
        r=decode_output(frame(PROGRESS+'<S S="Error">Acceso denegado_x000D__x000A_Archivo ocupado</S>'))
        self.assertTrue(r['error_record']);self.assertIn('Acceso denegado\r\nArchivo ocupado',r['text'])
    def test_warning_not_hidden(self):
        r=decode_output(frame('<S S="warning">Advertencia importante</S>'))
        self.assertIn('Advertencia importante',r['text']);self.assertFalse(r['error_record'])
    def test_complex_error_kept(self):
        r=decode_output(frame('<Obj S="Error"><MS><S N="Message">El archivo no existe</S><I32 N="Code">123</I32></MS></Obj>'))
        self.assertTrue(r['error_record']);self.assertIn('El archivo no existe',r['text']);self.assertIn('123',r['text'])
    def test_normal_output_unchanged(self):
        self.assertEqual(decode_output('Información útil\r\n'.encode())['text'],'Información útil\r\n')
    def test_arbitrary_xml_unchanged(self):
        raw=b'<Objs><S>XML del usuario</S></Objs>';self.assertEqual(decode_output(raw)['text'],raw.decode())
    def test_wrong_namespace_not_silently_discarded(self):
        raw=b'#< CLIXML\n<Objs xmlns="user"><Obj S="progress">important</Obj></Objs>'
        r=decode_output(raw);self.assertEqual(r['text'],raw.decode());self.assertTrue(r['parse_warning'])
    def test_truncated_xml_retained(self):
        raw=frame(PROGRESS)[:-9];r=decode_output(raw);self.assertEqual(r['text'],raw.decode());self.assertTrue(r['parse_warning'])
    def test_escaped_underscore_decoded_once(self):
        r=decode_output(frame('<S>_x005F_x0041_</S>'));self.assertEqual(r['text'],'_x0041_')
    def test_surrogate_unicode_pair(self):
        self.assertIn('😀',decode_output(frame('<S>_xD83D__xDE00_</S>'))['text'])
    def test_utf16_bom(self):
        self.assertEqual(decode_output('Español'.encode('utf-16'))['text'],'Español')
    def test_command_kept_exactly_after_prelude(self):
        command='Write-Output "áéñ"\nWrite-Error "fallo"';args=build_arguments(command)
        script=base64.b64decode(args[-1]).decode('utf-16-le')
        self.assertTrue(script.endswith(command));self.assertIn("$ProgressPreference = 'SilentlyContinue'",script)
        self.assertEqual(args[args.index('-OutputFormat')+1],'Text');self.assertNotIn("$ErrorActionPreference = 'SilentlyContinue'",script)

class ProcessCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name)
        self.tools=Tools(base/'work',threading.Event(),'Groq',base/'data')
    def tearDown(self):self.tools.close();self.temp.cleanup()
    def capture(self,stdout,stderr,code=0):
        observed={}
        class Process:
            def __init__(self,args,**kwargs):
                observed.update(kwargs);observed['args']=args
                kwargs['stdout'].write(stdout);kwargs['stdout'].flush()
                kwargs['stderr'].write(stderr);kwargs['stderr'].flush()
            def poll(self):return code
            def wait(self,timeout):return code
        with patch('adapters.os.name','nt'),patch('adapters.subprocess.CREATE_NEW_PROCESS_GROUP',0,create=True),patch('adapters.subprocess.Popen',Process):
            result=self.tools.powershell('Write-Output "True"')
        return result,observed
    def test_streams_are_separate(self):
        result,observed=self.capture(b'True\r\n',frame(PROGRESS))
        self.assertIsNot(observed['stdout'],observed['stderr']);self.assertEqual(result['output'],'True\r\n');self.assertEqual(result['stderr'],'')
        self.assertEqual(result['progress_records_omitted'],1);self.assertIsNone(self.tools.process)
    def test_zero_exit_does_not_hide_stderr_or_mean_verified(self):
        result,_=self.capture(b'',frame('<S S="Error">fallo</S>'),0)
        self.assertEqual(result['exit_code'],0);self.assertIn('fallo',result['stderr']);self.assertTrue(result['powershell_error_record']);self.assertTrue(result['verification_required'])
    def test_plain_stderr_preserved_nonzero_exit(self):
        result,_=self.capture(b'',b'Native executable failed',7)
        self.assertEqual(result['exit_code'],7);self.assertEqual(result['stderr'],'Native executable failed')
    def test_truncation_indicated(self):
        result,_=self.capture(b'x'*17000,b'error')
        self.assertTrue(result['output_may_be_truncated']);self.assertEqual(len(result['output']),16000);self.assertEqual(result['stderr'],'error')
    @unittest.skipUnless(os.name=='nt','Actual Windows PowerShell required')
    def test_windows_text_progress_and_error(self):
        result=self.tools.powershell('Write-Progress -Activity "Preparando prueba" -Status "En curso"; Write-Output "Texto español"; Write-Error "Error de prueba"')
        self.assertIn('Texto español',result['output']);self.assertNotIn('<Objs',result['output']);self.assertIn('Error de prueba',result['stderr'])

if __name__=='__main__':unittest.main(verbosity=2)
