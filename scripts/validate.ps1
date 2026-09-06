. "$PSScriptRoot/common.ps1"
$env:JSII_RUNTIME_PACKAGE_CACHE_ROOT = Join-Path $script:ProjectRoot '.cache/jsii'
Invoke-Checked $script:ProjectPython @('-m','pytest','-q')
Invoke-Checked $script:ProjectPython @('scripts/check-docs.py')
& "$script:ProjectRoot/tests/test_scripts.ps1"
Invoke-Checked $script:ProjectCdk @('synth','--quiet','--no-lookups','--no-telemetry')
Write-Host 'Offline validation passed. No AWS deployment or runtime validation was performed.'
