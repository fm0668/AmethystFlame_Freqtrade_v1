$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m pip install -r .\live_service\requirements_live_service.txt
python -m live_service.app --config .\live_service\config.live.example.yaml

