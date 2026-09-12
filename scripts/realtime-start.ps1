param(
    [ValidateRange(1,60)][int]$DurationMinutes=5,
    [ValidateSet('normal','gas_slug','low_flow','mechanical','blockage','sensor_fault','shutdown')]
    [string]$Scenario='normal',
    [ValidateRange(0,600)][int]$DrainTimeoutSeconds=90,
    [ValidateRange(1,60)][int]$ExpiryGraceMinutes=10
)
. "$PSScriptRoot/common.ps1"
$bucket = Get-CoreOutput 'DataBucketName'
$scheduleName = "$script:ProjectPrefix-realtime-expiry"
$latestRunMarker = 'data/producer-runs/.latest'
# A failed producer does not update its marker.  Remember the time before
# work starts so finally never reconciles a completed *previous* run.
$runStartedAtUtc = [DateTime]::UtcNow

# M4: an independent one-shot expiry so this disposable stack cannot outlive
# its agreed deadline just because a laptop or terminal disconnected. This
# is a safety net, not the normal path: normal teardown (below) deletes the
# stack and this schedule itself well before the grace deadline in the
# common case. Remove any stray schedule from an earlier abnormal exit
# first, since a schedule name cannot be reused while one still exists;
# a missing schedule to delete is not an error.
try
{ Invoke-Checked aws @('scheduler','delete-schedule','--name',$scheduleName)
} catch
{
}

$reaperArn = Get-CoreOutput 'ExpiryReaperArn'
$schedulerRoleArn = Get-CoreOutput 'ExpirySchedulerRoleArn'
$deadlineMinutes = $DurationMinutes + $ExpiryGraceMinutes
$fireAt = [DateTime]::UtcNow.AddMinutes($deadlineMinutes).ToString('yyyy-MM-ddTHH:mm:ss')
$reaperInput = @{
    stack_name = "$script:ProjectPrefix-realtime"
    region = if ($env:AWS_DEFAULT_REGION)
    { $env:AWS_DEFAULT_REGION
    } else
    { 'us-east-1'
    }
    run_owner = "$env:USERNAME"
    expires_at_utc = "$fireAt`Z"
} | ConvertTo-Json -Compress
$target = @{Arn = $reaperArn; RoleArn = $schedulerRoleArn; Input = $reaperInput } | ConvertTo-Json -Compress
$targetFile = New-TemporaryFile
Set-Content -Path $targetFile -Value $target -NoNewline
try
{
    Invoke-Checked aws @(
        'scheduler', 'create-schedule', '--name', $scheduleName,
        '--schedule-expression', "at($fireAt)",
        '--schedule-expression-timezone', 'UTC',
        '--flexible-time-window', 'Mode=OFF',
        '--action-after-completion', 'DELETE',
        '--target', "file://$targetFile"
    )
} finally
{
    Remove-Item $targetFile -ErrorAction SilentlyContinue
}
Write-Host "Independent expiry scheduled for $fireAt UTC ($deadlineMinutes minutes from now) if normal teardown does not run first."

try
{
    Invoke-Checked $script:ProjectCdk @('deploy',"$script:ProjectPrefix-realtime",'--exclusively','--require-approval','never')
    Invoke-Checked $script:ProjectPython @('simulator/esp_simulator.py','--stream-name',"$script:ProjectPrefix-realtime",
        '--scenario',$Scenario,'--seconds',"$($DurationMinutes*60)")
    Write-Host 'Allowing 30 seconds for consumers before the drain gate checks archived outcomes.'
    Start-Sleep -Seconds 30
} finally
{
    # M4 drain gate: compare what the producer acknowledged against what
    # consumers actually archived (raw/ or quarantine/) before normal
    # deletion. This can only warn, not block, deletion here -- an operator
    # who is about to tear the stack down anyway needs to see the result,
    # not get stuck by it. A failed/incomplete drain check is reported
    # loudly and never silently treated as a clean run.
    if ((Test-Path $latestRunMarker) -and ((Get-Item $latestRunMarker).LastWriteTimeUtc -ge $runStartedAtUtc))
    {
        $runId = (Get-Content $latestRunMarker -Raw).Trim()
        Write-Host "Drain check for producer run $runId..."
        try
        {
            Invoke-Checked $script:ProjectPython @(
                'scripts/drain-check.py', '--bucket', $bucket, '--run-id', $runId,
                '--timeout-seconds', "$DrainTimeoutSeconds"
            )
        } catch
        {
            Write-Warning "Drain check reported this run incomplete or failed to run; see data/drain-receipts/$runId.json. Proceeding to teardown regardless -- investigate before trusting this run's data."
        }
    } else
    {
        Write-Warning 'No producer run marker found; skipping the drain gate.'
    }
    Write-Host 'Removing the realtime stack; inspect AWS if this cleanup fails.'
    Invoke-Checked $script:ProjectCdk @('destroy',"$script:ProjectPrefix-realtime",'--exclusively','--force')
    # Normal teardown succeeded: the independent expiry is no longer
    # needed. Best-effort only -- if this fails, the schedule will still
    # fire later, find the stack already gone, and no-op safely.
    try
    { Invoke-Checked aws @('scheduler','delete-schedule','--name',$scheduleName)
    } catch
    {
    }
}
