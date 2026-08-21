<#
Instala la app como SERVICIO de Windows con auto-restart, vía NSSM.

Uso (PowerShell COMO ADMINISTRADOR, desde cualquier carpeta):
  C:\apps\yieldvertex\deploy\install_service_windows.ps1                    # 127.0.0.1:8000
  C:\apps\yieldvertex\deploy\install_service_windows.ps1 -BindHost 0.0.0.0  # escuchar en la red

Prerrequisitos (ver DEPLOY.md):
  - Repo clonado FUERA de OneDrive (ej. C:\apps\yieldvertex) con el venv creado:
      python -m venv .venv
      .venv\Scripts\pip install -r backend\requirements.txt
  - NSSM en el PATH (https://nssm.cc  o  choco install nssm).
  - secrets.txt / .env en la raíz del repo (credenciales; la app los lee sola).

Qué configura:
  - Servicio auto-start al boot, con AUTO-RESTART si el proceso muere (3 s de espera).
  - Parada prolija: manda Ctrl+C y espera hasta 15 s (guarda snapshot, cierra el
    puente TLS) antes de matar el proceso.
  - Logs en <repo>\logs\service.log con rotación a 10 MB.
  - UN SOLO proceso (la app es stateful en memoria — nunca --workers ni 2 instancias).
#>
param(
  [string]$ServiceName = "YieldVertex",
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8000,
  [string]$PythonExe = ""              # default: .venv\Scripts\python.exe del repo
)
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $PythonExe) { $PythonExe = Join-Path $repo ".venv\Scripts\python.exe" }
if (-not (Test-Path $PythonExe)) {
  throw "No existe $PythonExe - crear el venv primero: python -m venv .venv ; .venv\Scripts\pip install -r backend\requirements.txt"
}
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
  throw "NSSM no esta en el PATH. Instalar desde https://nssm.cc o 'choco install nssm'."
}
if ($repo -match "OneDrive") {
  Write-Warning "El repo esta dentro de OneDrive: NO recomendado para un server (locks y sync rompen escrituras). Mover a C:\apps\yieldvertex."
}

$logs = Join-Path $repo "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$appArgs = "-m uvicorn backend.main:app --host $BindHost --port $Port --timeout-graceful-shutdown 10"

& nssm install $ServiceName $PythonExe $appArgs
& nssm set $ServiceName AppDirectory $repo
& nssm set $ServiceName DisplayName "YieldVertex (calculadora de bonos)"
& nssm set $ServiceName Description "FastAPI + feed BYMA. UN solo proceso (estado en memoria): no escalar en workers ni duplicar instancias."
& nssm set $ServiceName Start SERVICE_AUTO_START
& nssm set $ServiceName AppExit Default Restart          # auto-restart si el proceso muere
& nssm set $ServiceName AppRestartDelay 3000             # 3 s entre reintentos
& nssm set $ServiceName AppThrottle 5000                 # <5 s vivo = arranque fallido (evita loop caliente)
& nssm set $ServiceName AppStopMethodConsole 15000       # Ctrl+C prolijo hasta 15 s antes de matar
& nssm set $ServiceName AppStdout (Join-Path $logs "service.log")
& nssm set $ServiceName AppStderr (Join-Path $logs "service.log")
& nssm set $ServiceName AppRotateFiles 1
& nssm set $ServiceName AppRotateOnline 1
& nssm set $ServiceName AppRotateBytes 10485760          # rota a 10 MB
# APP_HOST consistente con el bind (el guard de arranque lo mira si AUTH_ENABLED=0):
& nssm set $ServiceName AppEnvironmentExtra "APP_HOST=$BindHost"

& nssm start $ServiceName
Start-Sleep -Seconds 6
try {
  $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 5
  Write-Host "OK - /healthz: status=$($r.status) bonds=$($r.bonds_loaded) feed_alive=$($r.feed_alive)"
  Write-Host "Servicio '$ServiceName' instalado. Logs: $logs\service.log"
} catch {
  Write-Warning "El servicio arranco pero /healthz aun no responde (el primer boot tarda ~10-20 s por la carga de especies)."
  Write-Warning "Verificar en unos segundos: http://127.0.0.1:$Port/healthz - y el log en $logs\service.log"
}
