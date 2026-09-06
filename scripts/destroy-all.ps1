param([switch]$DeleteData)
if (!$DeleteData) { throw 'Full reset deletes the project S3 bucket and DynamoDB data. Export data first, then pass -DeleteData. Use realtime-stop.ps1 to preserve data.' }
. "$PSScriptRoot/common.ps1"
Invoke-Checked aws @('sts','get-caller-identity')
Invoke-Checked $script:ProjectCdk @('destroy',"$script:ProjectPrefix-realtime",'--exclusively','--force')
Invoke-Checked $script:ProjectCdk @('destroy',"$script:ProjectPrefix-core",'--exclusively','--force')
Write-Host 'Project stacks removed. Shared CDK bootstrap resources and service-created logs may remain; see docs/04-OPERATIONS.md.'
