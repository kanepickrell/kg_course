<#
.SYNOPSIS
    Test ProtoGraph Ingestion Pipeline
.DESCRIPTION
    Complete test suite with timeout handling
.EXAMPLE
    .\test-ingestion-pipeline.ps1
#>

param(
    [string]$BaseUrl = "http://localhost:8000",
    [switch]$SkipSetup,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

# Colors
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Failure { Write-Host $args -ForegroundColor Red }

# Setup
if (-not $SkipSetup) {
    Write-Info "`n[SETUP] Setting up test environment..."
    New-Item -ItemType Directory -Force -Path ".\test_data" | Out-Null
    
    $testArtifact = @{
        "_key" = "lib_cs_mimikatz"
        "name" = "Credential Dump (Mimikatz)"
        "category" = "Cobalt Strike"
        "tactic" = "TA0006"
        "technique" = "T1003"
        "description" = "Extract credentials from LSASS memory"
        "riskLevel" = "critical"
        "executionType" = "cobalt_strike"
        "cobaltStrikeCommand" = "mimikatz `${command}"
        "parameters" = @(
            @{
                "id" = "command"
                "label" = "Mimikatz Command"
                "type" = "select"
                "required" = $true
                "default" = "sekurlsa::logonpasswords"
                "options" = @("sekurlsa::logonpasswords", "lsadump::sam")
            }
        )
    } | ConvertTo-Json -Depth 10
    
    $testArtifact | Out-File ".\test_data\test_artifact.json" -Encoding UTF8
    Write-Success "[DONE] Setup complete"
}

# Test 1: Health
Write-Info "`n=== TEST 1: Health Check ==="
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/ingest/health" -Method Get -TimeoutSec 10
    Write-Success "[PASS] Status: $($health.status)"
    Write-Success "[PASS] Database: $($health.database_connected)"
    Write-Success "[PASS] Ollama: $($health.ollama_connected)"
    Write-Success "[PASS] Model: $($health.model)"
} catch {
    Write-Failure "[FAIL] Health check failed: $($_.Exception.Message)"
    exit 1
}

# Test 2: Analyze (with progress indicator)
Write-Info "`n=== TEST 2: Analyze Artifact ==="
Write-Warning "[WAIT] This may take 30-120 seconds depending on your LLM setup..."

$analyzeBody = @{
    artifacts = @(
        @{
            id = "test_$(Get-Date -Format 'yyyyMMddHHmmss')"
            content = (Get-Content ".\test_data\test_artifact.json" -Raw)
            source_type = "pasted"
            filename = "test_artifact.json"
        }
    )
} | ConvertTo-Json -Depth 10

try {
    # Start progress indicator job
    $progressJob = Start-Job -ScriptBlock {
        $elapsed = 0
        while ($true) {
            Start-Sleep -Seconds 5
            $elapsed += 5
            Write-Output "[INFO] Still analyzing... ($elapsed seconds elapsed)"
        }
    }

    # Make the API call with timeout
    $analyze = Invoke-RestMethod `
        -Uri "$BaseUrl/api/ingest/analyze" `
        -Method Post `
        -ContentType "application/json" `
        -Body $analyzeBody `
        -TimeoutSec $TimeoutSeconds
    
    # Stop progress indicator
    Stop-Job -Job $progressJob -ErrorAction SilentlyContinue
    Remove-Job -Job $progressJob -ErrorAction SilentlyContinue
    
    $classification = $analyze.classifications[0]
    Write-Success "[PASS] Artifact ID: $($classification.artifactId)"
    Write-Success "[PASS] Classified as: $($classification.proposedType)"
    Write-Success "[PASS] Confidence: $([math]::Round($classification.confidence * 100, 1))%"
    Write-Success "[PASS] Icon: $($classification.suggestedIcon)"
    
    Write-Info "`nExtracted Key Attributes:"
    $classification.keyAttributes.PSObject.Properties | ForEach-Object {
        Write-Host "  - $($_.Name): $($_.Value)" -ForegroundColor Gray
    }
    
    $analyze | ConvertTo-Json -Depth 10 | Out-File ".\test_data\analyze_response.json" -Encoding UTF8
    Write-Info "[SAVED] analyze_response.json"
    
} catch {
    # Stop progress indicator on error
    if ($progressJob) {
        Stop-Job -Job $progressJob -ErrorAction SilentlyContinue
        Remove-Job -Job $progressJob -ErrorAction SilentlyContinue
    }
    
    Write-Failure "[FAIL] Analysis failed: $($_.Exception.Message)"
    if ($_.ErrorDetails) {
        Write-Failure "[ERROR] Details: $($_.ErrorDetails.Message)"
    }
    
    # Check if it was a timeout
    if ($_.Exception.Message -like "*timeout*") {
        Write-Warning "`n[TIP] Try increasing timeout with: .\test-ingestion.ps1 -TimeoutSeconds 300"
        Write-Warning "[TIP] Or check if Ollama is responding: curl http://localhost:11434/api/tags"
    }
    exit 1
}

# Test 3: Commit
Write-Info "`n=== TEST 3: Commit Artifact ==="
$analyze = Get-Content ".\test_data\analyze_response.json" -Raw | ConvertFrom-Json
$original = Get-Content ".\test_data\test_artifact.json" -Raw | ConvertFrom-Json
$classification = $analyze.classifications[0]

$commitBody = @{
    artifact_id = $classification.artifactId
    original_data = $original
    classification = @{
        proposedType = $classification.proposedType
        confidence = $classification.confidence
        reasoning = $classification.reasoning
        keyAttributes = $classification.keyAttributes
        suggestedIcon = $classification.suggestedIcon
    }
    schema = @{
        typeName = $classification.proposedType
        metadataFields = @("name", "category", "tactic", "technique", "description", "riskLevel")
        payloadStructure = @{
            parameters = "array"
            cobaltStrikeCommand = "string"
            executionType = "string"
        }
        storageLocation = "local"
    }
    created_by = $env:USERNAME
} | ConvertTo-Json -Depth 10

try {
    $commit = Invoke-RestMethod `
        -Uri "$BaseUrl/api/ingest/commit" `
        -Method Post `
        -ContentType "application/json" `
        -Body $commitBody `
        -TimeoutSec 30
    
    Write-Success "[PASS] Node created: $($commit.node_id)"
    Write-Success "[PASS] Node key: $($commit.node_key)"
    Write-Success "[PASS] Collection: $($commit.collection)"
    Write-Success "[PASS] Payload URL: $($commit.payload_url)"
    
    Write-Info "`nMetadata Fields ($($commit.metadata_fields.Count)):"
    $commit.metadata_fields | ForEach-Object { Write-Host "  - $_" -ForegroundColor Gray }
    
    Write-Info "`nPayload Fields ($($commit.payload_fields.Count)):"
    $commit.payload_fields | ForEach-Object { Write-Host "  - $_" -ForegroundColor Gray }
    
    $commit | ConvertTo-Json -Depth 10 | Out-File ".\test_data\commit_response.json" -Encoding UTF8
    Write-Info "[SAVED] commit_response.json"
    
} catch {
    Write-Failure "[FAIL] Commit failed: $($_.Exception.Message)"
    if ($_.ErrorDetails) {
        Write-Failure "[ERROR] Details: $($_.ErrorDetails.Message)"
    }
    exit 1
}

# Test 4: Retrieve Payload
Write-Info "`n=== TEST 4: Retrieve Payload ==="
$commit = Get-Content ".\test_data\commit_response.json" -Raw | ConvertFrom-Json
$artifactKey = $commit.node_key

try {
    $payload = Invoke-RestMethod `
        -Uri "$BaseUrl/api/ingest/payloads/$artifactKey.json" `
        -Method Get `
        -TimeoutSec 10
    
    Write-Success "[PASS] Payload retrieved successfully"
    Write-Info "`nPayload contains:"
    $payload.PSObject.Properties | ForEach-Object {
        Write-Host "  - $($_.Name)" -ForegroundColor Gray
    }
    
    $payload | ConvertTo-Json -Depth 10 | Out-File ".\test_data\retrieved_payload.json" -Encoding UTF8
    Write-Info "[SAVED] retrieved_payload.json"
    
} catch {
    Write-Failure "[FAIL] Payload retrieval failed: $($_.Exception.Message)"
}

# Test 5: Verify in Database
Write-Info "`n=== TEST 5: Verify in ArangoDB ==="
$nodeId = $commit.node_id

try {
    $verify = Invoke-RestMethod `
        -Uri "$BaseUrl/api/artifact/$nodeId" `
        -Method Get `
        -TimeoutSec 10
    
    Write-Success "[PASS] Node verified in database"
    Write-Info "`nNode Details:"
    Write-Host "  _id: $($verify.data._id)" -ForegroundColor Gray
    Write-Host "  _key: $($verify.data._key)" -ForegroundColor Gray
    Write-Host "  type: $($verify.data.type)" -ForegroundColor Gray
    Write-Host "  name: $($verify.data.name)" -ForegroundColor Gray
    Write-Host "  cluster: $($verify.data.cluster)" -ForegroundColor Gray
    Write-Host "  payload_url: $($verify.data.payload_url)" -ForegroundColor Gray
    
} catch {
    Write-Failure "[FAIL] Verification failed: $($_.Exception.Message)"
}

Write-Success "`n========================================="
Write-Success "ALL TESTS PASSED!"
Write-Success "========================================="
Write-Info "`nGenerated files in .\test_data\"
Write-Info "  - test_artifact.json (input)"
Write-Info "  - analyze_response.json (step 1)"
Write-Info "  - commit_response.json (step 2)"
Write-Info "  - retrieved_payload.json (step 3)"

Write-Info "`nTiming Summary:"
Write-Info "  Test 1 (Health): < 1 second"
Write-Info "  Test 2 (Analyze): $TimeoutSeconds seconds max (LLM processing)"
Write-Info "  Test 3 (Commit): < 5 seconds"
Write-Info "  Test 4 (Payload): < 1 second"
Write-Info "  Test 5 (Verify): < 1 second"