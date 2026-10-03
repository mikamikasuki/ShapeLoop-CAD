from __future__ import annotations
import json
import os
import threading
from copy import deepcopy
from pathlib import Path

DEFAULTS = {
    "provider": {"endpoint": "", "model": "", "api_key": "", "timeout_seconds": 45, "max_tokens": 4000},
    "workers": {"timeout_seconds": 120, "memory_mb": 4096, "max_workers": 2, "max_queue": 16, "output_mb": 64},
    "scout": {"network_enabled": False, "interval_seconds": 3600, "model_budget": 0, "sources": [], "enabled": False},
}

class Settings:
    def __init__(self, root: Path):
        self.path = root / "config.json"
        self.lock = threading.RLock()
        self.value = deepcopy(DEFAULTS)
        if self.path.exists():
            for section, values in json.loads(self.path.read_text()).items():
                if section in self.value and isinstance(values, dict):
                    self.value[section].update(values)
        # Explicit opt-in environment configuration; never sent back to the browser.
        for env, key in [("SHAPELOOP_MODEL_ENDPOINT","endpoint"),("SHAPELOOP_MODEL","model"),("SHAPELOOP_API_KEY","api_key")]:
            if os.environ.get(env):
                self.value["provider"][key] = os.environ[env]

    def public(self):
        data = deepcopy(self.value)
        data["provider"]["has_api_key"] = bool(data["provider"].pop("api_key", ""))
        data["provider"]["configured"] = bool(data["provider"]["endpoint"] and data["provider"]["model"])
        return data

    def update(self, patch: dict):
        with self.lock:
            data = deepcopy(self.value)
            for section, values in patch.items():
                if section not in DEFAULTS or not isinstance(values, dict):
                    raise ValueError(f"Unknown settings section: {section}")
                for key, value in values.items():
                    if key in {"configured", "has_api_key"}:
                        continue
                    if key not in DEFAULTS[section]:
                        raise ValueError(f"Unknown setting: {section}.{key}")
                    data[section][key] = value
            w = data["workers"]
            for key, lower, upper in [("timeout_seconds",1,600),("memory_mb",512,16384),("max_workers",1,4),("max_queue",1,64),("output_mb",1,256)]:
                value = int(w[key])
                if not lower <= value <= upper:
                    raise ValueError(f"{key} must be between {lower} and {upper}")
                w[key] = value
            if not 30 <= int(data["scout"]["interval_seconds"]) <= 604800:
                raise ValueError("Scout interval must be between 30 seconds and 7 days")
            if not isinstance(data["scout"]["sources"], list):
                raise ValueError("sources must be an array of URLs")
            if not 0 <= int(data["scout"]["model_budget"]) <= 10:
                raise ValueError("model_budget must be between 0 and 10 calls")
            if not 1 <= int(data["provider"]["timeout_seconds"]) <= 180:
                raise ValueError("Provider timeout out of range")
            if not 128 <= int(data["provider"]["max_tokens"]) <= 16000:
                raise ValueError("Provider max_tokens out of range")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(data, indent=2))
            temp.chmod(0o600)
            temp.replace(self.path)
            self.value = data
        return self.public()
