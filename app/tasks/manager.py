"""Task Manager — registro de tarefas da Lumen.

Fase 0: apenas criação, consulta e atualização de status, com
persistência em ``data/tasks.json``. A execução automática de tarefas
(planejamento, passos, verificação) chega em versões futuras (0.4+).
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class TaskStatus(str, Enum):
    """Ciclo de vida de uma tarefa."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskError(RuntimeError):
    """Falha do sistema de tarefas."""


class TaskNotFoundError(TaskError):
    """Tarefa solicitada não existe."""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Task:
    """Tarefa registrada na Lumen."""

    id: str
    title: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        """Representação serializável (formato do JSON em disco)."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "Task":
        """Reconstrói uma tarefa a partir do dicionário persistido."""
        try:
            task_id = data["id"]
            title = data["title"]
            status = TaskStatus(data.get("status", TaskStatus.PENDING.value))
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskError(f"Tarefa inválida no arquivo: {data!r}") from exc
        return cls(
            id=task_id,
            title=title,
            status=status,
            created_at=data.get("created_at") or _now_iso(),
            updated_at=data.get("updated_at") or _now_iso(),
            description=data.get("description", ""),
        )


class TaskManager:
    """Registro de tarefas com persistência JSON.

    IDs são sequenciais e legíveis (``T-0001``, ``T-0002``, ...).
    """

    def __init__(self, file_path: Path | str) -> None:
        self._path = Path(file_path)
        self._lock = threading.RLock()
        self._tasks: list[Task] = []
        self._load()

    # ------------------------------------------------------------ persistência
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TaskError(
                f"Arquivo de tarefas corrompido: {self._path} ({exc}). "
                "Corrija ou remova o arquivo para reiniciar as tarefas."
            ) from exc
        if not isinstance(raw, list):
            raise TaskError(
                f"Arquivo de tarefas inválido ({self._path}): esperado uma lista JSON."
            )
        self._tasks = [Task.from_dict(item) for item in raw]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [task.to_dict() for task in self._tasks]
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp_path, self._path)  # escrita atômica
        except OSError as exc:
            raise TaskError(f"Falha ao salvar tarefas em {self._path}: {exc}") from exc

    # ------------------------------------------------------------------ API
    def create_task(self, title: str, description: str = "") -> Task:
        """Cria uma tarefa nova (status inicial: ``PENDING``)."""
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise ValueError("O título da tarefa não pode ser vazio.")

        now = _now_iso()
        task = Task(
            id=self._next_id(),
            title=cleaned_title,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            description=(description or "").strip(),
        )
        with self._lock:
            self._tasks.append(task)
            self._save()
        return task

    def _next_id(self) -> str:
        numbers = []
        for task in self._tasks:
            prefix, _, suffix = task.id.rpartition("-")
            if prefix and suffix.isdigit():
                numbers.append(int(suffix))
        return f"T-{max(numbers, default=0) + 1:04d}"

    def get_task(self, task_id: str) -> Task:
        """Retorna a tarefa pelo ID.

        Raises:
            TaskNotFoundError: se não existir.
        """
        with self._lock:
            for task in self._tasks:
                if task.id == task_id:
                    return task
        raise TaskNotFoundError(f"Tarefa não encontrada: {task_id!r}")

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        """Cópia das tarefas, opcionalmente filtradas por status."""
        with self._lock:
            tasks = list(self._tasks)
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return tasks

    def update_status(self, task_id: str, status: "TaskStatus | str") -> Task:
        """Atualiza o status de uma tarefa e persiste."""
        if isinstance(status, TaskStatus):
            target = status
        else:
            try:
                target = TaskStatus(str(status).upper())
            except ValueError as exc:
                raise ValueError(
                    f"Status inválido: {status!r}. "
                    f"Use: {', '.join(s.value for s in TaskStatus)}."
                ) from exc

        with self._lock:
            task = self.get_task(task_id)  # levanta TaskNotFoundError se não existir
            task.status = target
            task.updated_at = _now_iso()
            self._save()
        return task

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._tasks)
