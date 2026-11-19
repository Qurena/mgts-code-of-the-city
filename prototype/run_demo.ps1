# Запуск показа одной командой: приёмник ответов и интерфейс.
# Если базы ещё нет, данные сначала загружаются из файла сопоставления.
# Использование:  .\run_demo.ps1                       (готовый набор в формате вебинара, папка mgts)
#                 .\run_demo.ps1 -Survey survey.json -Db pulse.db -Mapping mapping.json -Analyzer llm
param(
    [string]$Survey = "mgts/survey.json",
    [string]$Db = "mgts/pulse.db",
    [string]$Mapping = "mgts/mapping.json",
    [string]$Analyzer = "keywords",
    [int]$Port = 8501
)
Set-Location $PSScriptRoot
$env:SURVEY_CONFIG = (Resolve-Path $Survey).Path
$env:PULSE_DB = Join-Path $PSScriptRoot $Db
$env:MAPPING_FILE = Join-Path $PSScriptRoot $Mapping
$env:ANALYZER = $Analyzer
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
if (-not (Test-Path $env:PULSE_DB) -and (Test-Path $env:MAPPING_FILE)) {
    Write-Host "Базы ещё нет: загружаю данные из $Mapping"
    & $py import_data.py $env:MAPPING_FILE
}
Start-Process -FilePath $py -ArgumentList "receiver.py" -WindowStyle Hidden
Write-Host "Приёмник: http://127.0.0.1:8765  (POST /response, POST /form/<имя>)"
Write-Host "Интерфейс: http://localhost:$Port  (Ctrl+C останавливает интерфейс; приёмник закройте через диспетчер задач или Stop-Process)"
& $py -m streamlit run app.py --server.port $Port
