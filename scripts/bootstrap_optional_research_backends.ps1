$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot '..'
$vendor = Join-Path $root 'vendor\optional-research'
New-Item -ItemType Directory -Force -Path $vendor | Out-Null
$repos = @(
  @{ Name = 'qiskit-machine-learning'; Url = 'https://github.com/qiskit-community/qiskit-machine-learning.git' },
  @{ Name = 'lava'; Url = 'https://github.com/lava-nc/lava.git' }
)
foreach ($repo in $repos) {
  $dest = Join-Path $vendor $repo.Name
  if (-not (Test-Path $dest)) { git clone $repo.Url $dest }
}
Write-Host 'Optional research backends cloned under vendor/optional-research.'
Write-Host 'They are never imported by the default runtime; adapters remain optional.'
