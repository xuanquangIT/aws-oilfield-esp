. "$PSScriptRoot/common.ps1"
$arn = Get-CoreOutput 'StateMachineArn'
$execution = Invoke-Checked aws @('stepfunctions','start-execution','--state-machine-arn',$arn,'--query','executionArn','--output','text')
Write-Host "Execution: $execution"
Wait-AwsState -ReadState {
    Invoke-Checked aws @('stepfunctions','describe-execution','--execution-arn',$execution,'--query','status','--output','text')
} -Success 'SUCCEEDED' -Failure @('FAILED','TIMED_OUT','ABORTED')
$crawler = Get-CoreOutput 'GlueCrawlerName'
$previousCrawl = Invoke-Checked aws @('glue','get-crawler','--name',$crawler,'--query','Crawler.LastCrawl.StartTime','--output','json') | ConvertFrom-Json
Invoke-Checked aws @('glue','start-crawler','--name',$crawler)
Wait-AwsState -ReadState {
    $result = Invoke-Checked aws @('glue','get-crawler','--name',$crawler,'--query','Crawler','--output','json') | ConvertFrom-Json
    if ($result.State -ne 'READY' -or !$result.PSObject.Properties['LastCrawl']) { return 'WAITING' }
    if ([string]$result.LastCrawl.StartTime -eq [string]$previousCrawl) { return 'WAITING' }
    return $result.LastCrawl.Status
} -Success 'SUCCEEDED' -Failure @('FAILED','CANCELLED') -TimeoutSeconds 900
Write-Host 'ETL and crawler succeeded. Run the SQL in docs/04-OPERATIONS.md using the project Athena workgroup.'
