<#
.SYNOPSIS
    Prepara los archivos de una Release de CellDeck en la carpeta release\.

.DESCRIPTION
    Requiere haber ejecutado antes scripts\build.bat, que crea .venv-build con las
    dependencias verificadas por hash y genera dist\CellDeck.exe (un solo archivo).

    Este script:
      1. Compila la variante de carpeta (CELLDECK_ONEDIR=1) en dist\CellDeck\
      2. Copia release\CellDeck.exe y comprime release\CellDeck-win64.zip
      3. Escribe release\SHA256SUMS.txt (formato de sha256sum)
      4. Escribe release\NOTES.md con la sección de CHANGELOG.md de esta versión

    Lo usan GitHub Actions (.github/workflows/release.yml) y cualquiera que quiera
    reproducir una Release en local (ver docs/RELEASING.md).

.EXAMPLE
    scripts\build.bat
    powershell -ExecutionPolicy Bypass -File scripts\package_release.ps1
#>
[CmdletBinding()]
param(
    [string]$OutDir = "release"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv-build\Scripts\python.exe"
$OneFile = Join-Path $Root "dist\CellDeck.exe"
if (-not (Test-Path $Python)) { throw "No existe .venv-build. Ejecuta primero scripts\build.bat" }
if (-not (Test-Path $OneFile)) { throw "No existe dist\CellDeck.exe. Ejecuta primero scripts\build.bat" }

$Version = (& $Python -c "import sys; sys.path.insert(0, 'src'); import celldeck; print(celldeck.__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $Version) { throw "No se pudo leer la versión de src\celldeck\__init__.py" }
Write-Host "[1/4] CellDeck ${Version}: compilando la variante de carpeta ..."

$env:CELLDECK_ONEDIR = "1"
try {
    & $Python -m PyInstaller --noconfirm --log-level WARN celldeck.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló en la variante de carpeta" }
} finally {
    Remove-Item Env:\CELLDECK_ONEDIR -ErrorAction SilentlyContinue
}
$OneDir = Join-Path $Root "dist\CellDeck"
if (-not (Test-Path (Join-Path $OneDir "CellDeck.exe"))) { throw "No se generó dist\CellDeck\CellDeck.exe" }

Write-Host "[2/4] Copiando y comprimiendo en $OutDir\ ..."
$Out = Join-Path $Root $OutDir
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Path $Out | Out-Null
Copy-Item $OneFile (Join-Path $Out "CellDeck.exe")
# El zip contiene la carpeta CellDeck\ para que al descomprimir no se desparramen archivos.
Compress-Archive -Path $OneDir -DestinationPath (Join-Path $Out "CellDeck-win64.zip") -CompressionLevel Optimal

Write-Host "[3/4] Calculando SHA-256 ..."
$Assets = @("CellDeck.exe", "CellDeck-win64.zip")
$Sums = foreach ($name in $Assets) {
    $hash = (Get-FileHash -Algorithm SHA256 (Join-Path $Out $name)).Hash.ToLowerInvariant()
    "$hash  $name"
}
# Sin BOM y con LF, para que "sha256sum -c SHA256SUMS.txt" también funcione en Linux.
[System.IO.File]::WriteAllText((Join-Path $Out "SHA256SUMS.txt"), (($Sums -join "`n") + "`n"))

Write-Host "[4/4] Notas de la versión ..."
$Changelog = [System.IO.File]::ReadAllText((Join-Path $Root "CHANGELOG.md"))
$Pattern = "(?ms)^## \[" + [regex]::Escape($Version) + "\][^\n]*\n(.*?)(?=^## \[|\z)"
$Match = [regex]::Match($Changelog, $Pattern)
if (-not $Match.Success) { throw "CHANGELOG.md no tiene una sección '## [$Version]'" }

$Nl = "`n"
$Repo = if ($env:GITHUB_REPOSITORY) { $env:GITHUB_REPOSITORY } else { "<dueño>/<repo>" }
$Notes = $Match.Groups[1].Value.Trim() + $Nl + $Nl +
    "## Descarga" + $Nl + $Nl +
    "- **CellDeck.exe**: un solo archivo, se ejecuta sin instalar." + $Nl +
    "- **CellDeck-win64.zip**: la misma app en una carpeta. Arranca más rápido y los antivirus la marcan menos. Descomprímela y abre ``CellDeck\CellDeck.exe``." + $Nl + $Nl +
    "Windows puede mostrar *Windows protegió tu PC*, porque el ejecutable no está firmado. Pulsa **Más información** y después **Ejecutar de todas formas**." + $Nl + $Nl +
    "## SHA-256" + $Nl + $Nl + '```' + $Nl + ($Sums -join $Nl) + $Nl + '```' + $Nl + $Nl +
    "Comprueba que el archivo viene de este repositorio: ``gh attestation verify CellDeck.exe --repo $Repo``." + $Nl
[System.IO.File]::WriteAllText((Join-Path $Out "NOTES.md"), $Notes)

Write-Host ""
Write-Host "[OK] $OutDir\ listo para CellDeck $Version"
Get-ChildItem $Out | Format-Table Name, Length -AutoSize
