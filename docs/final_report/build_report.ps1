param([switch]$OnlyCached)

$ErrorActionPreference = 'Stop'
$documentRoot = $PSScriptRoot
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $documentRoot)
$buildRoot = Join-Path $documentRoot 'build_submission'
if (Test-Path -LiteralPath (Join-Path $repositoryRoot 'app.py')) {
    $outputRoot = Join-Path $repositoryRoot 'output\pdf'
    $portableEngine = Join-Path $repositoryRoot 'evaluation\cache\latex_runtime\tectonic_0_17_0\tectonic.exe'
} else {
    # Standalone source ZIP: build beside the extracted project, not in an ancestor folder.
    $outputRoot = Join-Path $documentRoot 'output'
    $portableEngine = $null
}
$previousFontConfig = $env:FONTCONFIG_FILE
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
Push-Location $documentRoot
try {
    $engineCommand = Get-Command tectonic -ErrorAction SilentlyContinue
    $classicCommand = Get-Command pdflatex -ErrorAction SilentlyContinue
    if ($portableEngine -and (Test-Path -LiteralPath $portableEngine)) {
        $enginePath = $portableEngine
    } elseif ($engineCommand) {
        $enginePath = $engineCommand.Source
    } else {
        $enginePath = $null
    }
    if ($enginePath) {
        if (([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) -and -not $previousFontConfig) {
            $fontConfigPath = Join-Path $buildRoot 'fontconfig.conf'
            $fontCacheRoot = Join-Path $buildRoot 'fontconfig-cache'
            New-Item -ItemType Directory -Path $fontCacheRoot -Force | Out-Null
            $fontDirectoryXml = [System.Security.SecurityElement]::Escape((Join-Path $env:WINDIR 'Fonts').Replace('\','/'))
            $fontCacheXml = [System.Security.SecurityElement]::Escape($fontCacheRoot.Replace('\','/'))
            $fontConfigXml = '<fontconfig><dir>' + $fontDirectoryXml + '</dir><cachedir>' + $fontCacheXml + '</cachedir></fontconfig>'
            [IO.File]::WriteAllText($fontConfigPath, $fontConfigXml)
            $env:FONTCONFIG_FILE = $fontConfigPath
        }
        $engineArguments = @('--outdir', 'build_submission', '--keep-logs', '--keep-intermediates')
        if ($OnlyCached) { $engineArguments += '--only-cached' }
        $engineArguments += 'main.tex'
        & $enginePath @engineArguments
        if ($LASTEXITCODE -ne 0) { throw 'LaTeX compilation failed.' }
    } elseif ($classicCommand) {
        if ($OnlyCached) { throw 'OnlyCached requires Tectonic.' }
        $bibliographyCommand = Get-Command bibtex -ErrorAction SilentlyContinue
        if (-not $bibliographyCommand) { throw 'BibTeX is required for the report references.' }
        & $classicCommand.Source '-interaction=nonstopmode' '-halt-on-error' '-output-directory=build_submission' 'main.tex'
        if ($LASTEXITCODE -ne 0) { throw 'Initial LaTeX compilation failed.' }
        & $bibliographyCommand.Source 'build_submission/main'
        if ($LASTEXITCODE -ne 0) { throw 'Bibliography compilation failed.' }
        for ($passNumber = 1; $passNumber -le 2; $passNumber++) {
            & $classicCommand.Source '-interaction=nonstopmode' '-halt-on-error' '-output-directory=build_submission' 'main.tex'
            if ($LASTEXITCODE -ne 0) { throw 'LaTeX compilation failed.' }
        }
    } else {
        throw 'No LaTeX engine found. Open this project in Codex or install Tectonic or a TeX distribution.'
    }
    $builtPdf = Join-Path $buildRoot 'main.pdf'
    if (-not (Test-Path -LiteralPath $builtPdf)) { throw 'No PDF was produced.' }
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    $reviewPdf = Join-Path $outputRoot 'AI_Visual_Product_Search_Submission_2026.pdf'
    Copy-Item -LiteralPath $builtPdf -Destination $reviewPdf -Force
    Write-Output $reviewPdf
} finally {
    $env:FONTCONFIG_FILE = $previousFontConfig
    Pop-Location
}
