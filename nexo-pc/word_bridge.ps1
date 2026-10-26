# Nexo fixed native Word adapter. Input is JSON through stdin, never evaluated.
# No new Word instance, no macros, no document opening, no auto-save, no replacement.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Hash-Text([string]$value) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($value)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Result($value) { [Console]::WriteLine(($value | ConvertTo-Json -Depth 8 -Compress)) }
try {
    $req = [Console]::ReadToEnd() | ConvertFrom-Json
    if ($req.action -notin @('list','read','comment')) { throw 'Operacion no permitida.' }
    $word = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application')
    if ($req.action -eq 'list') {
        $items = @()
        foreach ($d in $word.Documents) {
            if ($d.Path -and [IO.Path]::GetExtension($d.FullName) -ieq '.docx') {
                $items += @{path=[string]$d.FullName; name=[string]$d.Name; readonly=[bool]$d.ReadOnly}
            }
        }
        Result @{ok=$true; documents=$items; version=[string]$word.Version}; exit 0
    }
    $path = [string]$req.path
    if (-not [IO.Path]::IsPathRooted($path) -or [IO.Path]::GetExtension($path) -ine '.docx') { throw 'Confirma un documento DOCX guardado.' }
    $doc = $null
    foreach ($d in $word.Documents) { if ([string]::Equals([string]$d.FullName,$path,[StringComparison]::OrdinalIgnoreCase)) { $doc=$d; break } }
    if ($null -eq $doc) { throw 'El documento confirmado ya no esta abierto en esta instancia de Word.' }
    if (-not [string]::Equals([string]$word.ActiveDocument.FullName,$path,[StringComparison]::OrdinalIgnoreCase)) { throw 'Activa el documento confirmado en Word. No se leera otro documento.' }
    $sel=$word.Selection
    if ($sel.Type -ne 2 -or $sel.StoryType -ne 1 -or $sel.End -le $sel.Start) { throw 'Selecciona texto continuo del cuerpo principal, no un cursor, tabla, encabezado o comentario.' }
    $range=$sel.Range.Duplicate
    if ($range.Tables.Count -gt 0) { throw 'Esta version no admite selecciones dentro de tablas.' }
    $text=[string]$range.Text
    if ($text.Length -gt 12000) { throw 'Selecciona un apartado de hasta 12000 caracteres.' }
    $hash=Hash-Text $text
    $snapshot=@{path=$path; hwnd=[long]$word.ActiveWindow.Hwnd; start=[int]$range.Start; end=[int]$range.End; hash=$hash; text=$text}
    if ($req.action -eq 'read') { Result @{ok=$true; snapshot=$snapshot}; exit 0 }
    if ($doc.ReadOnly -or $doc.ProtectionType -ne -1) { throw 'Documento de solo lectura o protegido; no se modifico.' }
    $expected=$req.snapshot
    if ($null -eq $expected -or $expected.path -cne $path -or [long]$expected.hwnd -ne $snapshot.hwnd -or [int]$expected.start -ne $snapshot.start -or [int]$expected.end -ne $snapshot.end -or $expected.hash -cne $hash) {
        throw 'El documento, ventana o seleccion cambio. Vuelve a leer y revisar antes de comentar.'
    }
    $comment=[string]$req.comment
    $operation=[string]$req.operation
    if ($comment.Trim().Length -eq 0 -or $comment.Length -gt 6000 -or $operation -notmatch '^[a-f0-9]{32}$') { throw 'Comentario u operacion invalida.' }
    $marker='[Nexo:'+ $operation +']'
    foreach ($c in $doc.Comments) {
        if (([string]$c.Range.Text).Contains($marker)) { Result @{ok=$true; duplicate=$true; operation=$operation; saved=$false}; exit 0 }
    }
    # Revalidate immediately before mutation. The GUI asks the user not to edit during this brief operation.
    if ((Hash-Text ([string]$range.Text)) -cne $hash) { throw 'La seleccion cambio; operacion cancelada.' }
    $c=$doc.Comments.Add($range,($comment+"`r"+$marker))
    if (-not ([string]$c.Range.Text).Contains($marker)) { throw 'No se pudo verificar el comentario. Inspecciona Word antes de reintentar.' }
    Result @{ok=$true; operation=$operation; comment_index=[int]$c.Index; saved=$false; text_unchanged=((Hash-Text ([string]$range.Text)) -ceq $hash)}
} catch {
    Result @{ok=$false; error=$_.Exception.Message; warning='Si la operacion era comentar, inspecciona Word: un error puede ocurrir despues de una modificacion parcial. No hay reintento automatico.'}
    exit 1
}
