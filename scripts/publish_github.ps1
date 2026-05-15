param(
    [string]$Owner = "",
    [string]$RepoName = "garmin-cn-coach-stack",
    [ValidateSet("web", "token")]
    [string]$AuthMethod = "web"
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
Set-Location $projectDir

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI not found. Install gh first."
}

$Gh = (Get-Command gh.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if ([string]::IsNullOrWhiteSpace($Gh)) {
    throw "Official gh.exe not found. Install GitHub CLI."
}

if ($AuthMethod -eq "web") {
    & $Gh auth login --web --git-protocol https
} else {
    $secure = Read-Host "Paste GitHub PAT locally" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $token | & $Gh auth login --with-token
    } finally {
        if ($ptr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    }
}

$resolvedOwner = $Owner
if ([string]::IsNullOrWhiteSpace($resolvedOwner)) {
    $resolvedOwner = & $Gh api user --jq .login
}

$fullName = "$resolvedOwner/$RepoName"

try {
    & $Gh repo view $fullName | Out-Null
} catch {
    & $Gh repo create $fullName --public --source . --remote origin --push --description "Local-first Garmin Connect China automation stack"
    exit 0
}

$remoteUrl = "https://github.com/$fullName.git"
if ((git remote) -contains "origin") {
    git remote set-url origin $remoteUrl
} else {
    git remote add origin $remoteUrl
}

git branch -M main
git push -u origin main
