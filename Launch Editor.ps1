$ErrorActionPreference = 'Stop'
$editorPython = (Get-Command python -ErrorAction Stop).Source
$editorPythonWindowless = Join-Path (Split-Path $editorPython) 'pythonw.exe'
if (Test-Path -LiteralPath $editorPythonWindowless) {
    $editorPython = $editorPythonWindowless
}
Start-Process -FilePath $editorPython -ArgumentList ('"' + (Join-Path $PSScriptRoot 'run_editor.py') + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
