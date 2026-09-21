"""Save and load model artifacts; small per-process cache keyed by model version id (ARCH section 6)."""
import os

import joblib

_cache: dict = {"version_id": None, "artifact": None}


def save_artifact(base_dir: str, label: str, artifact: dict) -> str:
    folder = os.path.join(base_dir, label)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "model.joblib")
    joblib.dump(artifact, path)
    return path


def load_artifact(path: str) -> dict:
    return joblib.load(path)


def load_active(version_id: int, path: str) -> dict:
    """Return the artifact for the active version, reloading only when the active id changed."""
    if _cache["version_id"] != version_id:
        _cache["artifact"] = load_artifact(path)
        _cache["version_id"] = version_id
    return _cache["artifact"]


def clear_cache() -> None:
    _cache["version_id"] = None
    _cache["artifact"] = None
