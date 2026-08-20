param(
  [string]$GraphDbBase = "http://localhost:7200",
  [string]$RepoId = "atlas",
  [string]$SeedFile = "server/sample_data/codebase_seed.ttl"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $SeedFile)) {
  throw "Seed file not found: $SeedFile"
}

$repoListUrl = "$GraphDbBase/rest/repositories"
try {
  $repoResp = Invoke-WebRequest -Uri $repoListUrl -Method Get -TimeoutSec 10
  $repos = @()
  if ($repoResp.Content) {
    $repos = $repoResp.Content | ConvertFrom-Json
  }

  $repoExists = $false
  foreach ($r in $repos) {
    if ($r.id -eq $RepoId) {
      $repoExists = $true
      break
    }
  }

  if (-not $repoExists) {
    $available = if ($repos.Count -gt 0) { ($repos | ForEach-Object { $_.id }) -join ", " } else { "(none)" }
    throw "Repository '$RepoId' does not exist in GraphDB at $GraphDbBase. Existing repos: $available. Create '$RepoId' in GraphDB Workbench first."
  }
}
catch {
  throw "Failed repository precheck against $repoListUrl. $($_.Exception.Message)"
}

$seedContent = Get-Content -Path $SeedFile -Raw -Encoding UTF8
$statementsUrl = "$GraphDbBase/repositories/$RepoId/statements"

Write-Host "Loading seed TTL into $statementsUrl ..."

$response = Invoke-WebRequest `
  -Uri $statementsUrl `
  -Method Post `
  -ContentType "text/turtle" `
  -Body $seedContent

Write-Host "Done. Status: $($response.StatusCode)"
Write-Host "Now verify:"
Write-Host "  $GraphDbBase/repositories/$RepoId"
Write-Host "  http://localhost:8000/health"
Write-Host "  http://localhost:8000/graph"
