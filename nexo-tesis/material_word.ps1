# Read a library COPY in Word, with macros/links disabled. Never saves the document.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$word=$null;$doc=$null;$owned=$false;$opened=$false;$oldActive=$null;$security=$null;$links=$null
try {
 $req=[Console]::In.ReadToEnd() | ConvertFrom-Json
 if ($req.approved -isnot [bool] -or -not $req.approved -or -not [IO.File]::Exists([string]$req.path) -or [IO.Path]::GetExtension([string]$req.path) -ine '.docx') {throw 'Lectura DOCX no autorizada o ruta inválida.'}
 try {$word=[Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application');$oldActive=$word.ActiveDocument} catch {$word=New-Object -ComObject Word.Application;$owned=$true}
 $security=$word.AutomationSecurity;$links=$word.Options.UpdateLinksAtOpen
 $word.AutomationSecurity=3;$word.Options.UpdateLinksAtOpen=$false
 foreach ($d in $word.Documents) {if ($d.FullName -eq [string]$req.path) {throw 'La copia de biblioteca está abierta. Ciérrala antes de analizarla.'}}
 $m=[Type]::Missing
 $doc=$word.Documents.Open([string]$req.path,$false,$true,$false,$m,$m,$m,$m,$m,$m,$m,$false);$opened=$true
 if ($doc.ProtectionType -ne -1) {throw 'Documento protegido. No se eludió su protección.'}
 $segments=@();$count=0;$chars=0;$total=[int]$doc.Content.Paragraphs.Count
 foreach($para in $doc.Content.Paragraphs) {
  if ($chars -ge 100000 -or $count -ge 4000) {break};$count++
  $text=([string]$para.Range.Text).Trim();$chars+=$text.Length
  $segments+=@{locator=('párrafo '+$count);text=$text}
 }
 $result=@{segments=$segments;total=$total;omitted=($total-$count);warnings=@('Cuerpo principal mediante Word. No incluye encabezados, notas ni texto de imágenes. Se conserva el original.')}
} catch {$result=@{error=$_.Exception.Message}}
finally {
 $cleanup=@()
 if ($opened) {try {$doc.Close(0)} catch {$cleanup+='No se pudo cerrar la copia de lectura: revisa Word.'}}
 if ($null -ne $security) {
  try {$word.AutomationSecurity=$security} catch {$cleanup+='No se pudo restaurar AutomationSecurity; revisa Word.'}
  try {$word.Options.UpdateLinksAtOpen=$links} catch {$cleanup+='No se pudo restaurar la opción de vínculos; revisa Word.'}
 }
 if ($owned) {try {$word.Quit(0)} catch {$cleanup+='La instancia de lectura puede seguir abierta.'}} elseif ($null -ne $oldActive) {try {$oldActive.Activate()} catch {}}
 if ($cleanup.Count) {if (-not $result.ContainsKey('warnings')) {$result.warnings=@()};$result.warnings=@($result.warnings)+$cleanup}
}
[Console]::WriteLine(($result | ConvertTo-Json -Depth 6 -Compress))
