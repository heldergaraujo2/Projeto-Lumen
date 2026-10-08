"""Cliente HTTP da Remote Control API do Unreal Editor (Fase 4).

Implementado com ``urllib`` da stdlib, no mesmo padrão de transporte
injetável de ``app/research/client.py``: os testes usam um transporte fake
e **nenhum teste toca a rede**.

Rotas implementadas — conferidas contra a referência oficial
(https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-api-http-reference-for-unreal-engine,
versão 5.8, consultada em 2026-10-08):

===============================  =====  ==============================
Rota                             Verbo  Uso aqui
===============================  =====  ==============================
``/remote/info``                 GET    ``info()`` — descoberta/saúde
``/remote/object/call``          PUT    ``call_function()``
``/remote/object/property``      PUT    ``get_property()`` / ``set_property()``
``/remote/object/describe``      PUT    ``describe()``
``/remote/search/assets``        PUT    ``search_assets()``
``/remote/batch``                PUT    ``batch()``
``/remote/object/thumbnail``     PUT    ``thumbnail()``
``/remote/object/event``         PUT    ``await_event()`` (experimental)
===============================  =====  ==============================

**O que a RC API NÃO faz** (achado decisivo da Fase -1): não existe rota
para criar assets. Nem Blueprint, nem Material, nem Data Asset. A lista de
rotas acima é a lista completa. Criar uma classe Blueprint exige executar
código no editor — o que só é possível com o **Python Editor Script
Plugin** habilitado e a rota de execução liberada
(``app/unreal_bridge/python_script.py``). Por isso ``execute_python()``
existe e por isso o transporte tem o modo ``python``.

Restrições documentadas que o código respeita (e que aparecem nas
mensagens de erro, para o usuário entender o "não"):

- ``/remote/object/call`` só alcança função **chamável por Blueprint**
  (``BlueprintCallable`` ou definida em Blueprint);
- ``/remote/object/property`` só alcança propriedade ``public``, **sem**
  ``BlueprintGetter``/``BlueprintSetter``, e no editor precisa ser
  ``EditAnywhere`` (para escrever, não pode ser ``EditConst``). Em PIE
  precisa ser ``BlueprintVisible`` (e não ``BlueprintReadOnly`` para
  escrever);
- em PIE o caminho do objeto ganha o prefixo ``UEDPIE_0_``;
- ``/remote/object/event`` é experimental e exige
  ``WebControl.EnableExperimentalRoutes = 1`` em ``DefaultEngine.ini``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.unreal_bridge.config import (
    UnrealBridgeConfig,
    UnrealBridgeError,
    UnrealUnavailableError,
)

logger = logging.getLogger("lumen.unreal")

#: Transporte injetável: (method, url, body, headers, timeout) -> (status, body).
#: Mesma assinatura de ``app/research/client.py`` de propósito: um teste
#: aprende um formato e serve para os dois módulos.
Transport = Callable[[str, str, bytes | None, Mapping[str, str], float], tuple[int, bytes]]

REQUEST_PATH_CALL = "/remote/object/call"
REQUEST_PATH_PROPERTY = "/remote/object/property"
REQUEST_PATH_DESCRIBE = "/remote/object/describe"
REQUEST_PATH_SEARCH = "/remote/search/assets"
REQUEST_PATH_BATCH = "/remote/batch"
REQUEST_PATH_THUMBNAIL = "/remote/object/thumbnail"
REQUEST_PATH_EVENT = "/remote/object/event"
REQUEST_PATH_INFO = "/remote/info"

#: Valores aceitos em ``access`` (doc oficial).
ACCESS_READ = "READ_ACCESS"
ACCESS_WRITE = "WRITE_ACCESS"
ACCESS_WRITE_TRANSACTION = "WRITE_TRANSACTION_ACCESS"
ACCESS_VALUES = frozenset({ACCESS_READ, ACCESS_WRITE, ACCESS_WRITE_TRANSACTION})

#: Teto de bytes aceitos do editor (uma resposta de propriedades pode ser
#: grande, mas não ilimitada).
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

#: Teto de requisições por chamada de ``batch()``.
MAX_BATCH_REQUESTS = 50


def urllib_transport(
    method: str,
    url: str,
    body: bytes | None,
    headers: Mapping[str, str],
    timeout: float,
) -> tuple[int, bytes]:
    """Transporte padrão (rede real). Isolado para poder ser substituído."""
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - host local
            return int(response.status), response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # 4xx/5xx do editor trazem corpo útil: preservamos em vez de perder.
        return int(exc.code), exc.read() or b""


class RemoteControlClient:
    """Cliente fino da RC API. Não decide política — só fala HTTP.

    Args:
        config: parâmetros de conexão.
        transport: transporte injetável (usado pelos testes).
        verify_on_start: faz ``GET /remote/info`` antes da primeira
            operação real, para transformar "connection refused" num erro
            com instrução acionável.
    """

    def __init__(
        self,
        config: UnrealBridgeConfig | None = None,
        *,
        transport: Transport | None = None,
        verify_on_start: bool | None = None,
    ) -> None:
        self._config = config or UnrealBridgeConfig.from_env()
        self._transport = transport or urllib_transport
        self._verify_on_start = (
            self._config.verify_on_start if verify_on_start is None else verify_on_start
        )
        self._verified = False

    @property
    def config(self) -> UnrealBridgeConfig:
        return self._config

    # ------------------------------------------------------------ plumbing
    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        url = self._config.endpoint(path)
        body = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        effective_timeout = float(timeout if timeout is not None else self._config.timeout)
        try:
            status, raw = self._transport(method, url, body, headers, effective_timeout)
        except (URLError, OSError, TimeoutError) as exc:
            raise UnrealUnavailableError(
                f"Não foi possível falar com o Unreal em {self._config.base_url} "
                f"({type(exc).__name__}: {exc}). Verifique se o editor está aberto "
                "e se o plugin 'Remote Control API' está habilitado "
                "(veja TESTE_LOCAL.md, seção de troubleshooting)."
            ) from exc

        if len(raw) > MAX_RESPONSE_BYTES:
            raise UnrealBridgeError(
                f"Resposta do editor excedeu {MAX_RESPONSE_BYTES} bytes."
            )

        if status >= 400:
            detail = _extract_error(raw)
            raise UnrealBridgeError(
                f"O editor recusou {method} {path} (HTTP {status}){': ' + detail if detail else '.'}"
            )

        if not raw:
            # WRITE_ACCESS responde 200 com corpo vazio — sucesso, sem payload.
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UnrealBridgeError(
                f"Resposta do editor não é JSON válido em {path}: {exc}"
            ) from exc

    def _ensure_available(self) -> None:
        """Falha cedo com mensagem clara se o editor não estiver alcançável."""
        if self._verified or not self._verify_on_start:
            return
        self._verified = True
        self.info()

    # ---------------------------------------------------------------- saúde
    def info(self, *, timeout: float | None = None) -> dict[str, Any]:
        """``GET /remote/info`` — lista as rotas ativas (e prova que há editor)."""
        payload = self._request("GET", REQUEST_PATH_INFO, timeout=timeout)
        return payload if isinstance(payload, dict) else {"raw": payload}

    def is_available(self, *, timeout: float | None = None) -> bool:
        """``True`` se o editor responde. **Nunca levanta** — é um probe."""
        try:
            self.info(timeout=timeout)
            return True
        except UnrealBridgeError:
            return False

    def routes(self) -> list[str]:
        """Caminhos de rota anunciados pelo editor (para diagnóstico)."""
        payload = self.info()
        routes = payload.get("HttpRoutes") or []
        return sorted(
            str(entry.get("Path")) for entry in routes if isinstance(entry, Mapping)
        )

    # --------------------------------------------------------------- objetos
    def call_function(
        self,
        object_path: str,
        function_name: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        generate_transaction: bool = True,
        timeout: float | None = None,
    ) -> Any:
        """``PUT /remote/object/call``.

        ``generate_transaction=True`` (default) faz a chamada entrar no
        Undo History do editor — desfazer é o único "rollback" disponível
        para uma alteração remota, então manter ligado é o padrão seguro.
        """
        self._require(object_path, "objectPath")
        self._require(function_name, "functionName")
        self._ensure_available()
        return self._request(
            "PUT",
            REQUEST_PATH_CALL,
            {
                "objectPath": object_path,
                "functionName": function_name,
                "parameters": dict(parameters or {}),
                "generateTransaction": bool(generate_transaction),
            },
            timeout=timeout,
        )

    def get_property(
        self, object_path: str, property_name: str | None = None,
        *, timeout: float | None = None,
    ) -> Any:
        """``PUT /remote/object/property`` com ``READ_ACCESS``.

        Sem ``property_name`` devolve **todas** as propriedades legíveis do
        objeto (comportamento documentado da rota).
        """
        self._require(object_path, "objectPath")
        payload: dict[str, Any] = {"objectPath": object_path, "access": ACCESS_READ}
        if property_name:
            payload["propertyName"] = property_name
        self._ensure_available()
        return self._request("PUT", REQUEST_PATH_PROPERTY, payload, timeout=timeout)

    def set_property(
        self,
        object_path: str,
        property_name: str,
        value: Any,
        *,
        transaction: bool = True,
        timeout: float | None = None,
    ) -> Any:
        """``PUT /remote/object/property`` com escrita.

        Sucesso devolve ``None`` (a rota responde 200 com corpo vazio).
        ``transaction=True`` usa ``WRITE_TRANSACTION_ACCESS``: o editor
        trata a mudança como se feita no painel Details — undoable e com
        os eventos de pré/pós-mudança disparados.
        """
        self._require(object_path, "objectPath")
        self._require(property_name, "propertyName")
        self._ensure_available()
        return self._request(
            "PUT",
            REQUEST_PATH_PROPERTY,
            {
                "objectPath": object_path,
                "propertyName": property_name,
                "access": ACCESS_WRITE_TRANSACTION if transaction else ACCESS_WRITE,
                "propertyValue": {property_name: value},
            },
            timeout=timeout,
        )

    def describe(self, object_path: str, *, timeout: float | None = None) -> dict[str, Any]:
        """``PUT /remote/object/describe`` — propriedades/funções do objeto."""
        self._require(object_path, "objectPath")
        self._ensure_available()
        payload = self._request(
            "PUT", REQUEST_PATH_DESCRIBE, {"objectPath": object_path}, timeout=timeout
        )
        return payload if isinstance(payload, dict) else {}

    def search_assets(
        self,
        query: str = "",
        *,
        class_names: Sequence[str] | None = None,
        package_paths: Sequence[str] | None = None,
        recursive_paths: bool = True,
        recursive_classes: bool = False,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """``PUT /remote/search/assets`` — busca no Asset Registry."""
        self._ensure_available()
        payload = self._request(
            "PUT",
            REQUEST_PATH_SEARCH,
            {
                "Query": query or "",
                "Filter": {
                    "PackageNames": [],
                    "ClassNames": list(class_names or []),
                    "PackagePaths": list(package_paths or []),
                    "RecursiveClassesExclusionSet": [],
                    "RecursivePaths": bool(recursive_paths),
                    "RecursiveClasses": bool(recursive_classes),
                },
            },
            timeout=timeout,
        )
        assets = (payload or {}).get("Assets") if isinstance(payload, Mapping) else None
        return list(assets or [])

    def batch(
        self, requests: Sequence[Mapping[str, Any]], *, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        """``PUT /remote/batch`` — várias chamadas em um só request.

        Cada item de ``requests`` precisa de ``URL`` e ``Verb``; ``Body`` é
        opcional. ``RequestId`` é atribuído automaticamente quando ausente.
        """
        if not requests:
            raise UnrealBridgeError("batch() exige ao menos uma requisição.")
        if len(requests) > MAX_BATCH_REQUESTS:
            raise UnrealBridgeError(
                f"batch() aceita no máximo {MAX_BATCH_REQUESTS} requisições "
                f"(recebidas {len(requests)})."
            )
        prepared = []
        for index, item in enumerate(requests, start=1):
            url = item.get("URL") or item.get("url")
            if not url:
                raise UnrealBridgeError(f"requisição {index} do batch não tem 'URL'.")
            entry: dict[str, Any] = {
                "RequestId": item.get("RequestId", index),
                "URL": url,
                "Verb": str(item.get("Verb") or item.get("verb") or "PUT").upper(),
            }
            if item.get("Body") is not None:
                entry["Body"] = item["Body"]
            prepared.append(entry)

        self._ensure_available()
        payload = self._request(
            "PUT", REQUEST_PATH_BATCH, {"Requests": prepared}, timeout=timeout
        )
        responses = (payload or {}).get("Responses") if isinstance(payload, Mapping) else None
        return list(responses or [])

    def thumbnail(self, object_path: str, *, timeout: float | None = None) -> str:
        """``PUT /remote/object/thumbnail`` — miniatura do asset (base64/PNG)."""
        self._require(object_path, "objectPath")
        self._ensure_available()
        result = self._request(
            "PUT", REQUEST_PATH_THUMBNAIL, {"objectPath": object_path}, timeout=timeout
        )
        return "" if result is None else str(result)

    def await_event(
        self,
        event_type: str,
        object_path: str,
        property_name: str = "",
        *,
        timeout: float | None = None,
    ) -> Any:
        """``PUT /remote/object/event`` — **rota experimental**.

        Requer ``WebControl.EnableExperimentalRoutes = 1`` em
        ``DefaultEngine.ini``. A rota **não retorna** até o evento ocorrer,
        então o timeout precisa ser escolhido com cuidado.
        """
        self._require(object_path, "objectPath")
        self._ensure_available()
        payload: dict[str, Any] = {"EventType": event_type, "ObjectPath": object_path}
        if property_name:
            payload["PropertyName"] = property_name
        return self._request("PUT", REQUEST_PATH_EVENT, payload, timeout=timeout)

    # --------------------------------------------------------------- python
    def execute_python(
        self, code: str, *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Executa Python **dentro do editor** via Python Editor Script Plugin.

        Necessário porque a RC API não cria assets (ver docstring do
        módulo). Chama ``ExecutePythonCommandEx`` na biblioteca do plugin
        com ``ExecutionMode = ExecuteFile`` (sem arquivo, código em
        memória) e devolve o dicionário de saída do editor.

        **Validação manual pendente:** o nome exato dos parâmetros e o
        formato do dicionário de saída desta função vêm do plugin, não da
        referência HTTP da RC API. Ver a seção "O QUE AINDA PRECISA DE
        VALIDAÇÃO MANUAL" em ``TESTE_LOCAL.md``. O cliente trata a
        resposta de forma tolerante: aceita ``CommandResult``/``LogOutput``
        e também respostas sem esses campos, sem inventar sucesso.
        """
        if self._config.transport == "rc":
            raise UnrealBridgeError(
                "Executar Python exige o transporte 'python' ou 'auto' "
                "(LUMEN_UNREAL_TRANSPORT); com 'rc' só as rotas HTTP puras valem."
            )
        if not isinstance(code, str) or not code.strip():
            raise UnrealBridgeError("execute_python() exige código não vazio.")

        self._ensure_available()
        result = self.call_function(
            self._config.python_class_path,
            "ExecutePythonCommandEx",
            {
                "PythonCommand": code,
                "ExecutionMode": "ExecuteFile",
                "FileExecutionScope": "Private",
            },
            generate_transaction=False,
            timeout=timeout,
        )
        return result if isinstance(result, dict) else {"raw": result}

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _require(value: Any, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise UnrealBridgeError(f"'{name}' é obrigatório e deve ser texto não vazio.")


def _extract_error(raw: bytes) -> str:
    """Extrai a mensagem de erro do corpo, sem vazar HTML gigante."""
    if not raw:
        return ""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:300]
    if isinstance(payload, Mapping):
        for key in ("errorMessage", "message", "error", "Message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
        return json.dumps(payload, ensure_ascii=False)[:300]
    return text[:300]


__all__ = [
    "ACCESS_READ",
    "ACCESS_VALUES",
    "ACCESS_WRITE",
    "ACCESS_WRITE_TRANSACTION",
    "MAX_BATCH_REQUESTS",
    "MAX_RESPONSE_BYTES",
    "REQUEST_PATH_BATCH",
    "REQUEST_PATH_CALL",
    "REQUEST_PATH_DESCRIBE",
    "REQUEST_PATH_EVENT",
    "REQUEST_PATH_INFO",
    "REQUEST_PATH_PROPERTY",
    "REQUEST_PATH_SEARCH",
    "REQUEST_PATH_THUMBNAIL",
    "RemoteControlClient",
    "Transport",
    "urllib_transport",
]
