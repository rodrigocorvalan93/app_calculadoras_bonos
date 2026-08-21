<#
Actualiza la app a la última versión de main y reinicia el servicio.

Uso (PowerShell, no requiere admin si el servicio corre con permisos de la cuenta):
  C:\apps\yieldvertex\deploy\deploy.ps1
  C:\apps\yieldvertex\deploy\deploy.ps1 -Branch main -Port 8000

Qué hace:
  1. git fetch + chequeo de working tree limpio (aborta si hay cambios locales).
  2. git merge --ff-only (nunca merges implícitos en el server).
  3. pip install -r backend\requirements.txt (por si cambiaron dependencias).
  4. Renueva cert/CRL del add-in si hace falta (idempotente, no toca nada vigente).
  5. Reinicia el servicio y espera /healthz hasta 45 s.
  6. Si /healthz no responde: muestra el log y deja impreso el comando de ROLLBACK.
#>
param(
  [string]$ServiceName = "YieldVertex",
  [int]$Port = 8000,
  [string]$Branch = "main"
)
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$py = Join-Path $repo ".venv\Scripts\python.exe"

git fetch origin $Branch
$local = (git rev-parse HEAD).Trim()
$remote = (git rev-parse "origin/$Branch").Trim()
if ($local -eq $remote) {
  Write-Host "Ya estas en la ultima version ($($local.Substring(0,7))). Nada que deployar."
  exit 0
}
$dirty = git status --porcelain
if ($dirty) {
  throw "Working tree con cambios locales - resolver antes de deployar:`n$dirty"
}

Write-Host "Deploy: $($local.Substring(0,7)) -> $($remote.Substring(0,7))"
git merge --ff-only "origin/$Branch"
& $py -m pip install -q -r backend\requirements.txt
& $py -m backend.tools.https_local --quiet

& nssm restart $ServiceName

$deadline = (Get-Date).AddSeconds(45)
$r = $null
do {
  Start-Sleep -Seconds 2
  try { $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 3 } catch { $r = $null }
} while (-not $r -and (Get-Date) -lt $deadline)

if ($r -and $r.status -eq "ok") {
  Write-Host "Deploy OK -> $(git rev-parse --short HEAD) - bonds=$($r.bonds_loaded) feed_alive=$($r.feed_alive)"
} else {
  Write-Warning "La app no respondio /healthz tras el deploy. Ultimas lineas del log:"
  Get-Content (Join-Path $repo "logs\service.log") -Tail 30 -ErrorAction SilentlyContinue
  Write-Warning "ROLLBACK:  git reset --hard $($local.Substring(0,7)) ; nssm restart $ServiceName"
  exit 1
}
