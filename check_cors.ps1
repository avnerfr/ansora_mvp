# Check CORS headers from backend
Write-Host "Checking CORS headers from backend..." -ForegroundColor Cyan
Write-Host ""

$response = Invoke-WebRequest -Uri "https://ansora-mvp.onrender.com/health" -Method GET

Write-Host "Response Status: $($response.StatusCode)" -ForegroundColor Green
Write-Host ""
Write-Host "CORS Headers:" -ForegroundColor Yellow

$corsHeaders = @(
    'Access-Control-Allow-Origin',
    'Access-Control-Allow-Methods', 
    'Access-Control-Allow-Headers',
    'Access-Control-Allow-Credentials'
)

$foundAny = $false
foreach ($header in $corsHeaders) {
    if ($response.Headers[$header]) {
        Write-Host "  $header : $($response.Headers[$header])" -ForegroundColor Green
        $foundAny = $true
    } else {
        Write-Host "  $header : NOT FOUND" -ForegroundColor Red
    }
}

if (-not $foundAny) {
    Write-Host ""
    Write-Host "NO CORS HEADERS FOUND!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible causes:" -ForegroundColor Yellow
    Write-Host "1. ALLOWED_ORIGINS not set in Render environment" -ForegroundColor White
    Write-Host "2. Backend hasn't redeployed after adding ALLOWED_ORIGINS" -ForegroundColor White
    Write-Host "3. Backend code isn't applying CORS middleware" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "CORS is configured!" -ForegroundColor Green
}

