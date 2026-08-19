"""
veloctra_transformers/plugin_registry.py
=========================================
Dynamic plugin registry for sandboxed python record batch transformers using weakrefs.
"""

from __future__ import annotations

import importlib.util
import logging
import weakref
from pathlib import Path
from typing import Callable, Dict, Optional

import pyarrow as pa

logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    pass


class PluginExecutionError(Exception):
    pass


class PluginRegistry:
    def __init__(self, plugin_dir: Optional[Path] = None):
        self._plugin_dir = plugin_dir or (Path.cwd() / "plugins")
        self._cache: weakref.WeakValueDictionary[str, PluginContainer] = weakref.WeakValueDictionary()
        self._strong_refs: Dict[str, PluginContainer] = {}

    def load_plugin(self, name: str, file_path: Optional[Path] = None) -> Callable[[pa.RecordBatch], pa.RecordBatch]:
        if name in self._strong_refs:
            return self._strong_refs[name].transform_fn

        path = file_path or (self._plugin_dir / f"{name}.py")
        if not path.exists():
            raise PluginLoadError(f"Plugin file for '{name}' not found at '{path}'")

        try:
            spec = importlib.util.spec_from_file_location(f"veloctra_plugin_{name}", path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Could not load module spec for '{name}'")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "transform") or not callable(mod.transform):
                raise PluginLoadError(f"Plugin '{name}' at '{path}' must expose a 'transform(batch: RecordBatch) -> RecordBatch' function.")

            container = PluginContainer(name=name, fn=mod.transform, module=mod)
            self._strong_refs[name] = container
            self._cache[name] = container

            logger.info("[PluginRegistry] Loaded plugin '%s' from %s", name, path)
            return container.transform_fn

        except Exception as exc:
            if isinstance(exc, PluginLoadError):
                raise
            raise PluginLoadError(f"Failed to load plugin '{name}': {exc}") from exc

    def execute_plugin(self, name: str, batch: pa.RecordBatch) -> pa.RecordBatch:
        fn = self.load_plugin(name)
        try:
            return fn(batch)
        except Exception as exc:
            raise PluginExecutionError(f"Error executing plugin '{name}': {exc}") from exc

    def unload_plugin(self, name: str) -> bool:
        if name in self._strong_refs:
            del self._strong_refs[name]
            logger.info("[PluginRegistry] Unloaded plugin '%s'", name)
            return True
        return False


class PluginContainer:
    def __init__(self, name: str, fn: Callable, module: Any):
        self.name = name
        self.transform_fn = fn
        self._module = module
