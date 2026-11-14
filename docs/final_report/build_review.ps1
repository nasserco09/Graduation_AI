param([switch]$OnlyCached)
# Compatibility entry point; preserves the historical Chapter 1 PDF.
& (Join-Path $PSScriptRoot "build_report.ps1") -OnlyCached:$OnlyCached
