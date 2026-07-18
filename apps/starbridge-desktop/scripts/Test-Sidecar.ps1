[CmdletBinding()]
param(
    [string]$TargetTriple,
    [int]$StartupTimeoutSeconds = 15
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($TargetTriple)) {
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) {
        $env:PROCESSOR_ARCHITEW6432
    }
    else {
        $env:PROCESSOR_ARCHITECTURE
    }
    $TargetTriple = switch ($architecture.ToUpperInvariant()) {
        "AMD64" { "x86_64-pc-windows-msvc" }
        "ARM64" { "aarch64-pc-windows-msvc" }
        "X86" { "i686-pc-windows-msvc" }
        default { throw "Could not infer the current Windows target triple. Pass -TargetTriple explicitly." }
    }
}
$desktopRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$executable = Join-Path $desktopRoot "src-tauri\binaries\starbridge-sidecar-$TargetTriple.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    $buildScript = Join-Path $PSScriptRoot "Build-Sidecar.ps1"
    & $buildScript -TargetTriple $TargetTriple
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "The staged sidecar could not be built for $TargetTriple."
    }
}

$temporaryRoot = [IO.Path]::GetFullPath(
    (Join-Path ([IO.Path]::GetTempPath()) ("StarBridge Sidecar Test " + [Guid]::NewGuid().ToString("N")))
)
$tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\") + "\"
if (-not $temporaryRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a test directory outside the system temporary directory."
}
New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null

$randomBytes = New-Object byte[] 32
$randomNumberGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomNumberGenerator.GetBytes($randomBytes)
}
finally {
    $randomNumberGenerator.Dispose()
}
$sessionCredential = -join ($randomBytes | ForEach-Object { $_.ToString("x2") })
$startInfo = [Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $executable
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.Arguments = "--desktop --parent-pid $PID"
$startInfo.EnvironmentVariables["STARBRIDGE_SESSION_TOKEN"] = $sessionCredential
$startInfo.EnvironmentVariables["STARBRIDGE_APP_DATA_DIR"] = $temporaryRoot
$codexTestHome = Join-Path $temporaryRoot "codex-home"
$startInfo.EnvironmentVariables["CODEX_HOME"] = $codexTestHome
$process = [Diagnostics.Process]::new()
$process.StartInfo = $startInfo
$parentExitChildId = $null

try {
    if (-not $process.Start()) {
        throw "The sidecar process could not be started."
    }
    $readyTask = $process.StandardOutput.ReadLineAsync()
    if (-not $readyTask.Wait([TimeSpan]::FromSeconds($StartupTimeoutSeconds))) {
        throw "The sidecar did not report ready before the startup timeout."
    }
    $readyLine = $readyTask.Result
    $readyPrefix = "STARBRIDGE_READY "
    if (-not $readyLine.StartsWith($readyPrefix, [StringComparison]::Ordinal)) {
        throw "The sidecar emitted an invalid ready line."
    }
    if ($readyLine.IndexOf($sessionCredential, [StringComparison]::Ordinal) -ge 0) {
        throw "The ready line exposed the session credential."
    }
    $ready = $readyLine.Substring($readyPrefix.Length) | ConvertFrom-Json
    if ($ready.host -ne "127.0.0.1" -or $ready.port -le 0) {
        throw "The sidecar did not bind a valid loopback address and random port."
    }

    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($ready.port)/api/health" -TimeoutSec 5
    if (-not $health.ok) {
        throw "The sidecar health check failed."
    }
    $wrongHeaders = @{ "X-StarBridge-Session" = ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")) }
    $wrongCredentialStatus = 0
    try {
        Invoke-WebRequest `
            -UseBasicParsing `
            -Uri "http://127.0.0.1:$($ready.port)/api/bootstrap" `
            -Headers $wrongHeaders `
            -TimeoutSec 5 `
            -ErrorAction Stop | Out-Null
        throw "The sidecar accepted an incorrect session credential."
    }
    catch {
        if (-not $_.Exception.Response) {
            throw
        }
        $wrongCredentialStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($wrongCredentialStatus -ne 403) {
        throw "The sidecar returned $wrongCredentialStatus instead of 403 for an incorrect credential."
    }

    $headers = @{ "X-StarBridge-Session" = $sessionCredential }
    $bootstrap = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/api/bootstrap" `
        -Headers $headers `
        -TimeoutSec 10
    if (-not $bootstrap.ok) {
        throw "The authenticated bootstrap request failed."
    }

    $connections = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/api/connections" `
        -Headers $headers `
        -TimeoutSec 10
    if (-not $connections.ok -or $connections.data.drawing_enabled) {
        throw "The packaged sidecar did not begin with a locked Codex connection."
    }
    if ($connections.data.schema_version -ne "starbridge.desktop-connections.v2") {
        throw "The packaged sidecar did not expose the creative-application pairing protocol."
    }
    if ($connections.data.applications.Count -ne 6) {
        throw "The packaged sidecar did not report all six creative-application adapters."
    }
    foreach ($application in $connections.data.applications) {
        if (-not $application.id -or -not $application.pairing_state -or -not $application.adapter_kind) {
            throw "A packaged creative-application adapter omitted its pairing metadata."
        }
    }
    $pairingCode = [string]$connections.data.codex.pairing_code
    if ($pairingCode -notmatch "^[A-Z2-9]{8}$") {
        throw "The packaged sidecar returned an invalid pairing code."
    }

    $connectorInstall = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/api/connections/codex/install" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body '{"confirm_install":true}' `
        -TimeoutSec 10
    $codexTestConfig = Join-Path $codexTestHome "config.toml"
    if (-not $connectorInstall.data.installed -or -not (Test-Path -LiteralPath $codexTestConfig -PathType Leaf)) {
        throw "The packaged sidecar did not install its managed Codex connector."
    }
    $codexTestConfigText = [IO.File]::ReadAllText($codexTestConfig)
    if (-not $codexTestConfigText.Contains("mcp_servers.starbridge-desktop") -or $codexTestConfigText.Contains($sessionCredential)) {
        throw "The managed Codex connector config was missing or exposed the desktop credential."
    }

    $mcpInfo = [Diagnostics.ProcessStartInfo]::new()
    $mcpInfo.FileName = $executable
    $mcpInfo.UseShellExecute = $false
    $mcpInfo.CreateNoWindow = $true
    $mcpInfo.RedirectStandardInput = $true
    $mcpInfo.RedirectStandardOutput = $true
    $mcpInfo.RedirectStandardError = $true
    $mcpInfo.Arguments = "--mcp"
    $mcpInfo.EnvironmentVariables["STARBRIDGE_APP_DATA_DIR"] = $temporaryRoot
    $mcpProcess = [Diagnostics.Process]::new()
    $mcpProcess.StartInfo = $mcpInfo
    if (-not $mcpProcess.Start()) {
        throw "The packaged sidecar could not start in MCP connector mode."
    }
    $pairRequest = @{
        jsonrpc = "2.0"
        id = 1
        method = "tools/call"
        params = @{
            name = "starbridge.desktop_pair"
            arguments = @{
                pairing_code = $pairingCode
                confirm_pairing = $true
                confirm_write = $true
                dry_run = $false
            }
        }
    } | ConvertTo-Json -Depth 8 -Compress
    $mcpProcess.StandardInput.WriteLine($pairRequest)
    $mcpProcess.StandardInput.Flush()
    $pairResponseLine = $mcpProcess.StandardOutput.ReadLine()
    $mcpProcess.StandardInput.Close()
    if (-not $mcpProcess.WaitForExit(10000)) {
        $mcpProcess.Kill()
        throw "The packaged MCP connector did not exit after input closed."
    }
    $pairResponse = $pairResponseLine | ConvertFrom-Json
    if (-not $pairResponse.result.structuredContent.ok) {
        throw "The packaged MCP connector did not pair the desktop session."
    }
    $connections = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/api/connections" `
        -Headers $headers `
        -TimeoutSec 10
    if (-not $connections.data.drawing_enabled) {
        throw "The desktop session stayed locked after a valid Codex MCP pairing."
    }

    $sourceFile = Join-Path $temporaryRoot "community-vector-source.png"
    $sourceBytes = [Convert]::FromBase64String(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    [IO.File]::WriteAllBytes($sourceFile, $sourceBytes)
    $selectionBody = @{ input_path = $sourceFile } | ConvertTo-Json -Compress
    $selection = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/api/vectorization/selections" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $selectionBody `
        -TimeoutSec 10
    if (-not $selection.ok -or -not $selection.data.selectionId) {
        throw "The packaged sidecar could not select a Community vector input."
    }
    if (($selection | ConvertTo-Json -Depth 12).Contains($temporaryRoot)) {
        throw "The vector selection response exposed the source path."
    }

    $jobBody = @{
        selection_id = $selection.data.selectionId
        mode = "exact"
        parameters = @{}
        confirm_run = $true
        confirm_write = $true
        confirm_export = $true
    } | ConvertTo-Json -Depth 5 -Compress
    $startedJob = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/api/vectorization/jobs" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $jobBody `
        -TimeoutSec 10
    if (-not $startedJob.ok -or -not $startedJob.data.jobId) {
        throw "The packaged sidecar did not start the Community vector job."
    }
    $jobDeadline = [DateTime]::UtcNow.AddSeconds(20)
    $completedJob = $startedJob
    while ([DateTime]::UtcNow -lt $jobDeadline) {
        $completedJob = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$($ready.port)/api/vectorization/jobs/$($startedJob.data.jobId)" `
            -Headers $headers `
            -TimeoutSec 10
        if ($completedJob.data.status -in @("completed", "failed")) {
            break
        }
        Start-Sleep -Milliseconds 100
    }
    if ($completedJob.data.status -ne "completed") {
        throw "The packaged Community vector job did not complete: $($completedJob.data.status)"
    }
    if (-not $completedJob.data.result.metrics.pixelMatch) {
        throw "The packaged exact-vector workflow did not report a pixel match."
    }
    if (($completedJob | ConvertTo-Json -Depth 12).Contains($temporaryRoot)) {
        throw "The vector job response exposed an absolute source path."
    }
    if (-not (Get-ChildItem -LiteralPath (Join-Path $temporaryRoot "data\vectorization") -Filter "vector.svg" -Recurse -File -ErrorAction SilentlyContinue)) {
        throw "The packaged Community vector workflow did not create its controlled SVG output."
    }

    Invoke-RestMethod `
        -Uri "http://127.0.0.1:$($ready.port)/api/lifecycle/shutdown" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body "{}" `
        -TimeoutSec 5 | Out-Null

    if (-not $process.WaitForExit(10000)) {
        throw "The sidecar did not exit after an authenticated shutdown request."
    }
    $stderrText = $process.StandardError.ReadToEnd()
    if ($stderrText.IndexOf($sessionCredential, [StringComparison]::Ordinal) -ge 0) {
        throw "The sidecar exposed the session credential on stderr."
    }

    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, [int]$ready.port)
    try {
        $listener.Start()
    }
    finally {
        $listener.Stop()
    }

    $probeFile = Join-Path $temporaryRoot "parent-exit-probe.json"
    $parentExitDataRoot = Join-Path $temporaryRoot "parent-exit-data"
    $parentProbeScript = @'
$ErrorActionPreference = "Stop"
$credential = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
$childInfo = [Diagnostics.ProcessStartInfo]::new()
$childInfo.FileName = $env:STARBRIDGE_TEST_EXECUTABLE
$childInfo.UseShellExecute = $false
$childInfo.CreateNoWindow = $true
$childInfo.RedirectStandardOutput = $true
$childInfo.RedirectStandardError = $true
$childInfo.Arguments = "--desktop --parent-pid $PID"
$childInfo.EnvironmentVariables["STARBRIDGE_SESSION_TOKEN"] = $credential
$childInfo.EnvironmentVariables["STARBRIDGE_APP_DATA_DIR"] = $env:STARBRIDGE_TEST_DATA_ROOT
$child = [Diagnostics.Process]::new()
$child.StartInfo = $childInfo
if (-not $child.Start()) {
    throw "Could not start child sidecar."
}
$readyPrefix = "STARBRIDGE_READY "
$readyLine = $child.StandardOutput.ReadLine()
if (-not $readyLine.StartsWith($readyPrefix, [StringComparison]::Ordinal)) {
    throw "Child sidecar did not report ready."
}
$ready = $readyLine.Substring($readyPrefix.Length) | ConvertFrom-Json
$payload = [ordered]@{ pid = $child.Id; port = $ready.port }
[IO.File]::WriteAllText(
    $env:STARBRIDGE_TEST_PROBE,
    ($payload | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)
$child.Dispose()
'@
    $encodedProbe = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($parentProbeScript))
    $parentInfo = [Diagnostics.ProcessStartInfo]::new()
    $parentInfo.FileName = (Get-Command powershell.exe -ErrorAction Stop).Source
    $parentInfo.UseShellExecute = $false
    $parentInfo.CreateNoWindow = $true
    $parentInfo.RedirectStandardOutput = $true
    $parentInfo.RedirectStandardError = $true
    $parentInfo.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encodedProbe"
    $parentInfo.EnvironmentVariables["STARBRIDGE_TEST_EXECUTABLE"] = $executable
    $parentInfo.EnvironmentVariables["STARBRIDGE_TEST_DATA_ROOT"] = $parentExitDataRoot
    $parentInfo.EnvironmentVariables["STARBRIDGE_TEST_PROBE"] = $probeFile
    $parentProcess = [Diagnostics.Process]::new()
    $parentProcess.StartInfo = $parentInfo
    try {
        if (-not $parentProcess.Start()) {
            throw "The parent-exit probe process could not be started."
        }
        if (-not $parentProcess.WaitForExit(($StartupTimeoutSeconds + 5) * 1000)) {
            $parentProcess.Kill()
            throw "The parent-exit probe did not finish before the timeout."
        }
        if ($parentProcess.ExitCode -ne 0) {
            throw "The parent-exit probe failed before reporting the child sidecar."
        }
    }
    finally {
        $parentProcess.Dispose()
    }
    if (-not (Test-Path -LiteralPath $probeFile -PathType Leaf)) {
        throw "The parent-exit probe did not produce a result."
    }
    $parentProbe = Get-Content -LiteralPath $probeFile -Raw -Encoding utf8 | ConvertFrom-Json
    $parentExitChildId = [int]$parentProbe.pid
    $parentExitPort = [int]$parentProbe.port
    $childStopped = $false
    $childDeadline = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $childDeadline) {
        if (-not (Get-Process -Id $parentExitChildId -ErrorAction SilentlyContinue)) {
            $childStopped = $true
            break
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $childStopped) {
        throw "The sidecar remained alive after its parent process exited."
    }
    $parentExitChildId = $null

    $parentExitListener = [Net.Sockets.TcpListener]::new(
        [Net.IPAddress]::Loopback,
        $parentExitPort
    )
    try {
        $parentExitListener.Start()
    }
    finally {
        $parentExitListener.Stop()
    }

    [ordered]@{
        ok = $true
        ready = $true
        loopback_only = $true
        wrong_credential_rejected = $true
        authenticated_bootstrap = $true
        community_vectorization = $true
        vector_path_redacted = $true
        graceful_shutdown = $true
        process_exited = $process.HasExited
        port_released = $true
        parent_exit_cleanup = $true
        orphan_process = $false
        credential_exposed = $false
        app_data_cleaned = $true
    } | ConvertTo-Json
}
finally {
    if ($parentExitChildId) {
        Stop-Process -Id $parentExitChildId -Force -ErrorAction SilentlyContinue
    }
    if (-not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit(5000) | Out-Null
    }
    $process.Dispose()
    if (Test-Path -LiteralPath $temporaryRoot) {
        if (-not $temporaryRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean a path outside the system temporary directory."
        }
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
