param(
    [string]$RepoUrl,
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Continue"
$ownerRepo = $RepoUrl -replace "https://github.com/", ""
$safeName = $ownerRepo -replace "/", "_"
$outFile = "data/bench_$safeName.json"

$body = @{ repo_url = $RepoUrl } | ConvertTo-Json

try {
    $r = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/agent/analyze" -ContentType "application/json" -Body $body -TimeoutSec 300
    $m = $r.metrics
    $e = $r.result_evaluation
    $result = [PSCustomObject]@{
        repo = $ownerRepo
        status = "success"
        total_files = $m.total_files
        ignored_dirs = $m.ignored_dirs
        candidate_core_files = $m.candidate_core_files
        selected_core_files = $m.selected_core_files
        raw_candidate_chars = $m.raw_candidate_chars
        final_context_chars = $m.final_context_chars
        context_compression_ratio = $m.context_compression_ratio
        generated_doc_count = $m.generated_doc_count
        interview_question_count = $m.interview_question_count
        agent_step_count = $m.agent_step_count
        tool_call_count = $m.tool_call_count
        analysis_duration_ms = $m.analysis_duration_ms
        llm_call_count = $m.llm_call_count
        llm_success_count = $m.llm_success_count
        llm_total_duration_ms = $m.llm_total_duration_ms
        textcitation_score = $e.textcitation_score
        coverage_score = $e.coverage_score
        hallucination_risk = $e.hallucination_risk
        usefulness_score = $e.usefulness_score
    }
    $result | ConvertTo-Json -Depth 3 | Out-File -FilePath $outFile -Encoding utf8
    $ratio = [math]::Round($m.context_compression_ratio * 100, 1)
    Write-Host "OK:$ownerRepo|dur=$($m.analysis_duration_ms)|steps=$($m.agent_step_count)|tools=$($m.tool_call_count)|compress=${ratio}%"
} catch {
    $result = [PSCustomObject]@{ repo = $ownerRepo; status = "failed"; error = $_.Exception.Message }
    $result | ConvertTo-Json -Depth 3 | Out-File -FilePath $outFile -Encoding utf8
    Write-Host "FAIL:$ownerRepo|$($_.Exception.Message)"
}