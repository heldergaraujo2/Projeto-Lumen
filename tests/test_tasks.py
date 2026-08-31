"""Testes do TaskManager."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.tasks.manager import TaskManager, TaskNotFoundError, TaskStatus


def test_create_task_with_defaults(tmp_path):
    """3. TaskManager cria tarefa com id, status PENDING e timestamps."""
    manager = TaskManager(tmp_path / "tasks.json")
    task = manager.create_task("Criar inventário do jogo")

    assert task.id == "T-0001"
    assert task.title == "Criar inventário do jogo"
    assert task.status is TaskStatus.PENDING
    datetime.fromisoformat(task.created_at)
    datetime.fromisoformat(task.updated_at)


def test_ids_increment_and_persist(tmp_path):
    path = tmp_path / "tasks.json"
    manager = TaskManager(path)
    manager.create_task("primeira")
    manager.create_task("segunda")

    reloaded = TaskManager(path)
    assert [t.id for t in reloaded.list_tasks()] == ["T-0001", "T-0002"]


def test_update_status_persists(tmp_path):
    path = tmp_path / "tasks.json"
    manager = TaskManager(path)
    task = manager.create_task("estudar Unreal")

    updated = manager.update_status(task.id, "in_progress")
    assert updated.status is TaskStatus.IN_PROGRESS

    assert TaskManager(path).get_task("T-0001").status is TaskStatus.IN_PROGRESS


def test_update_invalid_status_raises(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json")
    task = manager.create_task("a")
    with pytest.raises(ValueError):
        manager.update_status(task.id, "BANANA")


def test_get_missing_task_raises(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json")
    with pytest.raises(TaskNotFoundError):
        manager.get_task("T-9999")


def test_create_empty_title_raises(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json")
    with pytest.raises(ValueError):
        manager.create_task("   ")


def test_list_filters_by_status(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json")
    first = manager.create_task("a")
    manager.create_task("b")
    manager.update_status(first.id, TaskStatus.DONE)

    assert len(manager.list_tasks()) == 2
    assert [t.id for t in manager.list_tasks(status=TaskStatus.DONE)] == [first.id]
    assert [t.id for t in manager.list_tasks(status=TaskStatus.PENDING)] == ["T-0002"]
