<#
.SYNOPSIS
  Ejecuta un botón de PhoneDeck desde PowerShell (útil para probar sin el celular).

.EXAMPLE
  .\scripts\try_action.ps1 -List
  .\scripts\try_action.ps1 media play-pause
  .\scripts\try_action.ps1 pc sleep -Confirm
#>
param(
    [string]$Page,
    [string]$Item,
    [switch]$List,
    [switch]$Confirm,
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$Port"

$session = Invoke-RestMethod "$base/api/session"
$headers = @{ 'X-PhoneDeck-Token' = $session.token }

if ($List -or -not $Page) {
    $cfg = Invoke-RestMethod "$base/api/config" -Headers $headers
    foreach ($p in $cfg.config.pages) {
        Write-Host "[$($p.id)] $($p.name)" -ForegroundColor Cyan
        foreach ($i in $p.items | Where-Object { $_.kind -eq 'button' }) {
            Write-Host ("   {0,-16} {1,-18} ({2})" -f $i.id, $i.label, $i.action.type)
        }
    }
    return
}

$body = @{ page = $Page; item = $Item; confirmed = [bool]$Confirm } | ConvertTo-Json
try {
    $res = Invoke-RestMethod -Method Post "$base/api/run" -Headers $headers `
        -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
    $res | ConvertTo-Json -Depth 5
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 428) { Write-Warning "Requiere confirmación: añade -Confirm" }
    else { Write-Error "HTTP $code - $($_.ErrorDetails.Message)" }
}
