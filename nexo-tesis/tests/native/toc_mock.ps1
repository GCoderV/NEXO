# Documented-property contract double, not Microsoft Word COM.
param([string]$Helper)
$ErrorActionPreference='Stop'
. $Helper
Add-Type -TypeDefinition @'
using System;
using System.Collections;
using System.Collections.Generic;
public class StyleName {public string NameLocal; public StyleName(string s){NameLocal=s;}}
public class HeadingEntry {public object Style; public int Level;public HeadingEntry(object s,int l){Style=s;Level=l;}}
public class HeadingCollection : IEnumerable {
 public List<HeadingEntry> Items=new List<HeadingEntry>();
 public HeadingEntry Add(object s,int level){var e=new HeadingEntry(s,level);Items.Add(e);return e;}
 public IEnumerator GetEnumerator(){return Items.GetEnumerator();}
}
public class TOCContract {
 // No UseOutlineLevels property: an assignment MUST fail rather than be silently accepted.
 public bool UseHeadingStyles,IncludePageNumbers,RightAlignPageNumbers,UseHyperlinks;
 public int UpperHeadingLevel,LowerHeadingLevel,TabLeader,Updates;
 public HeadingCollection HeadingStyles=new HeadingCollection();
 public void Update(){Updates++;}
}
public class TOCs {public TOCContract Toc=new TOCContract();public TOCContract Item(int i){if(i!=1)throw new Exception();return Toc;}}
public class F {public string Name;public int Size;}
public class P {public int LineSpacingRule,SpaceBefore,SpaceAfter;}
public class S {public F Font=new F();public P ParagraphFormat=new P();}
public class Styles {public Dictionary<int,S> Values=new Dictionary<int,S>();public S Item(int id){if(!Values.ContainsKey(id))Values.Add(id,new S());return Values[id];}}
public class DocContract {public TOCs TablesOfContents=new TOCs();public Styles Styles=new Styles();public int Repaginations;public void Repaginate(){Repaginations++;}}
'@
$d=[DocContract]::new();$toc=$d.TablesOfContents.Toc
$null=$toc.HeadingStyles.Add('Personalizado',2)
$null=$toc.HeadingStyles.Add([StyleName]::new('NexoAPA-Nivel1'),3)
Update-NexoTOC $d
Update-NexoTOC $d
if ($toc.HeadingStyles.Items.Count -ne 4) { throw 'Duplicates or lost custom entries' }
if ($toc.HeadingStyles.Items[1].Level -ne 1) { throw 'Level not normalized' }
if ($toc.Updates -ne 2 -or $d.Repaginations -ne 2) { throw 'TOC not updated' }
if ($toc.UpperHeadingLevel -ne 1 -or $toc.LowerHeadingLevel -ne 3 -or -not $toc.IncludePageNumbers) { throw 'TOC options invalid' }
$rejected=$false
try { $toc.UseOutlineLevels=$true } catch { $rejected=$true }
if (-not $rejected) { throw 'Double did not enforce missing-property error' }
@{passed=5;real_word_com=$false;existing_custom_entries_preserved=$true;no_duplicate_styles=$true;repagination_and_update=$true;old_assignment_rejected=$rejected;supported_contract=$true} | ConvertTo-Json -Compress
