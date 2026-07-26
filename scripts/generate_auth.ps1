# scripts/generate_auth.ps1
param(
  [string]$ClientId = $env:FYERS_CLIENT_ID,
  [string]$RedirectUri = $env:REDIRECT_URI
)

if (-not $ClientId -or -not $RedirectUri) {
  Write-Host "Set FYERS_CLIENT_ID and REDIRECT_URI environment variables first."
  exit 1
}

$state = [System.Guid]::NewGuid().ToString("N")
# Save state to a file for later verification (optional)
$state | Out-File -FilePath ".oauth_state" -Encoding ascii

$params = @{
  client_id = $ClientId
  redirect_uri = $RedirectUri
  response_type = "code"
  state = $state
}
$query = ($params.GetEnumerator() | ForEach-Object { "$($_.Key)=$([uri]::EscapeDataString($_.Value))" }) -join "&"
$url = "https://api-t1.fyers.in/api/v3/generate-authcode?$query"
Write-Host "Opening: $url"
Start-Process $url
