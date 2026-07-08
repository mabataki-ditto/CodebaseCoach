param(
    [string]$BaseUrl = "http://localhost:8000",
    [int]$TimeoutSec = 300
)

$ErrorActionPreference = "Continue"

$repos = @(
    "https://github.com/sindresorhus/awesome",
    "https://github.com/axios/axios",
    "https://github.com/pallets/flask",
    "https://github.com/vuejs/pinia",
    "https://github.com/prettier/prettier",
    "https://github.com/tiangolo/sqlmodel",
    "https://github.com/fastify/fastify",
    "https://github.com/pytest-dev/pytest",
    "https://github.com/python-poetry/poetry",
    "https://github.com/expressjs/express"
)

$results = @()

foreach ($repoUrl in $repos) {
    $ownerRepo = $repoUrl -replace "https://github.com/", ""
    Write-Host "========================================"
    Write-Host "Analyzing: $ownerRepo"
    Write-Host "========================================"

    $body = @{ repo_url = $repoUrl } | ConvertTo-Json

    try {
        $started = Get-Date
        $response = Invoke-RestMethod `
            -Method Post `
            -Uri "$BaseUrl/api/agent/analyze" `
            -ContentType "application/json" `
            -Body $body `
            -TimeoutSec $TimeoutSec
        $elapsed = [int]((Get-Date) - $started).TotalMilliseconds

        $metrics = $response.metrics
        $quality = $response.context_quality_report
        $eval = $response.result_evaluation

        $result = [PSCustomObject]@{
            repo                = $ownerRepo
            status              = "success"
            total_files         = $metrics.total_files
            ignored_dirs        = $metrics.ignored_dirs
            candidate_core_files = $metrics.candidate_core_files
            selected_core_files = $metrics.selected_core_files
            raw_candidate_chars = $metrics.raw_candidate_chars
            final_context_chars = $metrics.final_context_chars
            context_compression_ratio = $metrics.context_compression_ratio
            generated_doc_count = $metrics.generated_doc_count
            generated_doc_chars = $metrics.generated_doc_total_chars
            interview_questions = $metrics.interview_question_count
            agent_step_count    = $metrics.agent_step_count
            agent_success       = $metrics.agent_success_step_count
            agent_failed        = $metrics.agent_failed_step_count
            agent_skipped       = $metrics.agent_skipped_step_count
            tool_call_count     = $metrics.tool_call_count
            tool_success        = $metrics.tool_success_count
            tool_failed         = $metrics.tool_failed_count
            analysis_duration_ms = $metrics.analysis_duration_ms
            llm_call_count      = $metrics.llm_call_count
            llm_success         = $metrics.llm_success_count
            llm_failed          = $metrics.llm_failed_count
            llm_total_duration  = $metrics.llm_total_duration_ms
            textcitation_score  = $eval.textcitation_score
            coverage_score      = $eval.coverage_score
            hallucination_risk  = $eval.hallucination_risk
            usefulness_score    = $eval.usefulness_score
            wall_clock_ms       = $elapsed
        }

        Write-Host "  OK | duration=$($metrics.analysis_duration_ms)ms | steps=$($metrics.agent_step_count) | tools=$($metrics.tool_call_count) | files=$($metrics.total_files) | core=$($metrics.selected_core_files) | compress_ratio=$([math]::Round($metrics.context_compression_ratio * 100, 1))%"
    }
    catch {
        Write-Host "  FAILED: $_"
        $result = [PSCustomObject]@{
            repo   = $ownerRepo
            status = "failed"
            error  = $_.Exception.Message
        }
    }

    $results += $result
    Write-Host ""
}

# Save results
$results | ConvertTo-Json -Depth 4 | Out-File -FilePath "data/benchmark_results.json" -Encoding utf8

# Print summary
Write-Host "`n========== SUMMARY =========="
$successful = $results | Where-Object { $_.status -eq "success" }
$failed = $results | Where-Object { $_.status -ne "success" }

Write-Host "Total: $($results.Count) | Success: $($successful.Count) | Failed: $($failed.Count)"
Write-Host ""

if ($successful.Count -gt 0) {
    $avgDuration = [math]::Round(($successful | Measure-Object -Property analysis_duration_ms -Average).Average, 0)
    $avgSteps = [math]::Round(($successful | Measure-Object -Property agent_step_count -Average).Average, 1)
    $avgTools = [math]::Round(($successful | Measure-Object -Property tool_call_count -Average).Average, 1)
    $avgCompress = [math]::Round(($successful | Measure-Object -Property context_compression_ratio -Average).Average * 100, 1)
    $avgFiles = [math]::Round(($successful | Measure-Object -Property total_files -Average).Average, 0)
    $avgCore = [math]::Round(($successful | Measure-Object -Property selected_core_files -Average).Average, 1)
    $avgInterview = [math]::Round(($successful | Measure-Object -Property interview_questions -Average).Average, 1)
    $avgLLMCalls = [math]::Round(($successful | Measure-Object -Property llm_call_count -Average).Average, 1)
    $avgCitation = [math]::Round(($successful | Measure-Object -Property textcitation_score -Average).Average * 100, 1)
    $avgCoverage = [math]::Round(($successful | Measure-Object -Property coverage_score -Average).Average * 100, 1)
    $avgHallucination = [math]::Round(($successful | Measure-Object -Property hallucination_risk -Average).Average * 100, 1)
    $avgUsefulness = [math]::Round(($successful | Measure-Object -Property usefulness_score -Average).Average * 100, 1)

    Write-Host "=== AVERAGES (n=$($successful.Count)) ==="
    Write-Host "  analysis_duration_ms       : $avgDuration"
    Write-Host "  agent_step_count           : $avgSteps"
    Write-Host "  tool_call_count            : $avgTools"
    Write-Host "  context_compression_ratio  : ${avgCompress}%"
    Write-Host "  total_files                : $avgFiles"
    Write-Host "  selected_core_files        : $avgCore"
    Write-Host "  interview_question_count   : $avgInterview"
    Write-Host "  llm_call_count             : $avgLLMCalls"
    Write-Host "  textcitation_score         : ${avgCitation}%"
    Write-Host "  coverage_score             : ${avgCoverage}%"
    Write-Host "  hallucination_risk         : ${avgHallucination}%"
    Write-Host "  usefulness_score           : ${avgUsefulness}%"
}

if ($failed.Count -gt 0) {
    Write-Host "`n=== FAILED ==="
    $failed | ForEach-Object { Write-Host "  $($_.repo): $($_.error)" }
}

Write-Host "`nResults saved to: data/benchmark_results.json"