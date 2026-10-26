"""Read-only citation normalization. Returned links are not evidence of reading a source."""
from urllib.parse import urlsplit,urlunsplit

def references(obj):
    out=[]
    if not isinstance(obj,dict):return out
    for key in ('sourceAttributions','attributions','citations'):
        values=obj.get(key,[])
        if isinstance(values,dict):values=[values]
        if not isinstance(values,list):continue
        for x in values[:30]:
            if not isinstance(x,dict):continue
            value=x.get('seeMoreUrl') or x.get('url') or x.get('link')
            if not isinstance(value,str) or len(value)>3000:continue
            try:
                u=urlsplit(value)
                if u.scheme not in ('https','http') or not u.hostname or u.username or u.password:continue
                # Credentials/session parameters are never persisted. This can make a temporary link unusable.
                url=urlunsplit((u.scheme,u.netloc,u.path,'',''))
            except ValueError:continue
            title=x.get('displayName') or x.get('title') or x.get('name') or u.hostname
            out.append({'title':str(title)[:400],'url':url,'marker':str(x.get('referenceId',x.get('id','')))[:80],'status':'referencia devuelta por Copilot; contenido no verificado; parámetros de enlace omitidos'})
    return out
