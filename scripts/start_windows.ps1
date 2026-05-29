$ErrorActionPreference = "Stop"
$ContainerName = "finally"
$ImageName = "finally"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Create db directory if it doesn't exist
New-Item -ItemType Directory -Force -Path "$ProjectRoot\db" | Out-Null

# Check .env exists
if (-not (Test-Path "$ProjectRoot\.env")) {
    Write-Error "ERROR: .env file not found. Copy .env.example to .env and fill in your API key."
    exit 1
}

# Build image if --build flag passed or image doesn't exist
$imageExists = docker image inspect $ImageName 2>$null
if ($args -contains "--build" -or -not $imageExists) {
    Write-Host "Building Docker image..."
    docker build -t $ImageName $ProjectRoot
}

# Stop and remove existing container if present
$containerExists = docker container inspect $ContainerName 2>$null
if ($containerExists) {
    Write-Host "Stopping existing container..."
    docker stop $ContainerName
    docker rm $ContainerName
}

# Start container
Write-Host "Starting FinAlly..."
docker run -d `
    --name $ContainerName `
    -p 8000:8000 `
    -v "${ProjectRoot}\db:/app/db" `
    --env-file "$ProjectRoot\.env" `
    $ImageName

Write-Host "FinAlly is running at http://localhost:8000"
Start-Process "http://localhost:8000"
