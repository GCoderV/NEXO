"""Bounded extraction subprocess, no network, macros or arbitrary commands."""
import json,sys
try:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(700*1024*1024,700*1024*1024))
    except ImportError:pass
    from materials import extract
    req=json.loads(sys.stdin.buffer.read(20000).decode('utf-8'));result=extract(req['path'])
except Exception as e:result={'error':str(e)[:400]}
sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
