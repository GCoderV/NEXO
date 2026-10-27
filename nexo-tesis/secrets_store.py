"""Current-user DPAPI, independent academic settings. No plaintext fallback."""
import base64, ctypes, os
class WindowsProtector:
    """DPAPI current user, UI forbidden. Same Windows account can decrypt."""
    def _crypt(self, data, decrypt=False):
        if os.name!='nt':
            raise RuntimeError('Guardar claves requiere Windows DPAPI. No se guardarán en texto plano; puedes usarlas solo durante esta sesión.')
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
        buf=ctypes.create_string_buffer(data)
        src=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
        crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        fn.restype=wintypes.BOOL
        kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
        if not fn(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not out.pbData or not out.cbData:return b''
            return ctypes.string_at(out.pbData,out.cbData)
        finally:
            # LocalFree expects HLOCAL; a typed POINTER(c_ubyte) can raise
            # ArgumentError on some Python builds, leaking the DPAPI buffer.
            if out.pbData:kernel.LocalFree(ctypes.cast(out.pbData,ctypes.c_void_p))
    def seal(self,text):return base64.b64encode(self._crypt(text.encode('utf-8'))).decode('ascii')
    def open(self,text):return self._crypt(base64.b64decode(text,validate=True),True).decode('utf-8')

