$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($file in Get-ChildItem "$root/scripts/*.ps1") {
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count) { throw "PowerShell parse error: $($file.Name): $parseErrors" }
}

# Test the real native exit-code wrapper, using a local failing Python process.
. "$root/scripts/common.ps1"
$failed = $false
try { Invoke-Checked $script:ProjectPython @('-c','raise SystemExit(7)') }
catch { $failed = $true }
if (!$failed) { throw 'Native failures must throw.' }

# Execute the actual wrapper body with cloud/process dependencies replaced.
# No AWS commands or deployments are allowed in these behavioral tests.
function Test-Wrapper {
    param([string]$File, [string]$FailureAt, [string[]]$ExpectedCommands)
    $script:Calls = [System.Collections.Generic.List[string]]::new()
    $script:FailureAt = $FailureAt
    $script:ProjectPrefix = 'unit-test'
    $script:ProjectCdk = 'fake-cdk'
    $script:ProjectPython = 'fake-python'
    function Invoke-Checked {
        param([string]$Command, [string[]]$Arguments)
        $operation = "$Command $($Arguments[0])"
        $script:Calls.Add($operation)
        if ($operation -eq $script:FailureAt) { throw 'Injected native failure' }
    }
    function Get-CoreOutput { param([string]$Key) return 'fixture-output' }
    function Start-Sleep { param([int]$Seconds) }
    $body = Get-Content "$root/scripts/$File" -Raw
    $body = $body -replace '(?m)^\. "\$PSScriptRoot/common\.ps1"\r?\n', ''
    $threw = $false
    try { & ([scriptblock]::Create($body)) }
    catch { $threw = $true }
    if ($FailureAt -and !$threw) { throw "$File should fail when $FailureAt fails." }
    if (!$FailureAt -and $threw) { throw "$File unexpectedly failed." }
    if (($script:Calls -join '|') -ne ($ExpectedCommands -join '|')) {
        throw "$File wrong call order: $($script:Calls -join ', ')"
    }
}
Test-Wrapper 'realtime-start.ps1' '' @('fake-cdk deploy','fake-python simulator/esp_simulator.py','fake-cdk destroy')
Test-Wrapper 'realtime-start.ps1' 'fake-cdk deploy' @('fake-cdk deploy','fake-cdk destroy')
Test-Wrapper 'realtime-start.ps1' 'fake-python simulator/esp_simulator.py' @('fake-cdk deploy','fake-python simulator/esp_simulator.py','fake-cdk destroy')
Test-Wrapper 'realtime-start.ps1' 'fake-cdk destroy' @('fake-cdk deploy','fake-python simulator/esp_simulator.py','fake-cdk destroy')
$blocked = $false
try { & "$root/scripts/destroy-all.ps1" }
catch { $blocked = $true }
if (!$blocked) { throw 'Reset must require explicit data deletion intent.' }
function Test-Batch {
    param([string]$WorkflowStatus, [string]$CrawlStatus)
    $script:CrawlStarted = $false
    $script:CrawlReads = 0
    function Get-CoreOutput { param([string]$Key) return 'fixture-output' }
    function Invoke-Checked {
        param([string]$Command, [string[]]$Arguments)
        if ($Command -eq 'fake-python') {
            return '{"manifest_key":"manifests/fixture/input-manifest.json"}'
        }
        switch ($Arguments[1]) {
            'start-execution' { return 'fixture-execution' }
            'describe-execution' { return $WorkflowStatus }
            'start-crawler' { $script:CrawlStarted = $true; return }
            'get-crawler' {
                if ($Arguments -contains 'Crawler.LastCrawl.StartTime') { return '"2026-09-04T00:00:00Z"' }
                $script:CrawlReads++
                # Simulate eventually consistent metadata: prior success must not close this run.
                if ($script:CrawlReads -eq 1) {
                    return '{"State":"READY","LastCrawl":{"StartTime":"2026-09-04T00:00:00Z","Status":"SUCCEEDED"}}'
                }
                return (@{State='READY'; LastCrawl=@{StartTime='2026-09-05T00:00:00Z'; Status=$CrawlStatus}} | ConvertTo-Json -Compress)
            }
            default { throw "Unexpected cloud operation: $Arguments" }
        }
    }
    function Wait-AwsState {
        param([scriptblock]$ReadState, [string]$Success, [string[]]$Failure, [int]$TimeoutSeconds)
        foreach ($attempt in 1..4) {
            $state = & $ReadState
            if ($state -eq $Success) { return }
            if ($state -in $Failure) { throw "Expected injected failure: $state" }
        }
        throw 'Fixture did not complete.'
    }
    $body = (Get-Content "$root/scripts/run-batch.ps1" -Raw) -replace '(?m)^\. "\$PSScriptRoot/common\.ps1"\r?\n', ''
    $threw = $false
    try { & ([scriptblock]::Create($body)) }
    catch { $threw = $true }
    $shouldFail = $WorkflowStatus -ne 'SUCCEEDED' -or $CrawlStatus -ne 'SUCCEEDED'
    if ($threw -ne $shouldFail) { throw 'Incorrect batch result.' }
    if ($WorkflowStatus -ne 'SUCCEEDED' -and $script:CrawlStarted) { throw 'Crawler started after failed ETL.' }
    if ($WorkflowStatus -eq 'SUCCEEDED' -and $script:CrawlReads -ne 2) { throw 'Stale crawler result was accepted.' }
}
Test-Batch 'SUCCEEDED' 'SUCCEEDED'
Test-Batch 'FAILED' 'SUCCEEDED'
Test-Batch 'SUCCEEDED' 'FAILED'
Write-Host 'PowerShell checks passed: syntax, native errors, four cleanup paths, reset guard, three batch paths including stale crawler metadata.'
