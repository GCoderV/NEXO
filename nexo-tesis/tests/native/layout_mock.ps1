# REAL PowerShell execution against a deliberately small text/range DOUBLE, NOT Word COM.
param([string]$Helper)
$ErrorActionPreference='Stop'
. $Helper
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
public class NFont {public string Name;public object Size,Bold,Italic,Underline,Color;}
public class NPF {public object LineSpacingRule,SpaceBefore,SpaceAfter,Alignment,LeftIndent,RightIndent,FirstLineIndent,OutlineLevel,WidowControl,KeepWithNext;}
public class NList {public void RemoveNumbers(){}}
public class NRange {
 public NDoc Doc; public int Start,End; public string Style; public NFont Font=new NFont(); public NPF ParagraphFormat=new NPF(); public NList ListFormat=new NList();
 public NRange(NDoc d,int s,int e){Doc=d;Start=s;End=e;}
 public string Text {get{return Doc.Raw.Substring(Start,End-Start);}set{Doc.Raw=Doc.Raw.Substring(0,Start)+value+Doc.Raw.Substring(End);End=Start+value.Length;}}
}
public class NBookmarks {public Dictionary<string,NRange> Items=new Dictionary<string,NRange>();public bool Exists(string name){return Items.ContainsKey(name);}public void Add(string name,NRange r){Items.Add(name,r);}}
public class NDoc {
 public string Raw; public bool ReadOnly=false,TrackRevisions=false,TrackFormatting=false;public int ProtectionType=-1;
 public NBookmarks Bookmarks=new NBookmarks();public List<NRange> Ranges=new List<NRange>();
 public NDoc(string raw){Raw=raw;} public NRange Content{get{return new NRange(this,0,Raw.Length);}}
 public NRange Range(int a,int b){if(a<0||b<a||b>Raw.Length)throw new Exception("range outside text "+a+":"+b+" / "+Raw.Length);var r=new NRange(this,a,b);Ranges.Add(r);return r;}
}
public class NUndo {public void StartCustomRecord(string name){}public void EndCustomRecord(){}}
public class NWord {public NUndo UndoRecord=new NUndo();}
'@
# Native snapshot/style catalog calls are excluded from this text-placement double.
function Get-NexoLayoutState($doc,$word) { return $script:inputData.state }
function Initialize-NexoAPA($doc,[bool]$reset=$false) {}
function Result($value) { $script:result=$value }
$script:inputData=[Console]::In.ReadToEnd() | ConvertFrom-Json
$doc=[NDoc]::new([string]$inputData.text);$word=[NWord]::new()
try {
    Invoke-NexoLayout $inputData.request $doc $word
    $formatted=@($doc.Ranges | Where-Object {$_.Style} | ForEach-Object {@{start=$_.Start;end=$_.End;style=$_.Style;text=$_.Text;first=$_.ParagraphFormat.FirstLineIndent;outline=$_.ParagraphFormat.OutlineLevel;font=$_.Font.Name;size=$_.Font.Size;spacing=$_.ParagraphFormat.LineSpacingRule}})
    @{result=$script:result;text=$doc.Raw;markers=@($doc.Bookmarks.Items.Keys);tracking=$doc.TrackRevisions;formatting=$doc.TrackFormatting;ranges=$formatted} | ConvertTo-Json -Depth 12 -Compress
} catch { @{error=$_.Exception.Message;text=$doc.Raw;tracking=$doc.TrackRevisions;formatting=$doc.TrackFormatting} | ConvertTo-Json -Compress }
