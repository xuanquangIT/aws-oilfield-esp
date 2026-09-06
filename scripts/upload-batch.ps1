. "$PSScriptRoot/common.ps1"
if (!(Test-Path data/historical.csv)) { throw 'Generate data first: .venv/Scripts/python.exe scripts/seed-batch-data.py' }
$bucket = Get-CoreOutput 'DataBucketName'
Invoke-Checked aws @('s3','cp','data/historical.csv',"s3://$bucket/raw/batch/historical.csv")
