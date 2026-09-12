param(
    [string]$StartDate = ([DateTime]::UtcNow.Date.AddDays(-6).ToString('yyyy-MM-dd')),
    [string]$EndDate = ([DateTime]::UtcNow.Date.ToString('yyyy-MM-dd')),
    [ValidateRange(0, 30)][int]$LateArrivalLookbackDays = 1,
    [string]$ManifestKey
)

. "$PSScriptRoot/common.ps1"

try {
    $start = [DateTime]::ParseExact($StartDate, 'yyyy-MM-dd', $null)
    $end = [DateTime]::ParseExact($EndDate, 'yyyy-MM-dd', $null)
}
catch {
    throw 'StartDate and EndDate must be UTC dates in yyyy-MM-dd format.'
}
if ($start -gt $end) { throw 'StartDate must be on or before EndDate.' }

$runId = "m3-$([Guid]::NewGuid().ToString('N'))"
$bucket = Get-CoreOutput 'DataBucketName'
if (!$ManifestKey) {
    $manifestId = "m3-manifest-$([Guid]::NewGuid().ToString('N'))"
    $created = Invoke-Checked $script:ProjectPython @(
        'scripts/create-m3-manifest.py', '--bucket', $bucket,
        '--manifest-id', $manifestId,
        '--start-date', $StartDate,
        '--end-date', $EndDate,
        '--late-arrival-lookback-days', "$LateArrivalLookbackDays"
    )
    $ManifestKey = (($created | Select-Object -Last 1) | ConvertFrom-Json).manifest_key
}
if (!$ManifestKey) { throw 'M3 input manifest creation did not return a manifest key.' }

$arn = Get-CoreOutput 'StateMachineArn'
$executionInput = @{
    run_id = $runId
    input_manifest_key = $ManifestKey
} | ConvertTo-Json -Compress
$execution = Invoke-Checked aws @(
    'stepfunctions', 'start-execution', '--state-machine-arn', $arn,
    '--input', $executionInput, '--query', 'executionArn', '--output', 'text'
)
Write-Host "M3 run: $runId"
Write-Host "Input manifest: $ManifestKey"
Write-Host "Execution: $execution"
Wait-AwsState -ReadState {
    Invoke-Checked aws @('stepfunctions','describe-execution','--execution-arn',$execution,'--query','status','--output','text')
} -Success 'SUCCEEDED' -Failure @('FAILED','TIMED_OUT','ABORTED')

# The crawler is a catalog discovery exercise. The approved consumer handoff
# is curated/publication/current.json, written by Glue only after its M3 DQ
# gate passes; a failed run therefore leaves the previous pointer unchanged.
$crawler = Get-CoreOutput 'GlueCrawlerName'
$previousCrawl = Invoke-Checked aws @('glue','get-crawler','--name',$crawler,'--query','Crawler.LastCrawl.StartTime','--output','json') | ConvertFrom-Json
Invoke-Checked aws @('glue','start-crawler','--name',$crawler)
Wait-AwsState -ReadState {
    $result = Invoke-Checked aws @('glue','get-crawler','--name',$crawler,'--query','Crawler','--output','json') | ConvertFrom-Json
    if ($result.State -ne 'READY' -or !$result.PSObject.Properties['LastCrawl']) { return 'WAITING' }
    if ([string]$result.LastCrawl.StartTime -eq [string]$previousCrawl) { return 'WAITING' }
    return $result.LastCrawl.Status
} -Success 'SUCCEEDED' -Failure @('FAILED','CANCELLED') -TimeoutSeconds 900
Write-Host "M3 ETL and crawler succeeded. Inspect s3://$bucket/staging/m3/$runId/quality-report.json and curated/publication/current.json before querying Athena."
