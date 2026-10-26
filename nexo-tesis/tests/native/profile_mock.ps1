param([string]$Helper)
$ErrorActionPreference='Stop'
. $Helper
$pg=[pscustomobject]@{PaperSize=2;TopMargin=0;BottomMargin=0;LeftMargin=0;RightMargin=0;Gutter=0;HeaderDistance=0}
$doc=[pscustomobject]@{Sections=@([pscustomobject]@{PageSetup=$pg;Headers=@();Footers=@()})}
$word=New-Object PSObject
$word | Add-Member ScriptMethod CentimetersToPoints {param($n) $n*28.3464567}
Set-NexoFormat ([pscustomobject]@{effective=[pscustomobject]@{page_size='A4';font='Arial';body_size=11;heading_size=14;subheading_size=13;spacing=1.5;margin_cm=3;alignment='izquierda'}})
Format-NexoDocument $doc ([pscustomobject]@{paragraphs=@();tocs=@();page_number_present=$true}) ([pscustomobject]@{headings=@();body_start=0})
$pg | ConvertTo-Json -Compress
