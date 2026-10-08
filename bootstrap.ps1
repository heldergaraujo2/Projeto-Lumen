<#
.SYNOPSIS
    Bootstrap da LUMEN no Windows: prepara o ambiente, confere o Unreal e sobe
    o servidor MCP.

.DESCRIPTION
    Executa, em ordem, os passos 1-11 descritos em TESTE_LOCAL.md:

      1. verifica Python 3.10+
      2. clona o repositório (se necessário) ou faz git pull
      3. cria/ativa o virtualenv (.venv)
      4. pip install -r requirements.txt
      5. roda o pytest e reporta a contagem
      6. verifica o arquivo .uproject passado em -UnrealProjectPath
      7. verifica se RemoteControlAPI e PythonScriptPlugin estão habilitados
      8. inicia o Unreal Editor (se -LaunchUnreal)
      9. aguarda e faz HTTP GET na porta da Remote Control API
     10. inicia o servidor MCP
     11. imprime o resumo final

    Não assume caminho fixo nenhum: tudo é descoberto ou perguntado.

.NOTES
    Escrito para PowerShell 5.1 (o que já vem no Windows 10/11).
    NAO VALIDADO EM WINDOWS REAL: este script foi escrito sem acesso a um
    Windows/Unreal neste ambiente de desenvolvimento. Ele foi feito para
    falhar de forma visivel e explicada (try/catch em cada etapa, mensagem
    de erro com o motivo), nunca em silencio. Ver TESTE_LOCAL.md §6.

.EXAMPLE
    .\bootstrap.ps1 -UnrealProjectPath "C:\MeuProjeto\MeuProjeto.uproject" -LaunchUnreal

.EXAMPLE
    .\bootstrap.ps1 -UnrealProjectPath "C:\MeuProjeto\MeuProjeto.uproject" -AllowWrite -SkipTests
#>
[CmdletBinding()]
param(
    # Caminho do arquivo .uproject do seu projeto Unreal.
    [string]$UnrealProjectPath,

    # Abre o Unreal Editor automaticamente.
    [switch]$LaunchUnreal,

    # Pula a suíte de testes (bootstrap mais rápido).
    [switch]$SkipTests,

    # Inicia o servidor MCP com escrita habilitada (default: somente leitura).
    [switch]$AllowWrite,

    # Caminho do executável do Unreal Editor, se você quiser forçar um.
    [string]$UnrealEditorPath,

    # Porta da Remote Control API (default 30010).
    [int]$RemoteControlPort = 30010,

    # Autoriza pastas extras para o agente (além da pasta do .uproject).
    [string[]]$Workspace,

    # Não sobe o servidor MCP ao final (útil para só preparar o ambiente).
    [switch]$NoMcpServer
)

$ErrorActionPreference = 'Stop'
# Set-StrictMode foi propositalmente NAO usado: a versao 'Latest' transforma
# o acesso a uma propriedade inexistente em erro, e .uproject de terceiros
# varia bastante (nem todo projeto tem "Plugins", por exemplo). A validacao
# aqui e explicita, com mensagem propria em cada caso.

# ============================================================== utilidades
$Script:RepoRoot = $PSScriptRoot
$Script:StepLog = New-Object System.Collections.ArrayList
$Script:CurrentStep = 0
$Script:CurrentStepName = ''

function Write-Header([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkGray
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor DarkGray
}

function Start-Step([string]$Name) {
    $Script:CurrentStep++
    $Script:CurrentStepName = $Name
    Write-Host ''
    Write-Host ("[{0}] {1}" -f $Script:CurrentStep, $Name) -ForegroundColor White
}

function Write-Ok([string]$Message)   { Write-Host "    OK  $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "    AVISO  $Message" -ForegroundColor Yellow }
function Write-Info([string]$Message) { Write-Host "    ...  $Message" -ForegroundColor Gray }

function Complete-Step([string]$Detail = '') {
    [void]$Script:StepLog.Add([pscustomobject]@{
        Number = $Script:CurrentStep
        Name   = $Script:CurrentStepName
        Detail = $Detail
    })
}

function Stop-WithFailure([string]$Reason, [string]$HowToFix = '') {
    Write-Host ''
    Write-Host ('-' * 72) -ForegroundColor DarkGray
    Write-Host "  FALHOU NA ETAPA $Script:CurrentStep, MOTIVO:" -ForegroundColor Red
    Write-Host "  $Reason" -ForegroundColor Red
    if ($HowToFix) {
        Write-Host ''
        Write-Host "  COMO RESOLVER:" -ForegroundColor Yellow
        foreach ($line in ($HowToFix -split "`n")) {
            Write-Host "    $line" -ForegroundColor Yellow
        }
    }
    Write-Host ''
    if ($Script:StepLog.Count -gt 0) {
        Write-Host '  Etapas concluidas antes da falha:' -ForegroundColor DarkGray
        foreach ($step in $Script:StepLog) {
            Write-Host ("    [OK] {0}. {1}" -f $step.Number, $step.Name) -ForegroundColor DarkGray
        }
    }
    Write-Host ('-' * 72) -ForegroundColor DarkGray
    Write-Host ''
    Write-Host '  ❌ Falhou.' -ForegroundColor Red
    Write-Host ''
    exit 1
}

function Test-CommandExists([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# =========================================================== 1. Python 3.10+
function Get-PythonCommand {
    <#
      Descobre um interpretador Python >= 3.10.
      Tenta, em ordem: py -3, python, python3. Não assume caminho fixo.
    #>
    $candidates = @()
    if (Test-CommandExists 'py') {
        $candidates += ,@('py', @('-3'))
    }
    if (Test-CommandExists 'python') { $candidates += ,@('python', @()) }
    if (Test-CommandExists 'python3') { $candidates += ,@('python3', @()) }

    foreach ($candidate in $candidates) {
        $exe  = $candidate[0]
        $base = $candidate[1]
        try {
            $raw = & $exe @base -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $raw) { continue }
            $version = [version]($raw.Trim())
            if ($version -ge [version]'3.10.0') {
                return [pscustomobject]@{ Exe = $exe; BaseArgs = $base; Version = $version }
            }
            Write-Info "$exe tem Python $version (precisa 3.10+); tentando o proximo."
        } catch {
            continue
        }
    }
    return $null
}

function Step-1-Python {
    Start-Step 'Verificando Python 3.10+'
    $python = Get-PythonCommand
    if (-not $python) {
        Stop-WithFailure 'Nenhum Python 3.10+ encontrado no PATH.' @'
Instale o Python 3.10 ou superior:
  https://www.python.org/downloads/windows/

Na instalacao, MARQUE a opcao "Add python.exe to PATH".
Depois feche e reabra o PowerShell e rode este script de novo.
'@
    }
    Write-Ok "Python $($python.Version) encontrado ($($python.Exe))."
    Complete-Step "Python $($python.Version)"
    return $python
}

# ========================================================== 2. repositório
function Step-2-Repository {
    Start-Step 'Verificando o repositorio'

    if (-not (Test-Path (Join-Path $Script:RepoRoot 'main.py'))) {
        Stop-WithFailure "Nao encontrei main.py em '$Script:RepoRoot'." @'
Este script deve ser executado de dentro do repositorio clonado:

  git clone https://github.com/heldergaraujo2/Projeto-Lumen.git
  cd Projeto-Lumen
  .\bootstrap.ps1 -UnrealProjectPath "C:\MeuProjeto\MeuProjeto.uproject"
'@
    }

    if (Test-CommandExists 'git') {
        if (Test-Path (Join-Path $Script:RepoRoot '.git')) {
            Write-Info 'Fazendo git pull (se houver remoto configurado)...'
            try {
                $branch = (& git -C $Script:RepoRoot rev-parse --abbrev-ref HEAD 2>$null)
                $pull = (& git -C $Script:RepoRoot pull --ff-only 2>&1)
                if ($LASTEXITCODE -eq 0) {
                    Write-Ok "Repositorio atualizado (branch $branch)."
                } else {
                    Write-Warn2 "git pull nao aplicou: $pull"
                    Write-Warn2 'Continuando com o codigo local (sem sobrescrever nada).'
                }
            } catch {
                Write-Warn2 "git pull falhou: $($_.Exception.Message)"
            }
        } else {
            Write-Warn2 'Nao ha .git aqui; tratando como copia local do codigo.'
        }
    } else {
        Write-Warn2 'git nao encontrado no PATH; pulando atualizacao.'
    }

    Complete-Step 'Codigo presente'
}

# ============================================================ 3. virtualenv
function Step-3-Virtualenv($python) {
    Start-Step 'Criando/ativando o virtualenv (.venv)'
    $venvPath = Join-Path $Script:RepoRoot '.venv'
    $venvPython = Join-Path $venvPath 'Scripts\python.exe'

    if (Test-Path $venvPython) {
        Write-Ok "Virtualenv ja existe: $venvPath"
    } else {
        Write-Info "Criando virtualenv em $venvPath ..."
        # Out-Null e obrigatorio: qualquer byte no stdout do `python -m venv`
        # entraria no valor de retorno desta funcao e contaminaria $venvPython.
        & $python.Exe @($python.BaseArgs) -m venv $venvPath | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
            Stop-WithFailure 'Falha ao criar o virtualenv.' @'
Tente manualmente para ver o erro completo:

  python -m venv .venv

Se falhar, confirme que o modulo venv esta instalado
(no Debian/Ubuntu seria python3-venv; no Windows ele vem junto).
'@
        }
        Write-Ok 'Virtualenv criado.'
    }

    Complete-Step $venvPath
    return $venvPython
}

# ========================================================= dependências
function Step-4-Dependencies([string]$venvPython) {
    Start-Step 'Instalando dependencias (pip install -r requirements.txt)'
    $requirements = Join-Path $Script:RepoRoot 'requirements.txt'
    if (-not (Test-Path $requirements)) {
        Stop-WithFailure "requirements.txt nao encontrado em '$Script:RepoRoot'." `
            'Confirme que voce esta rodando dentro do repositorio clonado.'
    }

    Write-Info 'Atualizando pip...'
    & $venvPython -m pip install --upgrade pip --quiet 2>&1 |
        ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    if ($LASTEXITCODE -ne 0) { Write-Warn2 'Nao foi possivel atualizar o pip; seguindo.' }

    Write-Info 'Instalando requisitos...'
    & $venvPython -m pip install -r $requirements 2>&1 |
        ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    if ($LASTEXITCODE -ne 0) {
        Stop-WithFailure 'pip install falhou.' @'
Rode manualmente para ver o erro completo:

  .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Erros comuns:
  - sem internet / proxy bloqueando o PyPI;
  - Python de 32 bits (instale a versao 64 bits).
'@
    }
    Write-Ok 'Dependencias instaladas.'
    Complete-Step 'pip install concluido'
}

# ================================================================ 5. testes
function Step-5-Tests([string]$venvPython) {
    Start-Step 'Rodando a suite de testes (pytest)'

    if ($SkipTests) {
        Write-Warn2 'Pulado por -SkipTests.'
        Complete-Step 'pulado'
        return
    }

    Push-Location $Script:RepoRoot
    try {
        $output = & $venvPython -m pytest -q --no-header 2>&1
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    $summaryLine = ($output | Select-Object -Last 1)
    if ($code -eq 0) {
        Write-Ok "Testes passaram: $summaryLine"
        Complete-Step "$summaryLine"
    } else {
        Write-Host $output -ForegroundColor DarkGray
        Stop-WithFailure "A suite de testes falhou (codigo $code)." @'
Rode manualmente para ver as falhas:

  .\.venv\Scripts\python.exe -m pytest -q

Se as falhas forem de tkinter, e porque o Python foi instalado sem suporte a
Tk. Reinstale o Python marcando "tcl/tk and IDLE" no instalador.
'@
    }
}

# ============================================================ 6. .uproject
function Step-6-Uproject {
    Start-Step 'Verificando o projeto Unreal (.uproject)'

    if (-not $UnrealProjectPath) {
        Write-Warn2 'O parametro -UnrealProjectPath nao foi informado.'
        $answer = Read-Host '    Caminho do arquivo .uproject (Enter para pular)'
        if ($answer -and $answer.Trim()) {
            $UnrealProjectPath = $answer.Trim().Trim('"')
        }
    }

    if (-not $UnrealProjectPath) {
        Write-Warn2 'Sem .uproject informado: as etapas 6-9 serao puladas.'
        Complete-Step 'pulado'
        return $null
    }

    if (-not (Test-Path $UnrealProjectPath)) {
        Stop-WithFailure "O arquivo nao existe: '$UnrealProjectPath'" @'
Passe o caminho COMPLETO do arquivo .uproject (nao a pasta), por exemplo:

  .\bootstrap.ps1 -UnrealProjectPath "C:\MeuProjeto\MeuProjeto.uproject"

No Explorer: clique com o botao direito no .uproject -> Copiar como caminho,
e cole entre aspas.
'@
    }

    if ([System.IO.Path]::GetExtension($UnrealProjectPath) -ne '.uproject') {
        Stop-WithFailure "O arquivo nao tem extensao .uproject: '$UnrealProjectPath'" `
            'Aponte para o arquivo .uproject do seu projeto Unreal.'
    }

    Write-Ok "Projeto encontrado: $UnrealProjectPath"
    Complete-Step $UnrealProjectPath
    return (Resolve-Path $UnrealProjectPath).Path
}

# ======================================================= 7. plugins do UE
function Step-7-Plugins([string]$uprojectPath) {
    Start-Step 'Verificando os plugins do Unreal (Remote Control API / Python)'

    if (-not $uprojectPath) {
        Write-Warn2 'Pulado (sem .uproject).'
        Complete-Step 'pulado'
        return
    }

    $rawContent = Get-Content -Raw -LiteralPath $uprojectPath -ErrorAction SilentlyContinue
    if (-not $rawContent -or -not $rawContent.Trim()) {
        Stop-WithFailure "O .uproject esta vazio: '$uprojectPath'" `
            'Confirme que voce apontou para o arquivo .uproject correto.'
    }
    try {
        $json = $rawContent | ConvertFrom-Json
    } catch {
        Stop-WithFailure "Nao consegui ler o .uproject como JSON: $($_.Exception.Message)" @'
O .uproject e um arquivo JSON. Se ele estiver corrompido, abra-o no editor de
texto e confira a sintaxe (virgulas, chaves e colchetes).
'@
    }

    $enabled = @()
    $pluginsProperty = $json.PSObject.Properties | Where-Object { $_.Name -eq 'Plugins' }
    if ($pluginsProperty -and $pluginsProperty.Value) {
        foreach ($plugin in @($pluginsProperty.Value)) {
            $nameProperty = $plugin.PSObject.Properties | Where-Object { $_.Name -eq 'Name' }
            $enabledProperty = $plugin.PSObject.Properties | Where-Object { $_.Name -eq 'Enabled' }
            if ($enabledProperty -and $enabledProperty.Value -eq $true -and $nameProperty) {
                $enabled += [string]$nameProperty.Value
            }
        }
    }

    # Nome real no .uproject e 'RemoteControlAPI'; o rotulo no editor e
    # 'Remote Control API'. Aceitamos as variacoes para nao dar falso
    # negativo em projetos que usam outra grafia.
    $hasRemoteControl = $false
    $hasPython = $false
    foreach ($name in $enabled) {
        if ($name -match 'RemoteControl' -and $name -notmatch 'Python') { $hasRemoteControl = $true }
        if ($name -match 'PythonScriptPlugin|PythonEditorScript') { $hasPython = $true }
    }

    if ($hasRemoteControl) {
        Write-Ok 'Plugin "Remote Control API" esta habilitado.'
    } else {
        Write-Warn2 'Plugin "Remote Control API" NAO esta habilitado no .uproject.'
    }
    if ($hasPython) {
        Write-Ok 'Plugin "Python Editor Script Plugin" esta habilitado.'
    } else {
        Write-Warn2 'Plugin "Python Editor Script Plugin" NAO esta habilitado no .uproject.'
    }

    if (-not $hasRemoteControl -or -not $hasPython) {
        Write-Host ''
        Write-Host '    COMO HABILITAR (escolha um caminho):' -ForegroundColor Yellow
        Write-Host '    A) Pelo editor: Edit > Plugins > procure e marque Enabled,' -ForegroundColor Yellow
        Write-Host '       depois REINICIE o editor.' -ForegroundColor Yellow
        Write-Host '    B) Editando o .uproject, adicione dentro de "Plugins":' -ForegroundColor Yellow
        Write-Host ''
        Write-Host '         { "Name": "RemoteControlAPI",   "Enabled": true },' -ForegroundColor Yellow
        Write-Host '         { "Name": "PythonScriptPlugin", "Enabled": true }' -ForegroundColor Yellow
        Write-Host ''
        Write-Host '    O "Python Editor Script Plugin" e OBRIGATORIO para criar' -ForegroundColor Yellow
        Write-Host '    Blueprints: a Remote Control API nao tem rota para criar' -ForegroundColor Yellow
        Write-Host '    assets. Detalhes em TESTE_LOCAL.md secao 7.' -ForegroundColor Yellow
        Write-Host ''
        Write-Host '    Ha ainda UM SEGUNDO portao, em Config\DefaultRemoteControl.ini:' -ForegroundColor Yellow
        Write-Host '    bEnableRemotePythonExecution=True e a entrada em' -ForegroundColor Yellow
        Write-Host '    +CustomAllowedRemoteFunctionCalls para PythonScriptLibrary.' -ForegroundColor Yellow
        Write-Host '    (Tambem exige reiniciar o editor. Ver TESTE_LOCAL.md 1.3.)' -ForegroundColor Yellow
    }

    Complete-Step ("RemoteControl={0} Python={1}" -f $hasRemoteControl, $hasPython)
}

# ======================================================== 8. abrir o editor
function Find-UnrealEditor([string]$EngineAssociation) {
    <#
      Descobre o UnrealEditor.exe sem assumir caminho fixo:
      1) o caminho explicito em -UnrealEditorPath;
      2) o registro do Launcher da Epic para a versao do projeto;
      3) as pastas de instalacao padrao do Launcher.
    #>
    if ($UnrealEditorPath) {
        if (Test-Path $UnrealEditorPath) { return (Resolve-Path $UnrealEditorPath).Path }
        Write-Warn2 "O -UnrealEditorPath informado nao existe: $UnrealEditorPath"
    }

    $engineDirs = @()

    # (2) registro do Epic Games Launcher
    $regRoot = 'HKLM:\SOFTWARE\EpicGames\Unreal Engine'
    if (Test-Path $regRoot) {
        foreach ($key in (Get-ChildItem $regRoot -ErrorAction SilentlyContinue)) {
            try {
                $props = Get-ItemProperty -Path $key.PSPath -ErrorAction Stop
                if ($props.InstalledDirectory) { $engineDirs += [string]$props.InstalledDirectory }
            } catch { continue }
        }
    }

    # (3) pastas padrao
    foreach ($drive in @('C:', 'D:', 'E:')) {
        $base = "$drive\Program Files\Epic Games"
        if (Test-Path $base) {
            foreach ($dir in (Get-ChildItem $base -Directory -ErrorAction SilentlyContinue)) {
                if ($dir.Name -like 'UE_*') { $engineDirs += $dir.FullName }
            }
        }
    }

    foreach ($engine in $engineDirs) {
        $candidate = Join-Path $engine 'Engine\Binaries\Win64\UnrealEditor.exe'
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Step-8-LaunchUnreal([string]$uprojectPath) {
    Start-Step 'Iniciando o Unreal Editor'

    if (-not $LaunchUnreal) {
        Write-Info 'Pulado (use -LaunchUnreal para abrir o editor).'
        Complete-Step 'pulado'
        return $false
    }
    if (-not $uprojectPath) {
        Write-Warn2 'Sem .uproject: nao ha o que abrir.'
        Complete-Step 'pulado'
        return $false
    }

    $editor = Find-UnrealEditor
    if (-not $editor) {
        Write-Warn2 'Nao encontrei o UnrealEditor.exe automaticamente.'
        $answer = Read-Host '    Caminho completo do UnrealEditor.exe (Enter para pular)'
        if ($answer -and $answer.Trim()) {
            $editor = $answer.Trim().Trim('"')
            if (-not (Test-Path $editor)) {
                Stop-WithFailure "O caminho informado nao existe: $editor" `
                    'Aponte para ...\Engine\Binaries\Win64\UnrealEditor.exe'
            }
        } else {
            Write-Warn2 'Sem editor: abra o Unreal manualmente e siga o TESTE_LOCAL.md.'
            Complete-Step 'pulado (editor nao localizado)'
            return $false
        }
    }

    Write-Info "Abrindo: $editor"
    Write-Info "Projeto : $uprojectPath"
    Start-Process -FilePath $editor -ArgumentList @("`"$uprojectPath`"")
    Write-Ok 'Editor iniciado. Ele pode levar alguns minutos para carregar.'
    Complete-Step $editor
    return $true
}

# ====================================================== 9. porta 30010
function Step-9-WaitForRemoteControl([int]$Port, [bool]$EditorStarted) {
    Start-Step "Aguardando a Remote Control API (porta $Port)"

    $maxAttempts = 60
    if (-not $EditorStarted) {
        $maxAttempts = 3
        Write-Info 'Editor nao foi iniciado por este script; checagem rapida apenas.'
    }

    $uri = "http://127.0.0.1:$Port/remote/info"
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri $uri -TimeoutSec 5 -ErrorAction Stop
            if ($null -ne $response.HttpRoutes) {
                Write-Ok "Editor respondendo em $uri ($($response.HttpRoutes.Count) rotas)."
                Complete-Step "$($response.HttpRoutes.Count) rotas"
                return $true
            }
        } catch {
            # esperado enquanto o editor carrega
        }
        if ($attempt -lt $maxAttempts) {
            Write-Info "tentativa $attempt/$maxAttempts - ainda nao respondeu; aguardando 5s..."
            Start-Sleep -Seconds 5
        }
    }

    Write-Warn2 "A porta $Port nao respondeu."
    Write-Host ''
    Write-Host '    VERIFIQUE (em ordem):' -ForegroundColor Yellow
    Write-Host '      1. O Unreal Editor esta aberto?' -ForegroundColor Yellow
    Write-Host '      2. Edit > Plugins > "Remote Control API" esta Enabled? (reinicie)' -ForegroundColor Yellow
    Write-Host '      3. No console do editor (tecla `), rode: WebControl.StartServer' -ForegroundColor Yellow
    Write-Host '      4. A porta bate com RemoteControlHttpServerPort do' -ForegroundColor Yellow
    Write-Host '         Config\DefaultRemoteControl.ini?' -ForegroundColor Yellow
    Write-Host '    Checklist completo: TESTE_LOCAL.md secao 8.1' -ForegroundColor Yellow
    Write-Host ''
    Complete-Step "sem resposta na porta $Port"
    return $false
}

# ====================================================== 10. servidor MCP
function Step-10-McpServer([string]$venvPython, [string]$uprojectPath) {
    Start-Step 'Iniciando o servidor MCP'

    if ($NoMcpServer) {
        Write-Info 'Pulado (-NoMcpServer).'
        Complete-Step 'pulado'
        return
    }

    # Workspaces: o que o usuario passou + a pasta do .uproject.
    $folders = @()
    if ($Workspace) { $folders += $Workspace }
    if ($uprojectPath) { $folders += (Split-Path -Parent $uprojectPath) }
    $folders = $folders | Where-Object { $_ } | Select-Object -Unique

    if ($folders.Count -eq 0) {
        Write-Warn2 'Nenhuma pasta autorizada: o servidor so tera os workspaces ja salvos.'
        Write-Warn2 'Use -Workspace "C:\Pasta" ou -UnrealProjectPath.'
    }

    $serverArgs = @('-m', 'app.mcp_server')
    foreach ($folder in $folders) {
        $serverArgs += @('--workspace', $folder)
        Write-Info "Workspace autorizado: $folder"
    }
    $serverArgs += '--allow-read'
    if ($AllowWrite) {
        $serverArgs += '--allow-write'
        Write-Warn2 'ESCRITA HABILITADA (-AllowWrite): cada operacao ainda pede'
        Write-Warn2 'aprovacao no checkpoint, a menos que voce use --auto-approve.'
    } else {
        Write-Info 'Somente leitura (use -AllowWrite para permitir escrita).'
    }

    Write-Ok 'Comando do servidor MCP:'
    Write-Host ''
    Write-Host "    cd `"$Script:RepoRoot`"" -ForegroundColor Cyan
    Write-Host "    & `"$venvPython`" $($serverArgs -join ' ')" -ForegroundColor Cyan
    Write-Host ''
    Write-Info 'Cole isto no mcpServers do seu cliente (Claude Desktop/Cline):'
    Write-Host ''
    $jsonFolders = ($folders | ForEach-Object { '        "--workspace", "' + ($_ -replace '\\', '\\') + '",' }) -join "`n"
    @"
    "lumen": {
      "command": "$($venvPython -replace '\\', '\\')",
      "args": [
        "-m", "app.mcp_server",
$jsonFolders
        "--allow-read"$(if ($AllowWrite) { ',' + "`n" + '        "--allow-write"' } else { '' })
      ],
      "cwd": "$($Script:RepoRoot -replace '\\', '\\')",
      "env": { "LUMEN_MCP_LOG_LEVEL": "WARNING", "PYTHONIOENCODING": "utf-8" }
    }
"@ | Write-Host -ForegroundColor DarkCyan

    Write-Info 'O servidor roda como subprocesso do cliente MCP; nao o iniciamos'
    Write-Info 'aqui para nao disputar o stdin. Modelo pronto: mcp_config.json'

    Complete-Step ($folders -join '; ')
}

# ============================================================== 11. resumo
function Step-11-Summary([bool]$RemoteControlOk, [bool]$EditorStarted) {
    Write-Header 'RESUMO'

    foreach ($step in $Script:StepLog) {
        $detail = if ($step.Detail) { " ($($step.Detail))" } else { '' }
        Write-Host ("  [OK] {0}. {1}{2}" -f $step.Number, $step.Name, $detail) -ForegroundColor Green
    }

    Write-Host ''
    if (-not $RemoteControlOk) {
        Write-Host '  ⚠  Pronto para uso PARCIAL.' -ForegroundColor Yellow
        Write-Host '     Pesquisa, planejamento, escrita de arquivos e servidor MCP OK.' -ForegroundColor Yellow
        Write-Host '     A ponte com o Unreal NAO foi validada (porta 30010 sem resposta).' -ForegroundColor Yellow
        Write-Host '     Siga TESTE_LOCAL.md secao 8.1 e rode o script novamente.' -ForegroundColor Yellow
        Write-Host ''
        return
    }

    if (-not $EditorStarted) {
        Write-Host '  ✅ Pronto para uso.' -ForegroundColor Green
        Write-Host '     O editor ja estava aberto e respondeu na porta 30010.' -ForegroundColor Green
    } else {
        Write-Host '  ✅ Pronto para uso.' -ForegroundColor Green
    }
    Write-Host ''
    Write-Host '  PROXIMOS PASSOS:' -ForegroundColor Cyan
    Write-Host '    1. Configure o cliente MCP com o JSON impresso na etapa 10' -ForegroundColor Cyan
    Write-Host '       (modelo pronto em mcp_config.json).' -ForegroundColor Cyan
    Write-Host '    2. Feche e reabra o Claude Desktop (ele so le a config no inicio).' -ForegroundColor Cyan
    Write-Host '    3. Peça: "Use unreal_get_info e me diga se o editor esta conectado."' -ForegroundColor Cyan
    Write-Host '    4. Depois: "Crie um Actor Blueprint BP_TestConnection em' -ForegroundColor Cyan
    Write-Host '       /Game/Blueprints." e confira no Content Browser.' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '    Roteiro completo: TESTE_LOCAL.md secao 4.' -ForegroundColor Cyan
    Write-Host '    As ferramentas de criacao de Blueprint ainda NAO foram validadas' -ForegroundColor DarkGray
    Write-Host '    contra um Unreal real - se algo falhar, veja TESTE_LOCAL.md secao 7.' -ForegroundColor DarkGray
    Write-Host ''
}

# ==================================================================== main
try {
    Write-Header 'LUMEN - bootstrap para Windows'
    Write-Host "  Repositorio: $Script:RepoRoot"
    Write-Host "  PowerShell : $($PSVersionTable.PSVersion)"

    $python      = Step-1-Python
    Step-2-Repository | Out-Null
    $venvPython  = Step-3-Virtualenv $python
    Step-4-Dependencies $venvPython
    Step-5-Tests $venvPython
    $uproject    = Step-6-Uproject
    Step-7-Plugins $uproject
    $editorUp    = Step-8-LaunchUnreal $uproject
    $rcOk        = Step-9-WaitForRemoteControl $RemoteControlPort ([bool]$editorUp)
    Step-10-McpServer $venvPython $uproject
    Step-11-Summary ([bool]$rcOk) ([bool]$editorUp)

    exit 0
} catch {
    Stop-WithFailure "Erro inesperado na etapa $Script:CurrentStep: $($_.Exception.Message)" @'
Execute com -Verbose para mais detalhes, ou rode os comandos manualmente
seguindo TESTE_LOCAL.md. A mensagem completa da excecao esta abaixo.
'@
}
