$script:NexoFormat=@{page_size='Carta';font='Times New Roman';body_size=12;heading_size=12;subheading_size=12;spacing=2;line_rule=2;margin_cm=2.54;alignment='izquierda'}
function Set-NexoFormat($profile) {
    if ($null -eq $profile) { return }
    $v=$profile.effective
    if ($v.font -notin @('Times New Roman','Arial','Calibri') -or $v.alignment -notin @('izquierda','justificado') -or [double]$v.spacing -notin @(1,1.5,2)) { throw 'Perfil de formato no admitido.' }
    foreach ($key in @('body_size','heading_size','subheading_size')) {if ([double]$v.$key -lt 10 -or [double]$v.$key -gt 18) {throw 'Tamano de fuente invalido.'}}
    if ([double]$v.margin_cm -lt 1 -or [double]$v.margin_cm -gt 4) {throw 'Margenes invalidos.'}
    if ($v.page_size -and $v.page_size -notin @('Carta','A4')) {throw 'Papel no admitido.'}
    if ($v.page_size) {$script:NexoFormat.page_size=$v.page_size}
    foreach ($key in @('font','body_size','heading_size','subheading_size','spacing','margin_cm','alignment')) {$script:NexoFormat[$key]=$v.$key}
    $script:NexoFormat.line_rule=if ([double]$v.spacing -eq 1) {0} elseif ([double]$v.spacing -eq 1.5) {1} else {2}
}
# Trusted native Word layout helpers. Document/model text is DATA, never executed.
function Get-NexoLayoutState($doc, $word) {
    $raw=[string]$doc.Content.Text
    if ($raw.Length -gt 2000000 -or $doc.Content.Paragraphs.Count -gt 4000) { throw 'Documento demasiado grande para este analisis acotado (4000 parrafos / 2 millones de caracteres).' }
    $rows=New-Object System.Collections.Generic.List[object]
    foreach ($p in $doc.Content.Paragraphs) {
        $r=$p.Range; $text=([string]$r.Text).Trim(); $truncated=$text.Length -gt 240
        if ($truncated) { $text=$text.Substring(0,240) }
        $style=[string]$r.Style.NameLocal
        $rows.Add([ordered]@{start=[int]$r.Start; end=[int]$r.End; text=$text; truncated=$truncated; level=[int]$p.OutlineLevel; style=$style; table=($r.Tables.Count -gt 0); special=($r.InlineShapes.Count -gt 0 -or $r.OMaths.Count -gt 0); list=([int]$r.ListFormat.ListType -ne 0)})
    }
    $tocs=@();foreach ($t in $doc.TablesOfContents) { $tocs+=[ordered]@{start=[int]$t.Range.Start;end=[int]$t.Range.End} }
    $markers=@();foreach ($b in $doc.Bookmarks) { if ($b.Name -match '^NexoS[a-f0-9]{32}$') { $markers+=[string]$b.Name } }
    $numbered=$false; $headerText=$false
    foreach ($s in $doc.Sections) {
        foreach ($kind in @(1,2,3)) {
            foreach ($h in @($s.Headers.Item($kind),$s.Footers.Item($kind))) {
                if ($h.Exists) {
                    if ($h.PageNumbers.Count -gt 0) { $numbered=$true }
                    if (([string]$h.Range.Text).Trim().Length -gt 0) { $headerText=$true }
                }
            }
        }
    }
    $rowArray=@($rows.ToArray())
    $structure=([ordered]@{paragraphs=$rowArray;tocs=$tocs;revisions=[int]$doc.Revisions.Count} | ConvertTo-Json -Depth 6 -Compress)
    return @{path=[string]$doc.FullName;name=[string]$doc.Name;hwnd=[long]$word.ActiveWindow.Hwnd;end=[int]$doc.Content.End;hash=(Hash-Text $raw);structure_hash=(Hash-Text $structure);paragraphs=$rowArray;tocs=$tocs;markers=$markers;revisions=[int]$doc.Revisions.Count;empty=($raw.Trim().Length -eq 0);page_number_present=$numbered;header_text_present=$headerText}
}
function Set-NexoStyle($doc,[string]$name,[int]$level=10,[bool]$bold=$false,[bool]$italic=$false,[int]$alignment=0,[double]$left=0,[double]$first=36,[bool]$reset=$false) {
    $style=$null
    $created=$false
    try { $style=$doc.Styles.Item($name) } catch { $style=$doc.Styles.Add($name,1);$created=$true }
    if (-not $created -and -not $reset) { return }
    $style.AutomaticallyUpdate=$false; $style.BaseStyle=$doc.Styles.Item(-1).NameLocal
    $style.Font.Name=$script:NexoFormat.font;$style.Font.Size=[double]$script:NexoFormat.body_size;$style.Font.Bold=0;$style.Font.Italic=0;if ($bold) {$style.Font.Bold=-1};if ($italic) {$style.Font.Italic=-1}
    if ($level -le 3) {$style.Font.Size=if ($level -eq 1) {[double]$script:NexoFormat.heading_size} else {[double]$script:NexoFormat.subheading_size}}
    $pf=$style.ParagraphFormat;$pf.LineSpacingRule=[int]$script:NexoFormat.line_rule;$pf.SpaceBefore=0;$pf.SpaceAfter=0;$pf.Alignment=$alignment;$pf.LeftIndent=$left;$pf.RightIndent=0;$pf.FirstLineIndent=$first;$pf.OutlineLevel=$level;$pf.WidowControl=$true;$pf.KeepWithNext=($level -le 3)
}
function Initialize-NexoAPA($doc,[bool]$reset=$false) {
    Set-NexoStyle $doc 'NexoAPA-Cuerpo' -reset $reset
    Set-NexoStyle $doc 'NexoAPA-Nivel1' 1 $true $false 1 0 0 -reset $reset
    Set-NexoStyle $doc 'NexoAPA-Nivel2' 2 $true $false 0 0 0 -reset $reset
    Set-NexoStyle $doc 'NexoAPA-Nivel3' 3 $true $true 0 0 0 -reset $reset
    Set-NexoStyle $doc 'NexoAPA-Referencias' 10 $false $false 0 36 -36 -reset $reset
    Set-NexoStyle $doc 'NexoAPA-Cita' 10 $false $false 0 36 0 -reset $reset
    Set-NexoStyle $doc 'NexoAPA-Lista' 10 $false $false 0 36 -18 -reset $reset
    Set-NexoStyle $doc 'NexoAPA-Indice' 10 $true $false 1 0 0 -reset $reset
}
function Set-NexoRangeStyle($range,[string]$style) {
    $range.Style=$style;$range.Font.Name=$script:NexoFormat.font;$range.Font.Size=[double]$script:NexoFormat.body_size
    $pf=$range.ParagraphFormat;$pf.LineSpacingRule=[int]$script:NexoFormat.line_rule;$pf.SpaceBefore=0;$pf.SpaceAfter=0;$pf.Alignment=0;$pf.LeftIndent=0;$pf.RightIndent=0;$pf.FirstLineIndent=36;$pf.OutlineLevel=10;$pf.WidowControl=$true;$pf.KeepWithNext=$false
    if ($style -eq 'NexoAPA-Cuerpo' -and $script:NexoFormat.alignment -eq 'justificado') {$pf.Alignment=3}
    if ($style -match '^NexoAPA-Nivel([123])$') {
        $level=[int]$Matches[1];$pf.OutlineLevel=$level;$pf.FirstLineIndent=0;$pf.KeepWithNext=$true
        if ($level -eq 1) {$pf.Alignment=1}
        $range.Font.Size=if ($level -eq 1) {[double]$script:NexoFormat.heading_size} else {[double]$script:NexoFormat.subheading_size}
        $range.Font.Bold=$true;$range.Font.Italic=($level -eq 3)
    } elseif ($style -eq 'NexoAPA-Referencias') { $pf.LeftIndent=36;$pf.FirstLineIndent=-36 }
    elseif ($style -eq 'NexoAPA-Cita') { $pf.LeftIndent=36;$pf.FirstLineIndent=0 }
    elseif ($style -eq 'NexoAPA-Lista') { $pf.LeftIndent=36;$pf.FirstLineIndent=-18 }
    elseif ($style -eq 'NexoAPA-Indice') { $pf.Alignment=1;$pf.FirstLineIndent=0;$pf.KeepWithNext=$true;$range.Font.Bold=$true }
}
function Format-NexoBlocks($doc,[int]$pos,$blocks) {
    $offset=0
    foreach ($b in $blocks) {
        $length=([string]$b.text).Length;$part=$doc.Range($pos+$offset,$pos+$offset+$length+1)
        $part.Font.Bold=$false;$part.Font.Italic=$false;$part.Font.Underline=0;$part.Font.Color=0;$part.ListFormat.RemoveNumbers()
        $style=switch ([string]$b.kind) { 'heading' { 'NexoAPA-Nivel'+[string]$b.level } 'reference' {'NexoAPA-Referencias'} 'quote' {'NexoAPA-Cita'} 'list' {'NexoAPA-Lista'} default {'NexoAPA-Cuerpo'} }
        Set-NexoRangeStyle $part $style
        foreach ($run in $b.runs) {
            $em=$doc.Range($pos+$offset+[int]$run.start,$pos+$offset+[int]$run.start+[int]$run.length)
            if ($run.bold) { $em.Font.Bold=$true };if ($run.italic) { $em.Font.Italic=$true }
        }
        $offset+=$length+1
    }
}
function Format-NexoDocument($doc,$state,$plan) {
    foreach ($s in $doc.Sections) {
        $page=$s.PageSetup;$margin=[double]$script:NexoFormat.margin_cm*72/2.54;$page.TopMargin=$margin;$page.BottomMargin=$margin;$page.LeftMargin=$margin;$page.RightMargin=$margin;$page.Gutter=0;$page.PaperSize=if ($script:NexoFormat.page_size -eq 'A4') {7} else {2};$page.HeaderDistance=36
    }
    $headingMap=@{};foreach ($h in $plan.headings) { $headingMap[[string]$h.start]=$h }
    $sectionKey='';$sectionLevel=1;$abstract=$false
    foreach ($p in $state.paragraphs) {
        $insideToc=$false;foreach ($t in $state.tocs) { if ($p.start -lt $t.end -and $p.end -gt $t.start) { $insideToc=$true;break } }
        if ($insideToc -or $p.table -or $p.special) { continue }
        $r=$doc.Range([int]$p.start,[int]$p.end)
        $r.Font.Name=$script:NexoFormat.font;$r.Font.Size=[double]$script:NexoFormat.body_size
        $h=$headingMap[[string]$p.start]
        if ($null -ne $h) {
            $abstract=([string]$h.label_kind -eq 'abstract')
            if ($h.key) { $sectionKey=[string]$h.key;$sectionLevel=[int]$h.level }
            elseif ([int]$h.level -le $sectionLevel) { $sectionKey='' }
            if ([int]$h.level -le 3) { Set-NexoRangeStyle $r ('NexoAPA-Nivel'+[string]$h.level) }
            continue
        }
        if ($abstract) { Set-NexoRangeStyle $r 'NexoAPA-Cuerpo';$r.ParagraphFormat.FirstLineIndent=0;continue }
        if ([string]$p.style -match '^(Caption|Epigrafe|Epígrafe)$') { $r.ParagraphFormat.FirstLineIndent=0;$r.ParagraphFormat.Alignment=0;continue }
        if ([int]$p.start -lt [int]$plan.body_start) { $r.ParagraphFormat.LineSpacingRule=[int]$script:NexoFormat.line_rule;continue }
        if ($p.list) { $r.ParagraphFormat.LineSpacingRule=[int]$script:NexoFormat.line_rule;$r.ParagraphFormat.SpaceBefore=0;$r.ParagraphFormat.SpaceAfter=0;continue }
        if ($sectionKey -eq 'referencias') { Set-NexoRangeStyle $r 'NexoAPA-Referencias' }
        elseif ([string]$p.style -match '^(Quote|Intense Quote|Cita|Cita destacada|Texto de cita|NexoAPA-Cita)$') { Set-NexoRangeStyle $r 'NexoAPA-Cita' }
        else { Set-NexoRangeStyle $r 'NexoAPA-Cuerpo' }
    }
    if (-not $state.page_number_present -and -not $state.header_text_present) {
        $sectionNumber=0
        foreach ($s in $doc.Sections) {
            $sectionNumber++;$kinds=@(1)
            if ($s.PageSetup.DifferentFirstPageHeaderFooter) { $kinds+=2 }
            if ($s.PageSetup.OddAndEvenPagesHeaderFooter) { $kinds+=3 }
            foreach ($kind in $kinds) {
                $h=$s.Headers.Item($kind)
                if ($h.PageNumbers.Count -eq 0) { $null=$h.PageNumbers.Add(2,$true) }
                if ($sectionNumber -eq 1) { $h.PageNumbers.RestartNumberingAtSection=$true;$h.PageNumbers.StartingNumber=1 } else { $h.PageNumbers.RestartNumberingAtSection=$false }
                $h.Range.Font.Name=$script:NexoFormat.font;$h.Range.Font.Size=[double]$script:NexoFormat.body_size;$h.Range.ParagraphFormat.Alignment=2
            }
        }
    }
}
# UseOutlineLevels is an Add parameter, NOT a TableOfContents property.
# Register custom APA styles through the documented HeadingStyles collection.
function Set-NexoTOCStyles($toc) {
    foreach ($level in @(1,2,3)) {
        $name='NexoAPA-Nivel'+[string]$level;$found=$false
        foreach ($entry in $toc.HeadingStyles) {
            $entryStyle=$entry.Style
            $entryName=if ($entryStyle -is [string]) { $entryStyle } else { [string]$entryStyle.NameLocal }
            if ($entryName -eq $name) { $entry.Level=$level;$found=$true;break }
        }
        if (-not $found) { $null=$toc.HeadingStyles.Add($name,$level) }
    }
}
function Update-NexoTOC($doc) {
            foreach ($id in @(-20,-21,-22)) {
                $style=$doc.Styles.Item($id);$style.Font.Name=$script:NexoFormat.font;$style.Font.Size=[double]$script:NexoFormat.body_size
                $style.ParagraphFormat.LineSpacingRule=[int]$script:NexoFormat.line_rule;$style.ParagraphFormat.SpaceBefore=0;$style.ParagraphFormat.SpaceAfter=0
            }
            $toc=$doc.TablesOfContents.Item(1);$toc.UseHeadingStyles=$true;$toc.UpperHeadingLevel=1;$toc.LowerHeadingLevel=3;$toc.IncludePageNumbers=$true;$toc.RightAlignPageNumbers=$true;$toc.UseHyperlinks=$true
            Set-NexoTOCStyles $toc
            $doc.Repaginate();$toc.Update()
}
function Invoke-NexoLayout($req,$doc,$word) {
    if ($req.action -eq 'layout') {Set-NexoFormat $req.plan.format_profile}
    $state=Get-NexoLayoutState $doc $word
    if ($req.action -eq 'inspect') { Result @{ok=$true;structure=$state};return }
    if ($req.approved -isnot [bool] -or $req.approved -ne $true -or [string]$req.operation -notmatch '^[a-f0-9]{32}$') { throw 'Falta aprobacion explicita del plan de documento.' }
    if ($doc.ReadOnly -or $doc.ProtectionType -ne -1) { throw 'Documento protegido o de solo lectura; no se modifico.' }
    $plan=$req.plan;$expected=$plan.snapshot
    if ($null -eq $plan -or $plan.schema -ne 1 -or $expected.path -cne $state.path -or [long]$expected.hwnd -ne $state.hwnd -or $expected.hash -cne $state.hash -or $expected.structure_hash -cne $state.structure_hash -or [int]$expected.end -ne $state.end) { throw 'El documento o su estructura cambio desde la vista previa. Vuelve a analizar; no se aplico el plan.' }
    if ($plan.format_all -isnot [bool] -or $plan.operations.Count -gt 24 -or [int]$plan.body_start -lt 0 -or [int]$plan.body_start -ge $state.end -or $plan.toc.mode -notin @('none','create','update')) { throw 'Plan de documento invalido.' }
    $total=0;$locations=@{};$seenMarkers=@{}
    foreach ($p in $state.paragraphs) { $locations[[string]$p.start]=$true }
    $locations[[string]([int]$state.end - 1)]=$true
    foreach ($op in $plan.operations) {
        if (-not $locations.ContainsKey([string]$op.position) -or [string]$op.marker -notmatch '^NexoS[a-f0-9]{32}$' -or $seenMarkers.ContainsKey([string]$op.marker) -or $doc.Bookmarks.Exists([string]$op.marker) -or $op.blocks.Count -lt 1) { throw 'Ubicacion de insercion invalida o insercion ya registrada.' }
        $seenMarkers[[string]$op.marker]=$true
        foreach ($b in $op.blocks) {
            if ($b.kind -notin @('body','heading','reference','quote','list') -or [string]::IsNullOrWhiteSpace([string]$b.text) -or [string]$b.text -match '[\x00-\x08\x0a-\x1f]') { throw 'Bloque de texto invalido.' }
            if ($b.kind -eq 'heading' -and [int]$b.level -notin @(1,2,3)) { throw 'Nivel de encabezado no admitido.' }
            foreach ($run in $b.runs) { if ([int]$run.start -lt 0 -or [int]$run.length -lt 1 -or ([int]$run.start+[int]$run.length) -gt ([string]$b.text).Length) { throw 'Formato de texto fuera del bloque.' } }
            $total+=([string]$b.text).Length
        }
    }
    if ($total -gt 60000) { throw 'Lote demasiado grande.' }
    if ($plan.toc.mode -ne 'none' -and -not $locations.ContainsKey([string]$plan.toc.position) -and $plan.toc.mode -ne 'update') { throw 'Posicion de indice invalida.' }
    if ($plan.toc.mode -eq 'create' -and $doc.TablesOfContents.Count -ne 0) { throw 'Ya existe un indice: vuelve a preparar el plan.' }
    if ($plan.toc.mode -eq 'update' -and $doc.TablesOfContents.Count -ne 1) { throw 'No hay un unico indice para actualizar.' }
    $wasTracking=[bool]$doc.TrackRevisions;$wasFormatting=[bool]$doc.TrackFormatting;$undo=$false;$inserted=@();$tocPos=[int]$plan.toc.position
    try {
        try { $word.UndoRecord.StartCustomRecord('Nexo Tesis - estructura y APA');$undo=$true } catch { $undo=$false }
        $doc.TrackRevisions=$true;$doc.TrackFormatting=$true
        if (-not $doc.TrackRevisions) { throw 'No se pudo activar control de cambios.' }
        Initialize-NexoAPA $doc -reset ([bool]$plan.format_all)
        if ($plan.format_all) { Format-NexoDocument $doc $state $plan }
        else {
            foreach ($h in $plan.promotions) { $r=$doc.Range([int]$h.start,[int]$h.end);Set-NexoRangeStyle $r ('NexoAPA-Nivel'+[string]$h.level) }
        }
        $ordered=@($plan.operations | Sort-Object -Property @{Expression={[int]$_.position};Descending=$true},@{Expression={[int]$_.order};Descending=$true})
        $endUsed=$false
        $endHadText=-not @($state.paragraphs | Where-Object { [int]$_.start -eq ([int]$state.end - 1) }).Count
        foreach ($op in $ordered) {
            $pos=[int]$op.position;$before=[int]$doc.Content.End;$prefix='';$suffix="`r"
            if ($pos -eq ([int]$state.end - 1)) {
                if ($endUsed) { if ($endHadText) { $pos++ } }
                else { if ($endHadText) { $prefix="`r" };$suffix='';$endUsed=$true }
            }
            $payload=$prefix+([string]::Join("`r",[string[]]@($op.blocks | ForEach-Object {[string]$_.text})))+$suffix
            $r=$doc.Range($pos,$pos);$r.Text=$payload
            $blockRange=$doc.Range($pos,$pos+$payload.Length)
            if ([string]$blockRange.Text -cne $payload) { throw 'No se confirmo el texto insertado. Inspecciona Word antes de repetir.' }
            Format-NexoBlocks $doc ($pos+$prefix.Length) $op.blocks
            $null=$doc.Bookmarks.Add([string]$op.marker,($doc.Range($pos+$prefix.Length,$pos+$payload.Length)));$inserted+=[string]$op.section
            if ($pos -lt [int]$plan.toc.position) { $tocPos+=([int]$doc.Content.End - $before) }
        }
        if ($plan.toc.mode -eq 'create') {
            $title="Índice`r";$r=$doc.Range($tocPos,$tocPos);$r.Text=$title
            Set-NexoRangeStyle ($doc.Range($tocPos,$tocPos+$title.Length)) 'NexoAPA-Indice'
            $at=$doc.Range($tocPos+$title.Length,$tocPos+$title.Length)
            $m=[Type]::Missing
            $toc=$doc.TablesOfContents.Add($at,$true,1,3,$false,$m,$true,$true,$m,$true,$true,$true)
            $toc.TabLeader=1
            $after=$doc.Range([int]$toc.Range.End,[int]$toc.Range.End);$after.InsertBreak(7)
        }
        if ($plan.toc.mode -ne 'none') { Update-NexoTOC $doc }
        $outcome=@{ok=$true;operation=[string]$req.operation;inserted=$inserted;formatted=[bool]$plan.format_all;toc=[string]$plan.toc.mode;text_verified=$true;tracked=$true;undo_group=$undo;saved=$false;warnings=@($plan.warnings)}
    } finally {
        $doc.TrackRevisions=$wasTracking;$doc.TrackFormatting=$wasFormatting
        if ($undo) { $word.UndoRecord.EndCustomRecord() }
    }
    Result $outcome
}
