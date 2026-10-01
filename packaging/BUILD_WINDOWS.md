# Build do aplicativo Lumen para Windows

## Duplo clique
Com Python instalado, o arquivo Lumen.pyw abre a UI sem PowerShell.

## Executável
No ambiente de build:
python -m pip install pyinstaller
pyinstaller --noconfirm packaging/Lumen.spec

O executável fica em dist/Lumen/Lumen.exe.

## Componentes
- Computer Control é carregado pela composição oficial e permanece desarmado.
- Ollama é detectado, mas não iniciado automaticamente.
- Unreal/MCP é detectado, mas não iniciado automaticamente.
- Ausência de Ollama/MCP não impede a UI de abrir.
