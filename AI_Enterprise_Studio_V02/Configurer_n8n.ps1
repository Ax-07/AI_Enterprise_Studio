# One-time setup. Secret stored by Windows DPAPI for the current Windows user.
$ErrorActionPreference = 'Stop'
$folder = Join-Path $env:LOCALAPPDATA 'AIEnterpriseStudio'
$file = Join-Path $folder 'n8n-token.dpapi'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
if (-not (Test-Path -LiteralPath $file)) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    ConvertTo-SecureString $token -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -LiteralPath $file -Encoding ascii
} else {
    $secret = Get-Content -LiteralPath $file -Raw | ConvertTo-SecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
Set-Clipboard -Value $token
Write-Host 'Jeton copie dans le presse-papiers LOCAL. Ne le transmets jamais dans un chat.'
Write-Host 'Dans n8n local, importe les deux JSON du dossier n8n. Sur chaque Webhook, Header Auth :'
Write-Host 'Cree une seule credential (nom AES Local), Name = X-AES-Token, Value = coller le jeton. Reutilise-la pour les deux.'
Write-Host 'Publie les deux workflows. Efface ensuite le presse-papiers (Set-Clipboard -Value " " ; efface aussi son historique si active).'
Start-Process 'http://127.0.0.1:5678'
