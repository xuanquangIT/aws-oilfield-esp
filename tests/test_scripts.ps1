$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($file in Get-ChildItem "$root/scripts/*.ps1")
{
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count)
    { throw "PowerShell parse error: $($file.Name): $parseErrors"
    }
}

# Test the real native exit-code wrapper, using a local failing Python process.
. "$root/scripts/common.ps1"
$failed = $false
try
{ Invoke-Checked $script:ProjectPython @('-c', 'raise SystemExit(7)')
} catch
{ $failed = $true
}
if (!$failed)
{ throw 'Native failures must throw.'
}

# Execute the actual wrapper body with cloud/process dependencies replaced.
# No AWS commands or deployments are allowed in these behavioral tests.
#
# Operation keys are "$Command $($Arguments[0])" for most calls, but
# "aws scheduler <subcommand>" for scheduler calls specifically, since
# realtime-start.ps1 calls both create-schedule and delete-schedule (twice)
# and "aws scheduler" alone would not tell them apart.
function Test-Wrapper
{
    param([string]$File, [string]$FailureAt, [string[]]$ExpectedCommands)
    $script:Calls = [System.Collections.Generic.List[string]]::new()
    $script:FailureAt = $FailureAt
    $script:ProjectPrefix = 'unit-test'
    $script:ProjectCdk = 'fake-cdk'
    $script:ProjectPython = 'fake-python'
    function Invoke-Checked
    {
        param([string]$Command, [string[]]$Arguments)
        $operation = if ($Command -eq 'aws' -and $Arguments[0] -eq 'scheduler')
        {
            "aws scheduler $($Arguments[1])"
        } else
        {
            "$Command $($Arguments[0])"
        }
        $script:Calls.Add($operation)
        if ($operation -eq $script:FailureAt)
        { throw 'Injected native failure'
        }
    }
    function Get-CoreOutput
    { param([string]$Key) return 'fixture-output'
    }
    function Start-Sleep
    { param([int]$Seconds)
    }
    $body = Get-Content "$root/scripts/$File" -Raw
    $body = $body -replace '(?m)^\. "\$PSScriptRoot/common\.ps1"\r?\n', ''
    $threw = $false
    try
    { & ([scriptblock]::Create($body))
    } catch
    { $threw = $true
    }
    if ($FailureAt -and !$threw)
    { throw "$File should fail when $FailureAt fails."
    }
    if (!$FailureAt -and $threw)
    { throw "$File unexpectedly failed."
    }
    if (($script:Calls -join '|') -ne ($ExpectedCommands -join '|'))
    {
        throw "$File wrong call order: $($script:Calls -join ', ')"
    }
}

# The drain gate only runs if a producer left behind a run marker; remove
# any stray local marker first so these baseline cases are deterministic
# regardless of what a real esp_simulator.py run may have left on disk.
$latestMarker = "$root/data/producer-runs/.latest"
$savedMarker = $null
if (Test-Path $latestMarker)
{
    $savedMarker = Get-Content $latestMarker -Raw
    Remove-Item $latestMarker
}
try
{
    $baseline = @(
        'aws scheduler delete-schedule', 'aws scheduler create-schedule',
        'fake-cdk deploy', 'fake-python simulator/esp_simulator.py',
        'fake-cdk destroy', 'aws scheduler delete-schedule'
    )
    Test-Wrapper 'realtime-start.ps1' '' $baseline

    # A schedule creation failure means the independent expiry cannot be
    # guaranteed, so the script must refuse to touch the stream at all --
    # it should stop before ever calling cdk deploy.
    Test-Wrapper 'realtime-start.ps1' 'aws scheduler create-schedule' @(
        'aws scheduler delete-schedule', 'aws scheduler create-schedule'
    )

    Test-Wrapper 'realtime-start.ps1' 'fake-cdk deploy' @(
        'aws scheduler delete-schedule', 'aws scheduler create-schedule',
        'fake-cdk deploy', 'fake-cdk destroy', 'aws scheduler delete-schedule'
    )
    Test-Wrapper 'realtime-start.ps1' 'fake-python simulator/esp_simulator.py' @(
        'aws scheduler delete-schedule', 'aws scheduler create-schedule',
        'fake-cdk deploy', 'fake-python simulator/esp_simulator.py',
        'fake-cdk destroy', 'aws scheduler delete-schedule'
    )
    # A destroy failure is fatal, and true to a real abnormal exit, the
    # cleanup step after it (deleting the now-pointless schedule) never
    # gets a chance to run either -- the independent expiry will still
    # fire later and find the stack already stuck, which is the point.
    Test-Wrapper 'realtime-start.ps1' 'fake-cdk destroy' @(
        'aws scheduler delete-schedule', 'aws scheduler create-schedule',
        'fake-cdk deploy', 'fake-python simulator/esp_simulator.py',
        'fake-cdk destroy'
    )

    # Dedicated case: a producer run marker is present, so the drain gate
    # must run (as its own launcher/observer Invoke-Checked call) before
    # teardown, and a failing drain check must not block the destroy step.
    New-Item -ItemType Directory -Force -Path (Split-Path $latestMarker) | Out-Null
    Set-Content $latestMarker 'fixture-run-id' -NoNewline
    # The real simulator writes this marker after realtime-start.ps1 records
    # its run start time. Model that fresh write rather than a stale marker
    # inherited from a previous run.
    (Get-Item $latestMarker).LastWriteTimeUtc = [DateTime]::UtcNow.AddMinutes(1)
    Test-Wrapper 'realtime-start.ps1' '' @(
        'aws scheduler delete-schedule', 'aws scheduler create-schedule',
        'fake-cdk deploy', 'fake-python simulator/esp_simulator.py',
        'fake-python scripts/drain-check.py', 'fake-cdk destroy',
        'aws scheduler delete-schedule'
    )

    # An incomplete/failing drain check is a warning, not a fatal error: it
    # must not stop teardown, unlike deploy/simulator/destroy above.
    # Test-Wrapper asserts "the wrapper throws when FailureAt fails", which
    # is the wrong shape for this one case, so check it directly instead.
    $script:Calls = [System.Collections.Generic.List[string]]::new()
    $script:FailureAt = 'fake-python scripts/drain-check.py'
    $script:ProjectPrefix = 'unit-test'
    $script:ProjectCdk = 'fake-cdk'
    $script:ProjectPython = 'fake-python'
    function Invoke-Checked
    {
        param([string]$Command, [string[]]$Arguments)
        $operation = if ($Command -eq 'aws' -and $Arguments[0] -eq 'scheduler')
        {
            "aws scheduler $($Arguments[1])"
        } else
        {
            "$Command $($Arguments[0])"
        }
        $script:Calls.Add($operation)
        if ($operation -eq $script:FailureAt)
        { throw 'Injected native failure'
        }
    }
    function Get-CoreOutput
    { param([string]$Key) return 'fixture-output'
    }
    function Start-Sleep
    { param([int]$Seconds)
    }
    $body = Get-Content "$root/scripts/realtime-start.ps1" -Raw
    $body = $body -replace '(?m)^\. "\$PSScriptRoot/common\.ps1"\r?\n', ''
    $threw = $false
    try
    { & ([scriptblock]::Create($body))
    } catch
    { $threw = $true
    }
    if ($threw)
    { throw 'realtime-start.ps1 must not fail the whole run just because the drain check did.'
    }
    $expected = @(
        'aws scheduler delete-schedule', 'aws scheduler create-schedule',
        'fake-cdk deploy', 'fake-python simulator/esp_simulator.py',
        'fake-python scripts/drain-check.py', 'fake-cdk destroy',
        'aws scheduler delete-schedule'
    )
    if (($script:Calls -join '|') -ne ($expected -join '|'))
    {
        throw "realtime-start.ps1 wrong call order after a failed drain check: $($script:Calls -join ', ')"
    }
    Remove-Item $latestMarker
} finally
{
    if ($savedMarker)
    {
        New-Item -ItemType Directory -Force -Path (Split-Path $latestMarker) | Out-Null
        Set-Content $latestMarker $savedMarker -NoNewline
    }
}

$blocked = $false
try
{ & "$root/scripts/destroy-all.ps1"
} catch
{ $blocked = $true
}
if (!$blocked)
{ throw 'Reset must require explicit data deletion intent.'
}

function Test-Batch
{
    # M4: the state machine now owns Glue + crawler completion end to end, so
    # this wrapper is only a launcher/observer: start the execution, then
    # poll its status. There is no client-side crawler orchestration left to
    # fixture here.
    param([string]$WorkflowStatus)
    function Get-CoreOutput
    { param([string]$Key) return 'fixture-output'
    }
    function Invoke-Checked
    {
        param([string]$Command, [string[]]$Arguments)
        if ($Command -eq 'fake-python')
        {
            return '{"manifest_key":"manifests/fixture/input-manifest.json"}'
        }
        switch ($Arguments[1])
        {
            'start-execution'
            { return 'fixture-execution'
            }
            'describe-execution'
            { return $WorkflowStatus
            }
            default
            { throw "Unexpected cloud operation: $Arguments"
            }
        }
    }
    function Wait-AwsState
    {
        param([scriptblock]$ReadState, [string]$Success, [string[]]$Failure, [int]$TimeoutSeconds)
        foreach ($attempt in 1..4)
        {
            $state = & $ReadState
            if ($state -eq $Success)
            { return
            }
            if ($state -in $Failure)
            { throw "Expected injected failure: $state"
            }
        }
        throw 'Fixture did not complete.'
    }
    $body = (Get-Content "$root/scripts/run-batch.ps1" -Raw) -replace '(?m)^\. "\$PSScriptRoot/common\.ps1"\r?\n', ''
    $threw = $false
    try
    { & ([scriptblock]::Create($body))
    } catch
    { $threw = $true
    }
    $shouldFail = $WorkflowStatus -ne 'SUCCEEDED'
    if ($threw -ne $shouldFail)
    { throw 'Incorrect batch result.'
    }
}
Test-Batch 'SUCCEEDED'
Test-Batch 'FAILED'
Write-Host 'PowerShell checks passed: syntax, native errors, six cleanup paths, reset guard, two batch paths.'
