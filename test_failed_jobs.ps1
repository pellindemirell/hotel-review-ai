$ErrorActionPreference = 'Stop'
function Test-Login ($email, $password) {
    $body = @{ email = $email; password = $password } | ConvertTo-Json
    try {
        $response = Invoke-RestMethod -Uri 'http://localhost:5012/api/auth/login' -Method Post -Body $body -ContentType 'application/json'
        return $response.data.token
    } catch {
        return $null
    }
}

function Test-FailedJobs ($token, $name) {
    try {
        $response = Invoke-RestMethod -Uri 'http://localhost:5012/api/system/failed-jobs' -Method Get -Headers @{ Authorization = "Bearer $token" }
        Write-Host "$name GetFailedJobs: SUCCESS"
    } catch {
        Write-Host "$name GetFailedJobs: FAILED - $($_.Exception.Response.StatusCode)"
    }
}

$t1 = Test-Login 'superadmin@hotelgroup.com' 'Admin123!'
$t2 = Test-Login 'admin@adora.com' 'Admin123!'
$t3 = Test-Login 'housekeeping@adora.com' 'Admin123!'

Test-FailedJobs $t1 'SuperAdmin'
Test-FailedJobs $t2 'HotelAdmin'
Test-FailedJobs $t3 'DepartmentManager'
