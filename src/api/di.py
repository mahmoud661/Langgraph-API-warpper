from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import List

from fastapi import Depends, Request
from injector import Binder, Injector, Module, noscope
from sqlalchemy.orm import Session

from infrastructure.database.connection import get_db_session


def _iter_modules_in_package(package_name: str):
    try:
        pkg = importlib.import_module(package_name)
    except Exception:
        return

    if not hasattr(pkg, "__path__"):
        return

    for _, name, _ in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            yield importlib.import_module(name)
        except Exception:
            continue


class AutoBindModule(Module):
    def __init__(self, packages: List[str] | None = None):
        self.packages = packages or [
            "application.services",
            "application.AI",
            "infrastructure.database.postgres.repositories",
            "infrastructure.database.vector",
            "infrastructure.database",
            "presentation.controllers",
        ]

    def configure(self, binder: Binder) -> None:
        for package in self.packages:
            for module in _iter_modules_in_package(package):
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if not getattr(obj, "__module__", "").startswith(package):
                        continue

                    name = obj.__name__
                    if not (
                        name.endswith("Service")
                        or name.endswith("Repository")
                        or name.endswith("Controller")
                        or name.endswith("Runner")
                        or name.endswith("Provider")
                    ):
                        continue

                    try:
                        binder.bind(obj, to=obj, scope=noscope)
                    except Exception:
                        pass

                    for base in obj.__mro__[1:]:
                        if getattr(base, "__abstractmethods__", False):
                            try:
                                binder.bind(base, to=obj, scope=noscope)
                            except Exception:
                                continue


class RequestModule(Module):
    def __init__(self, db_session: Session):
        self._db_session = db_session

    def configure(self, binder: Binder) -> None:
        binder.bind(Session, to=self._db_session)


def inject_controller(controller_class: type):
    def dependency(request: Request, db: Session = Depends(get_db_session)):
        app = request.app
        base_injector = getattr(app.state, "base_injector", None)

        if base_injector is None:
            raise RuntimeError("base_injector not found in app.state")

        child_injector = base_injector.create_child_injector(RequestModule(db_session=db))
        instance = child_injector.get(controller_class)
        return instance

    return dependency


def create_base_injector() -> Injector:
    return Injector([AutoBindModule()])


__all__ = [
    "AutoBindModule",
    "RequestModule",
    "inject_controller",
    "create_base_injector",
]