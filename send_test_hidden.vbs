' Jalankan send_test.bat TANPA jendela CMD nongol (buat task one-shot).
' Path dihitung dari lokasi file ini sendiri -> aman dipindah ke PC lain.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run """" & dir & "\send_test.bat""", 0, False
