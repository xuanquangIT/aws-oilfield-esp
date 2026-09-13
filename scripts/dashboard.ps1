param([ValidateSet('fixture','aws')][string]$Mode='fixture', [ValidateSet('normal','low-flow','stale','unavailable')][string]$FixtureState='normal')
. "$PSScriptRoot/common.ps1"
Invoke-Checked $script:ProjectPython @('-m','dashboard.main','--mode',$Mode,'--fixture-state',$FixtureState)
