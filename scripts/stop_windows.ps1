$ContainerName = "finally"

$containerExists = docker container inspect $ContainerName 2>$null
if ($containerExists) {
    docker stop $ContainerName
    docker rm $ContainerName
    Write-Host "FinAlly stopped."
} else {
    Write-Host "FinAlly is not running."
}
