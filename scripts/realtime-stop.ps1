. "$PSScriptRoot/common.ps1"
Invoke-Checked $script:ProjectCdk @('destroy',"$script:ProjectPrefix-realtime",'--exclusively','--force')
