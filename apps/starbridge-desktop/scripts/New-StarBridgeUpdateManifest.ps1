[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')][string]$Version,
    [Parameter(Mandatory = $true)][ValidatePattern('^starbridge-desktop-v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')][string]$Tag,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9._-]+\.exe$')][string]$InstallerAssetName,
    [Parameter(Mandatory = $true)][string]$SignaturePath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$Notes = "StarBridge stability and product experience update.",
    [datetime]$PublishedAt = [datetime]::UtcNow
)

$ErrorActionPreference = "Stop"
$repository = "jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software"
$signatureFile = [IO.Path]::GetFullPath($SignaturePath)
$outputFile = [IO.Path]::GetFullPath($OutputPath)

if (-not (Test-Path -LiteralPath $signatureFile -PathType Leaf)) {
    throw "Updater signature file was not found."
}
$signature = (Get-Content -LiteralPath $signatureFile -Raw -Encoding utf8).Trim()
if ([string]::IsNullOrWhiteSpace($signature) -or $signature.Length -gt 16384) {
    throw "Updater signature is empty or unexpectedly large."
}

$encodedAssetName = [Uri]::EscapeDataString($InstallerAssetName)
$downloadUrl = "https://github.com/$repository/releases/download/$Tag/$encodedAssetName"
$manifest = [ordered]@{
    version = $Version
    notes = $Notes
    pub_date = $PublishedAt.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    platforms = [ordered]@{
        "windows-x86_64" = [ordered]@{
            signature = $signature
            url = $downloadUrl
        }
    }
}

$parent = Split-Path -Parent $outputFile
if ($parent) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$json = $manifest | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText($outputFile, $json, [Text.UTF8Encoding]::new($false))

[ordered]@{
    ok = $true
    version = $Version
    tag = $Tag
    asset = $InstallerAssetName
    manifest = [IO.Path]::GetFileName($outputFile)
    signature_embedded = $true
} | ConvertTo-Json -Compress
