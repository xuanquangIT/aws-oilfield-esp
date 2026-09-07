Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $script:ProjectRoot
$env:JSII_RUNTIME_PACKAGE_CACHE_ROOT = Join-Path $script:ProjectRoot '.cache/jsii'
$script:ProjectPrefix = (Get-Content (Join-Path $script:ProjectRoot 'cdk.json') -Raw | ConvertFrom-Json).context.project_prefix
$script:ProjectPython = Join-Path $script:ProjectRoot '.venv/Scripts/python.exe'
$script:ProjectCdk = Join-Path $script:ProjectRoot 'node_modules/.bin/cdk.cmd'
if (!(Test-Path $script:ProjectPython)) { throw 'Create .venv and install requirements first. See docs/01-GETTING-STARTED.md.' }
if (!(Test-Path $script:ProjectCdk)) { throw 'Run npm ci first. See docs/01-GETTING-STARTED.md.' }
$env:PATH = "$(Split-Path $script:ProjectPython);$env:PATH"
$env:AWS_PAGER = ''

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed (exit $LASTEXITCODE)." }
}

function Get-CoreOutput {
    param([string]$Key)
    $result = Invoke-Checked aws @('cloudformation','describe-stacks','--stack-name',"$script:ProjectPrefix-core",
        '--query',"Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue",'--output','text')
    if (!$result -or $result -eq 'None') { throw "Missing core output: $Key" }
    return "$result".Trim()
}

function Wait-AwsState {
    param([scriptblock]$ReadState, [string]$Success, [string[]]$Failure, [int]$TimeoutSeconds=1200)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $state = & $ReadState
        if ($state -eq $Success) { return }
        if ($state -in $Failure) { throw "AWS operation ended with $state" }
        Start-Sleep -Seconds 10
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Timed out waiting for AWS. The remote operation may still be running; inspect it before retrying.'
}
