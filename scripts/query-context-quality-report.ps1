param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$RepoUrl = "",
    [string]$JobId = "",
    [switch]$RawJson,
    [switch]$SummaryOnly
)

$ErrorActionPreference = "Stop"

function Normalize-BaseUrl {
    param([string]$Value)
    return $Value.TrimEnd("/")
}

function Show-Usage {
    Write-Host "Usage:"
    Write-Host "  Query by running a new synchronous analysis:"
    Write-Host "    .\scripts\query-context-quality-report.ps1 -RepoUrl https://github.com/owner/repo"
    Write-Host ""
    Write-Host "  Query an existing completed job snapshot:"
    Write-Host "    .\scripts\query-context-quality-report.ps1 -JobId <job-id>"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -BaseUrl http://localhost:8000"
    Write-Host "  -RawJson"
    Write-Host "  -SummaryOnly"
}

function Get-ReportFromAnalyze {
    param(
        [string]$ApiBaseUrl,
        [string]$RepositoryUrl
    )

    $body = @{
        repo_url = $RepositoryUrl
    } | ConvertTo-Json

    $result = Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBaseUrl/api/agent/analyze" `
        -ContentType "application/json" `
        -Body $body

    return $result.context_quality_report
}

function Get-ReportFromJob {
    param(
        [string]$ApiBaseUrl,
        [string]$AnalysisJobId
    )

    $snapshot = Invoke-RestMethod `
        -Method Get `
        -Uri "$ApiBaseUrl/api/agent/analyze/jobs/$AnalysisJobId"

    if ($null -eq $snapshot.result) {
        throw "Job snapshot has no final result yet. Wait for the job to complete, then retry."
    }

    return $snapshot.result.context_quality_report
}

function Write-ReportSummary {
    param($Report)

    if ($null -eq $Report) {
        throw "Response did not include context_quality_report."
    }

    Write-Host "Context quality report"
    Write-Host "----------------------"

    [PSCustomObject]@{
        candidate_file_count = $Report.candidate_file_count
        selected_file_count = $Report.selected_file_count
        omitted_candidate_count = $Report.omitted_candidate_count
        context_char_count = $Report.context_char_count
        raw_candidate_chars = $Report.raw_candidate_chars
        compression_ratio = $Report.compression_ratio
        truncated_selected_file_count = $Report.truncated_selected_file_count
        budget_limit_reached = $Report.budget_limit_reached
    } | Format-List

    if ($SummaryOnly) {
        return
    }

    Write-Host ""
    Write-Host "Selected files"
    Write-Host "--------------"
    if ($Report.selected_files.Count -gt 0) {
        $Report.selected_files | ForEach-Object { Write-Host "- $_" }
    } else {
        Write-Host "(none)"
    }

    Write-Host ""
    Write-Host "Directory coverage"
    Write-Host "------------------"
    if ($Report.directory_coverage.Count -gt 0) {
        $Report.directory_coverage |
            Select-Object directory, selected_file_count |
            Format-Table -AutoSize
    } else {
        Write-Host "(none)"
    }

    Write-Host ""
    Write-Host "Notes"
    Write-Host "-----"
    if ($Report.notes.Count -gt 0) {
        $Report.notes | ForEach-Object { Write-Host "- $_" }
    } else {
        Write-Host "(none)"
    }
}

if ([string]::IsNullOrWhiteSpace($RepoUrl) -and [string]::IsNullOrWhiteSpace($JobId)) {
    Show-Usage
    exit 1
}

if (-not [string]::IsNullOrWhiteSpace($RepoUrl) -and -not [string]::IsNullOrWhiteSpace($JobId)) {
    throw "Use either -RepoUrl or -JobId, not both."
}

$apiBaseUrl = Normalize-BaseUrl -Value $BaseUrl

if (-not [string]::IsNullOrWhiteSpace($RepoUrl)) {
    $report = Get-ReportFromAnalyze -ApiBaseUrl $apiBaseUrl -RepositoryUrl $RepoUrl
} else {
    $report = Get-ReportFromJob -ApiBaseUrl $apiBaseUrl -AnalysisJobId $JobId
}

if ($RawJson) {
    $report | ConvertTo-Json -Depth 10
} else {
    Write-ReportSummary -Report $report
}
