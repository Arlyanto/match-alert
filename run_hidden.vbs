' Jalankan run.bat TANPA jendela CMD nongol.
' Path dihitung dari lokasi file ini sendiri -> aman dipindah ke PC lain.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run """" & dir & "\run.bat""", 0, False
