$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$file = Join-Path $env:LOCALAPPDATA 'AIEnterpriseStudio\n8n-token.dpapi'
if (-not $env:AES_N8N_TOKEN -and (Test-Path -LiteralPath $file)) {
    try {
        $secret = Get-Content -LiteralPath $file -Raw | ConvertTo-SecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
        try { $env:AES_N8N_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    } catch { Write-Warning 'Jeton local inaccessible. n8n reste desactive; relancer Configurer_n8n.ps1 si necessaire.' }
}
try {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 serveur.py } else { & python serveur.py }
} finally { Remove-Item Env:AES_N8N_TOKEN -ErrorAction SilentlyContinue }
