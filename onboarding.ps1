param([switch]$Start)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Failures = 0

function Check($Label, $Ok, $Detail) {
    if ($Ok) { Write-Host "[OK]   $Label - $Detail" -ForegroundColor Green }
    else { Write-Host "[FAIL] $Label - $Detail" -ForegroundColor Red; $script:Failures++ }
}
function Warn($Label, $Detail) { Write-Host "[WARN] $Label - $Detail" -ForegroundColor Yellow }

Write-Host "`nPulse Studio - Windows readiness check`n" -ForegroundColor Magenta

$Docker = Get-Command docker -ErrorAction SilentlyContinue
Check "Docker CLI" ($null -ne $Docker) $(if ($Docker) { $Docker.Source } else { "Install Docker Desktop" })

$WslStatus = (& wsl --status 2>&1 | Out-String)
Check "WSL 2" ($LASTEXITCODE -eq 0 -and $WslStatus -match "2") "WSL backend"

$Engine = if ($Docker) { (& docker info --format '{{.ServerVersion}}' 2>$null | Out-String).Trim() } else { "" }
Check "Docker engine" ([bool]$Engine) $(if ($Engine) { "version $Engine" } else { "Start Docker Desktop" })

$Gpu = (& nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>$null | Select-Object -First 1)
Check "NVIDIA GPU" ([bool]$Gpu) $(if ($Gpu) { $Gpu } else { "GPU or NVIDIA driver not detected" })

if ($Docker -and $Engine) {
    $GpuDocker = (& docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1)
    Check "Docker GPU access" ([bool]$GpuDocker) $(if ($GpuDocker) { $GpuDocker } else { "Enable WSL integration and GPU support" })
    Push-Location $Root
    & docker compose config --quiet 2>$null
    Check "Compose configuration" ($LASTEXITCODE -eq 0) "docker-compose.yml"
    Pop-Location
}

$Drive = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($Root).Substring(0,1))
$FreeGb = [math]::Round($Drive.Free / 1GB, 1)
Check "Free disk space" ($FreeGb -ge 20) "$FreeGb GB available (20 GB recommended)"

$ModelBytes = (Get-ChildItem "$Root\models" -File -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
if ($null -eq $ModelBytes) { $ModelBytes = 0 }
$ModelGb = [math]::Round($ModelBytes / 1GB, 2)
if ($ModelGb -gt 0) { Check "Model cache" $true "$ModelGb GB cached" }
else { Warn "Model cache" "Whisper will download on first TXT alignment" }

$PulseRunning = $false
try { $ExistingHealth = Invoke-RestMethod http://localhost:8000/api/health -TimeoutSec 2; $PulseRunning = $ExistingHealth.status -eq "ok" } catch {}
foreach ($Port in 8000,8080) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    Check "Port $Port" (-not $Listener -or $PulseRunning) $(if ($Listener -and $PulseRunning) { "Pulse Studio is already running" } elseif ($Listener) { "occupied by another process" } else { "available" })
}

if ($Start -and $Failures -eq 0 -and -not $PulseRunning) {
    Write-Host "`nBuilding and starting Pulse Studio..." -ForegroundColor Cyan
    Push-Location $Root
    & docker compose up --build -d
    if ($LASTEXITCODE -eq 0) {
        Start-Sleep -Seconds 3
        try {
            $Health = Invoke-RestMethod http://localhost:8000/api/health -TimeoutSec 10
            Check "Pulse API" ($Health.status -eq "ok") "GPU: $($Health.gpu), NVENC: $($Health.nvenc)"
            Write-Host "`nOpen http://localhost:8080`n" -ForegroundColor Green
        } catch { Check "Pulse API" $false $_.Exception.Message }
    }
    Pop-Location
}
elseif ($Start -and $PulseRunning) { Write-Host "`nPulse Studio is already available at http://localhost:8080`n" -ForegroundColor Green }

if ($Failures -gt 0) { Write-Host "`n$Failures check(s) need attention.`n" -ForegroundColor Yellow; exit 1 }
Write-Host "`nYour workstation is ready for Pulse Studio.`n" -ForegroundColor Green
