param([string]$BudgetEmail)
. "$PSScriptRoot/common.ps1"
Invoke-Checked aws @('sts','get-caller-identity')
$arguments = @('deploy',"$script:ProjectPrefix-core",'--require-approval','never')
if ($BudgetEmail) { $arguments += @('-c',"budget_email=$BudgetEmail") }
else { Write-Warning 'No BudgetEmail supplied: the $5 account budget will have no email notifications.' }
Invoke-Checked $script:ProjectCdk $arguments
