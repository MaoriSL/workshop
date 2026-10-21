<#
.SYNOPSIS
    Lance un playbook de remédiation Poupal dans le conteneur ansible-runner (Windows / PowerShell).

.DESCRIPTION
    Équivalent de :
      docker compose -f infra/docker-compose.yml run --rm ansible-runner ansible-playbook playbooks/<p>.yml [options]
    Démarre le proxy filtrant du socket Docker si besoin (seule porte de l'exécuteur vers Docker)
    et construit l'image de l'exécuteur si elle n'existe pas encore.

.EXAMPLE
    .\run.ps1 verify
    .\run.ps1 restart_service -e service=api
    .\run.ps1 block_ip -e ip=203.0.113.42
    .\run.ps1 rollback -e service=api -e image_tag=previous
#>
param([string]$Playbook)
# $args : options supplémentaires transmises telles quelles à ansible-playbook (ex. -e service=api).
# (script « simple », sans [CmdletBinding()] : -e ne doit pas être confondu avec -ErrorAction)

$ErrorActionPreference = 'Stop'
$playbooks = 'deploy, restart_service, recreate_service, rollback, backup_db, restore_db, block_ip, unblock_ip, verify'
if (-not $Playbook) {
    Write-Host "Usage : .\run.ps1 <playbook> [-e variable=valeur ...]"
    Write-Host "Playbooks : $playbooks"
    exit 2
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$composeFile = Join-Path $repoRoot 'infra\docker-compose.yml'
$name = [System.IO.Path]::GetFileNameWithoutExtension($Playbook)   # accepte "verify" ou "verify.yml"

# 1. Le proxy filtrant du socket Docker doit tourner (sinon l'exécuteur ne peut rien faire)
docker compose -f $composeFile up -d docker-socket-proxy-ansible
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 2. Image de l'exécuteur : construite une seule fois, réutilisée ensuite
$image = docker compose -f $composeFile --profile tools config --images ansible-runner
docker image inspect $image *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Image $image absente : construction (une seule fois)..."
    docker compose -f $composeFile build ansible-runner
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# 3. Exécution du playbook (conteneur jetable, dépôt monté en lecture seule)
docker compose -f $composeFile run --rm -T ansible-runner ansible-playbook "playbooks/$name.yml" @args
exit $LASTEXITCODE
