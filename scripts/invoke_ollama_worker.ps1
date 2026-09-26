param(
    [Parameter(Mandatory = $true)]
    [string]$Task,

    [string[]]$ContextFile = @(),

    [ValidateRange(1000, 30000)]
    [int]$MaxContextChars = 16000,

    [ValidateRange(128, 1200)]
    [int]$MaxOutputTokens = 700,

    [string]$Model = "gpt-oss:20b"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$repositoryPrefix = $repositoryRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$sections = [System.Collections.Generic.List[string]]::new()
$remaining = $MaxContextChars

foreach ($relativePath in $ContextFile) {
    if ($remaining -le 0) { break }
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $relativePath))
    if (-not $candidate.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Context file is outside the repository: $relativePath"
    }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Context file does not exist: $relativePath"
    }
    $content = Get-Content -Raw -LiteralPath $candidate
    $take = [Math]::Min($content.Length, $remaining)
    $sections.Add("--- $relativePath ---`n$($content.Substring(0, $take))")
    $remaining -= $take
}

$context = if ($sections.Count) { $sections -join "`n`n" } else { "No file context supplied." }
$body = @{
    model = $Model
    stream = $false
    think = "low"
    messages = @(
        @{
            role = "system"
            content = "You are a bounded local software worker. Use only the supplied context. Do not claim to have run commands or changed files. Return a concise proposal, patch, test cases, or review as requested. Identify uncertainty explicitly."
        },
        @{
            role = "user"
            content = "TASK:`n$Task`n`nCONTEXT:`n$context"
        }
    )
    options = @{
        temperature = 0
        num_ctx = 4096
        num_predict = $MaxOutputTokens
    }
} | ConvertTo-Json -Depth 8

$response = Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:11434/api/chat" `
    -ContentType "application/json" `
    -Body $body `
    -TimeoutSec 120

if (-not $response.message.content) {
    throw "Ollama returned no worker content."
}

$response.message.content
