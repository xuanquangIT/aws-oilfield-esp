param(
    [ValidateRange(1,60)][int]$DurationMinutes=5,
    [ValidateSet('normal','gas_slug','low_flow','mechanical','blockage','sensor_fault','shutdown')]
    [string]$Scenario='normal'
)
. "$PSScriptRoot/common.ps1"
Get-CoreOutput 'DataBucketName' | Out-Null
try {
    Invoke-Checked $script:ProjectCdk @('deploy',"$script:ProjectPrefix-realtime",'--exclusively','--require-approval','never')
    Invoke-Checked $script:ProjectPython @('simulator/esp_simulator.py','--stream-name',"$script:ProjectPrefix-realtime",
        '--scenario',$Scenario,'--seconds',"$($DurationMinutes*60)")
    Write-Host 'Allowing 30 seconds for consumers. This grace period does not prove all records were processed.'
    Start-Sleep -Seconds 30
}
finally {
    Write-Host 'Removing the realtime stack; inspect AWS if this cleanup fails.'
    Invoke-Checked $script:ProjectCdk @('destroy',"$script:ProjectPrefix-realtime",'--exclusively','--force')
}
