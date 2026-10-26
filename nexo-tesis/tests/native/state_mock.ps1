# Snapshot serialization DOUBLE. This is not Word COM.
param([string]$Root)
$ErrorActionPreference='Stop'
. (Join-Path $Root 'word_layout.ps1')
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $Root 'word_bridge.ps1'),[ref]$tokens,[ref]$errors)
$hash=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Hash-Text'},$true)
. ([ScriptBlock]::Create($hash.Extent.Text))
$raw="Introducción`rTexto de prueba.`r";$rows=@();$position=0
foreach ($text in @('Introducción','Texto de prueba.')) {
    $r=[PSCustomObject]@{Start=$position;End=$position+$text.Length+1;Text=$text+"`r";Style=[PSCustomObject]@{NameLocal='Normal'};Tables=@();InlineShapes=@();OMaths=@();ListFormat=[PSCustomObject]@{ListType=0}}
    $rows+=[PSCustomObject]@{Range=$r;OutlineLevel=10};$position+=$text.Length+1
}
$doc=[PSCustomObject]@{FullName='C:\Copies\test.docx';Name='test.docx';Content=[PSCustomObject]@{Text=$raw;End=$raw.Length;Paragraphs=$rows};TablesOfContents=@();Bookmarks=@();Sections=@();Revisions=@()}
$word=[PSCustomObject]@{ActiveWindow=[PSCustomObject]@{Hwnd=5}}
Get-NexoLayoutState $doc $word | ConvertTo-Json -Depth 10 -Compress
