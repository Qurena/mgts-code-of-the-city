# Подготовка чистого ноутбука: окружение Python и зависимости.
# Если рядом есть папка wheels (скачана заранее), установка идёт без интернета.
Set-Location $PSScriptRoot
py -m venv .venv
$pip = ".\.venv\Scripts\python.exe"
if (Test-Path ".\wheels") {
    & $pip -m pip install --no-index --find-links .\wheels -r requirements.txt
} else {
    & $pip -m pip install -r requirements.txt
}
& $pip -W ignore -m unittest 2>&1 | Select-Object -Last 4
Write-Host "Готово. Демо: .\run_demo.ps1"
