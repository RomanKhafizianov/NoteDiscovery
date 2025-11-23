param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipCommit = $false
)

# Validate version format (semantic versioning)
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Host "Error: Version must be in format X.Y.Z (e.g., 0.4.0)" -ForegroundColor Red
    exit 1
}

Write-Host "Releasing version $Version..." -ForegroundColor Green

# Check if working directory is clean (unless skipping commit)
if (-not $SkipCommit) {
    $status = git status --porcelain
    if ($status) {
        Write-Host "Warning: Working directory has uncommitted changes:" -ForegroundColor Yellow
        Write-Host $status -ForegroundColor Yellow
        $response = Read-Host "Continue anyway? (y/N)"
        if ($response -ne 'y' -and $response -ne 'Y') {
            Write-Host "Aborted." -ForegroundColor Red
            exit 1
        }
    }
}

# Update VERSION file (single source of truth)
Write-Host "Updating VERSION file..." -ForegroundColor Yellow
$Version | Out-File -FilePath "VERSION" -Encoding utf8 -NoNewline

# Commit changes (unless skipped)
if (-not $SkipCommit) {
    Write-Host "Committing version changes..." -ForegroundColor Yellow
    git add VERSION
    git commit -m "Bump version to $Version"
    
    # Push commits first
    Write-Host "Pushing commits..." -ForegroundColor Yellow
    git push
}

# Create git tag
Write-Host "Creating git tag v$Version..." -ForegroundColor Yellow
git tag -a "v$Version" -m "Release version $Version"

# Push tag to remote
Write-Host "Pushing tag to remote..." -ForegroundColor Yellow
git push origin "v$Version"

Write-Host "`nRelease $Version completed successfully!" -ForegroundColor Green
Write-Host "Tag: v$Version" -ForegroundColor Cyan

