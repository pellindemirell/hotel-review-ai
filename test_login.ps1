$ErrorActionPreference = 'Stop'
function Test-Login ($email, $password) {
    $body = @{ email = $email; password = $password } | ConvertTo-Json
    try {
        $response = Invoke-RestMethod -Uri 'http://localhost:5012/api/auth/login' -Method Post -Body $body -ContentType 'application/json'
        return $response.data.token
    } catch {
        Write-Host "Login Failed for $email : $($_.Exception.Message)"
        return $null
    }
}

function Decode-Jwt ($token) {
    $parts = $token.Split('.')
    if ($parts.Length -lt 2) { return $null }
    $payload = $parts[1]
    $pad = $payload.Length % 4
    if ($pad -eq 2) { $payload += '==' } elseif ($pad -eq 3) { $payload += '=' }
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($payload)) | ConvertFrom-Json
}

Write-Host "--- Testing Login ---"
$t1 = Test-Login 'superadmin@hotelgroup.com' 'Admin123!'
$t2 = Test-Login 'admin@adora.com' 'Admin123!'
$t3 = Test-Login 'housekeeping@adora.com' 'Admin123!'

if ($t1) { Write-Host "SuperAdmin token:"; Decode-Jwt $t1 | ConvertTo-Json -Depth 1 }
if ($t2) { Write-Host "HotelAdmin token:"; Decode-Jwt $t2 | ConvertTo-Json -Depth 1 }
if ($t3) { Write-Host "DepartmentManager token:"; Decode-Jwt $t3 | ConvertTo-Json -Depth 1 }
