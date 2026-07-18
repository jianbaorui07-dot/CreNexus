[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$SignaturePath,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][string]$ExpectedTag,
    [Parameter(Mandatory = $true)][string]$ExpectedSignerSubject
)

$ErrorActionPreference = "Stop"
$repository = "jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software"
$installer = Get-Item -LiteralPath $InstallerPath -ErrorAction Stop
$signatureFile = Get-Item -LiteralPath $SignaturePath -ErrorAction Stop
$manifestFile = Get-Item -LiteralPath $ManifestPath -ErrorAction Stop

$authenticode = Get-AuthenticodeSignature -LiteralPath $installer.FullName
if ($authenticode.Status -ne "Valid") {
    throw "Installer Authenticode status is $($authenticode.Status), not Valid."
}
if (-not $authenticode.SignerCertificate -or
    $authenticode.SignerCertificate.Subject -notlike "*$ExpectedSignerSubject*") {
    throw "Installer signer subject does not match the approved publishing identity."
}
if (-not $authenticode.TimeStamperCertificate) {
    throw "Installer does not contain a trusted timestamp countersignature."
}

$signature = (Get-Content -LiteralPath $signatureFile.FullName -Raw -Encoding utf8).Trim()
if ([string]::IsNullOrWhiteSpace($signature) -or $signature.Length -gt 16384) {
    throw "Updater signature is empty or unexpectedly large."
}

$manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw -Encoding utf8 | ConvertFrom-Json
if ($manifest.version -ne $ExpectedVersion) {
    throw "Update manifest version does not match the release version."
}
$platform = $manifest.platforms.'windows-x86_64'
if (-not $platform -or $platform.signature -ne $signature) {
    throw "Update manifest does not embed the generated Windows signature."
}
$downloadUri = [Uri]$platform.url
$expectedPath = "/$repository/releases/download/$ExpectedTag/$([Uri]::EscapeDataString($installer.Name))"
if ($downloadUri.Scheme -ne "https" -or
    $downloadUri.Host -ne "github.com" -or
    $downloadUri.AbsolutePath -ne $expectedPath -or
    $downloadUri.Query -or
    $downloadUri.Fragment) {
    throw "Update manifest download URL is outside the approved GitHub release path."
}

$hash = Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256
[ordered]@{
    ok = $true
    installer = $installer.Name
    sha256 = $hash.Hash
    authenticode = $authenticode.Status.ToString()
    signer_subject = $authenticode.SignerCertificate.Subject
    timestamped = $true
    updater_signature_embedded = $true
    update_endpoint_host = $downloadUri.Host
} | ConvertTo-Json -Depth 4
