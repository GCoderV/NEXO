# Nexo fixed native Word adapter. Input is JSON through stdin, never evaluated.
# Opening/creating an unsaved document requires explicit UI approval. No macros, auto-save or replacement. Insertions are tracked.
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
    $req = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($req.action -notin @('list','read','comment','insert','create','open','inspect','layout')) { throw 'Operacion no permitida.' }
    if ($req.action -eq 'insert') {Set-NexoFormat $req.format_profile}
    if ($req.action -in @('create','open') -and ($req.approved -isnot [bool] -or $req.approved -ne $true -or [string]$req.operation -notmatch '^[a-f0-9]{32}$')) { throw 'Falta aprobacion explicita para abrir o crear en Word.' }
    try { $word = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application') }
    catch {
        if ($req.action -in @('create','open')) { $word = New-Object -ComObject Word.Application }
        else { throw 'No se pudo conectar con Word de escritorio. Abre el documento en Word y vuelve a Nexo; ambos deben ejecutarse con el mismo usuario y nivel de permisos. No ejecutes como administrador para sortear este error.' }
    }
    if ($req.action -eq 'create') {
        $word.Visible=$true
        $newDoc=$word.Documents.Add()
        $newDoc.Activate()
        Result @{ok=$true; operation=[string]$req.operation; name=[string]$newDoc.Name; created=$true; saved=$false}; exit 0
    }
    if ($req.action -eq 'open') {
        $openPath=[string]$req.path
        if (-not [IO.Path]::IsPathRooted($openPath) -or [IO.Path]::GetExtension($openPath) -ine '.docx' -or -not [IO.File]::Exists($openPath)) { throw 'Elige un DOCX existente con una ruta completa. No se admiten URLs de documentos.' }
        $opened=$null
        foreach ($d in $word.Documents) { if ([string]::Equals([string]$d.FullName,$openPath,[StringComparison]::OrdinalIgnoreCase)) { $opened=$d; break } }
        if ($null -eq $opened) {
            $oldSecurity=$word.AutomationSecurity
            $oldLinks=$word.Options.UpdateLinksAtOpen
            try {
                $word.AutomationSecurity=3
                $word.Options.UpdateLinksAtOpen=$false
                $opened=$word.Documents.Open($openPath,$false,$false,$false)
            } finally { $word.AutomationSecurity=$oldSecurity; $word.Options.UpdateLinksAtOpen=$oldLinks }
        }
        if (-not [string]::Equals([string]$opened.FullName,$openPath,[StringComparison]::OrdinalIgnoreCase)) { throw 'Word no confirmo el archivo seleccionado. Revisa su ventana antes de repetir.' }
        $word.Visible=$true; $opened.Activate()
        Result @{ok=$true; operation=[string]$req.operation; opened=$true; path=[string]$opened.FullName; name=[string]$opened.Name; readonly=[bool]$opened.ReadOnly; saved=$false}; exit 0
    }
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
    if ($req.action -in @('inspect','layout')) { Invoke-NexoLayout $req $doc $word; exit 0 }
    $sel=$word.Selection
    if ($sel.Type -notin @(1,2) -or $sel.StoryType -ne 1 -or $sel.End -lt $sel.Start) { throw 'Selecciona texto continuo o un punto de insercion en el cuerpo principal, no tablas, encabezados o comentarios.' }
    $range=$sel.Range.Duplicate
    if ($range.Tables.Count -gt 0) { throw 'Esta version no admite selecciones dentro de tablas.' }
    $text=if ($range.Start -eq $range.End) { '' } else { [string]$range.Text }
    if ($text.Length -gt 12000) { throw 'Selecciona un apartado de hasta 12000 caracteres.' }
    $hash=Hash-Text $text
    $snapshot=@{path=$path; hwnd=[long]$word.ActiveWindow.Hwnd; start=[int]$range.Start; end=[int]$range.End; hash=$hash; text=$text; collapsed=($range.Start -eq $range.End)}
    if ($req.action -eq 'read') { Result @{ok=$true; snapshot=$snapshot}; exit 0 }
    if ($doc.ReadOnly -or $doc.ProtectionType -ne -1) { throw 'Documento de solo lectura o protegido; no se modifico.' }
    $expected=$req.snapshot
    if ($null -eq $expected -or $expected.path -cne $path -or [long]$expected.hwnd -ne $snapshot.hwnd -or [int]$expected.start -ne $snapshot.start -or [int]$expected.end -ne $snapshot.end -or $expected.hash -cne $hash) {
        throw 'El documento, ventana o seleccion cambio. Vuelve a leer y revisar antes de comentar.'
    }
    if ($req.action -eq 'insert') {
        $content=[string]$req.text
        $operation=[string]$req.operation
        if ($content.Trim().Length -eq 0 -or $content.Length -gt 10000 -or $operation -notmatch '^[a-f0-9]{32}$') { throw 'Texto u operacion invalida.' }
        $bookmark='Nexo'+$operation
        if ($doc.Bookmarks.Exists($bookmark)) { Result @{ok=$true; duplicate=$true; operation=$operation; saved=$false}; exit 0 }
        $content=$content.Replace("`r`n","`r").Replace("`n","`r")
        $pos=[Math]::Min([int]$range.End,([int]$doc.Content.End - 1))
        $insertion=$doc.Range($pos,$pos)
        if ($req.blocks) { $content=[string]::Join("`r",[string[]]@($req.blocks | ForEach-Object {[string]$_.text})) }
        $payload="`r"+$content+"`r"
        $wasTracking=[bool]$doc.TrackRevisions
        try {
            $doc.TrackRevisions=$true
            if (-not $doc.TrackRevisions) { throw 'No se pudo activar control de cambios.' }
            $insertion.InsertAfter($payload)
            if ([string]$insertion.Text -cne $payload) { throw 'No se pudo verificar el texto insertado. Inspecciona Word; no reintentes automaticamente.' }
            Initialize-NexoAPA $doc
            if ($req.blocks) { Format-NexoBlocks $doc ($pos+1) $req.blocks }
            else { Set-NexoRangeStyle ($doc.Range($pos+1,$pos+$payload.Length)) 'NexoAPA-Cuerpo' }
            $null=$doc.Bookmarks.Add($bookmark,$insertion)
        } finally { $doc.TrackRevisions=$wasTracking }
        Result @{ok=$true; operation=$operation; text_verified=$true; tracked=$true; saved=$false}; exit 0
    }
    if ($range.Start -eq $range.End) { throw 'Para comentar, selecciona texto. Para un cursor usa insertar.' }
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
    Result @{ok=$false; error=$_.Exception.Message; warning='Si la operacion podia cambiar Word, inspecciona su ventana: un error puede ocurrir despues de una modificacion parcial. No hay reintento automatico.'}
    exit 1
}
