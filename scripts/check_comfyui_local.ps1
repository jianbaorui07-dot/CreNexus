param(
    [string]$Url = $env:STARBRIDGE_COMFYUI_URL
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Url)) {
    $Url = "http://127.0.0.1:8188"
}

Write-Output "StarBridge ComfyUI local check"
Write-Output "URL: $Url"
Write-Output "Mode: read-only"

try {
    $uri = [System.Uri]$Url
} catch {
    Write-Output "Status: invalid-url"
    Write-Output "Message: STARBRIDGE_COMFYUI_URL is not a valid URI."
    exit 1
}

$port = $uri.Port
if ($port -lt 0) {
    if ($uri.Scheme -eq "https") { $port = 443 } else { $port = 80 }
}

$client = [System.Net.Sockets.TcpClient]::new()
try {
    $async = $client.BeginConnect($uri.Host, $port, $null, $null)
    $connected = $async.AsyncWaitHandle.WaitOne(1500, $false)
    if ($connected) {
        $client.EndConnect($async)
        Write-Output "Port: reachable"
    } else {
        Write-Output "Port: not reachable"
        Write-Output "Next: start ComfyUI or set STARBRIDGE_COMFYUI_URL."
        exit 0
    }
} catch {
    Write-Output "Port: not reachable"
    Write-Output "Error: $($_.Exception.Message)"
    Write-Output "Next: start ComfyUI or set STARBRIDGE_COMFYUI_URL."
    exit 0
} finally {
    $client.Close()
}

$statsUrl = ($Url.TrimEnd("/") + "/system_stats")
try {
    $response = Invoke-WebRequest -Uri $statsUrl -UseBasicParsing -TimeoutSec 3 -Method Get
    Write-Output "Endpoint: /system_stats"
    Write-Output "HTTP: $($response.StatusCode)"
    Write-Output "Result: ComfyUI appears reachable."
} catch {
    Write-Output "Endpoint: /system_stats"
    Write-Output "Result: port reachable but status endpoint failed."
    Write-Output "Error: $($_.Exception.Message)"
}
