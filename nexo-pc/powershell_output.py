"""Decode framed PowerShell CLIXML without dropping errors or arbitrary XML."""
import re
import xml.etree.ElementTree as ET

NS='http://schemas.microsoft.com/powershell/2004/04'
MARKER=re.compile(r'(?m)^#< CLIXML\r?\n')
BLOCK=re.compile(r'<Objs\b[^>]*>.*?</Objs>',re.DOTALL)
ESCAPE=re.compile(r'_x([0-9A-Fa-f]{4})_')

def unescape(text):
    # Single pass: an escaped underscore must not trigger a second decoding pass.
    value=ESCAPE.sub(lambda m:chr(int(m.group(1),16)),text)
    return value.encode('utf-16-le','surrogatepass').decode('utf-16-le','replace')

def decode_output(raw):
    if raw.startswith((b'\xff\xfe',b'\xfe\xff')):text=raw.decode('utf-16','replace')
    else:text=raw.decode('utf-8-sig','replace')
    result={'text':text,'progress_omitted':0,'error_record':False,'parse_warning':False,'clixml_detected':False}
    if not MARKER.search(text):return result
    result['clixml_detected']=True
    # Keep the input untouched if it contains an incomplete/unrecognized block.
    pieces=[];offset=0
    for match in BLOCK.finditer(text):
        block=match.group(0)
        try:
            if '<!DOCTYPE' in block or '<!ENTITY' in block:raise ValueError('DTD not accepted')
            root=ET.fromstring(block)
            if root.tag!='{'+NS+'}Objs':raise ValueError('Not PowerShell CLIXML')
        except (ET.ParseError,ValueError):
            result['parse_warning']=True;continue
        prefix=text[offset:match.start()]
        pieces.append(MARKER.sub('',prefix))
        for record in root:
            stream=record.get('S','').lower()
            if stream=='progress':result['progress_omitted']+=1;continue
            if stream=='error':result['error_record']=True
            if record.tag=='{'+NS+'}S':
                message=unescape(record.text or '')
                pieces.append((f'[{stream}] ' if stream else '')+message+'\n')
            else:
                # Unknown/complex records (including detailed ErrorRecord objects)
                # remain lossless rather than being silently thrown away.
                pieces.append(ET.tostring(record,encoding='unicode')+'\n')
        offset=match.end()
    tail=text[offset:]
    if '<Objs' in tail or (offset==0):
        result['parse_warning']=True;pieces.append(tail)
    else:pieces.append(MARKER.sub('',tail))
    result['text']=''.join(pieces).strip('\r\n')
    return result

PRELUDE=("$ProgressPreference = 'SilentlyContinue'; "
         "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); "
         "$OutputEncoding = [Console]::OutputEncoding;\r\n")

def build_arguments(command):
    import base64
    encoded=base64.b64encode((PRELUDE+command).encode('utf-16-le')).decode('ascii')
    return ['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-InputFormat','Text','-OutputFormat','Text','-EncodedCommand',encoded]
