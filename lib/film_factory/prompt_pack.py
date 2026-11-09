"""Versioned PromptPack loader — category ≠ cast count."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

PACKS_ROOT = Path(__file__).resolve().parents[2] / "packs"

REQUIRED_PROMPT_KEYS = ("director", "draft", "revise", "qa", "behavior")


@dataclass
class PromptPack:
    id: str
    version: str
    label: str
    prompts: dict[str, str]
    defaults: dict[str, Any] = field(default_factory=dict)
    cast_policy: dict[str, Any] = field(default_factory=dict)
    qa_profile: dict[str, Any] = field(default_factory=dict)
    compatibility: list[str] = field(default_factory=list)
    path: str = ""

    def prompt(self, role: str) -> str:
        if role not in self.prompts or not self.prompts[role].strip():
            raise KeyError(f"PromptPack {self.id}@{self.version} missing role {role}")
        return self.prompts[role]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "label": self.label,
            "defaults": self.defaults,
            "cast_policy": self.cast_policy,
            "qa_profile": self.qa_profile,
            "compatibility": self.compatibility,
            "prompt_roles": sorted(self.prompts.keys()),
            "path": self.path,
        }


def _read_role(dir_path: Path, role: str) -> str:
    for name in (f"{role}.txt", f"{role}.md", f"SYS_{role.upper()}.txt"):
        p = dir_path / name
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


def load_pack(category_id: str, version: str = "v1") -> PromptPack:
    base = PACKS_ROOT / category_id / version
    if not base.is_dir():
        raise FileNotFoundError(f"pack not found: {base}")
    meta_path = base / "pack.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    prompts = {}
    for role in REQUIRED_PROMPT_KEYS:
        prompts[role] = _read_role(base, role)
    missing = [r for r in REQUIRED_PROMPT_KEYS if not prompts[r].strip()]
    if missing:
        raise ValueError(f"pack {category_id}@{version} missing prompts: {missing}")
    # optional audio qa
    audio = _read_role(base, "audio_qa")
    if audio.strip():
        prompts["audio_qa"] = audio
    return PromptPack(
        id=meta.get("id") or category_id,
        version=meta.get("version") or version,
        label=meta.get("label") or category_id,
        prompts=prompts,
        defaults=meta.get("defaults") or {},
        cast_policy=meta.get("cast_policy") or {},
        qa_profile=meta.get("qa_profile") or {},
        compatibility=list(meta.get("compatibility") or []),
        path=str(base),
    )


def get_pack(category_id: str, version: str = "v1") -> PromptPack:
    return load_pack(category_id, version)


def list_packs() -> list[dict[str, str]]:
    out = []
    if not PACKS_ROOT.exists():
        return out
    for cat in sorted(PACKS_ROOT.iterdir()):
        if not cat.is_dir() or cat.name == "projects":
            continue
        for ver in sorted(cat.iterdir()):
            if ver.is_dir() and (ver / "pack.json").exists():
                out.append({"id": cat.name, "version": ver.name, "path": str(ver)})
    return out


def load_project_overlay(project_id: str) -> dict[str, Any]:
    base = PACKS_ROOT / "projects" / project_id
    if not base.is_dir():
        raise FileNotFoundError(f"project overlay not found: {base}")
    meta = {}
    mp = base / "project.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    hardcode = ""
    for name in ("hardcode.txt", "hardcode.md", "HARDCODE.txt"):
        p = base / name
        if p.exists():
            hardcode = p.read_text(encoding="utf-8")
            break
    bible = ""
    for name in ("bible.md", "BIBLE.md", "SERIES_BIBLE.md"):
        p = base / name
        if p.exists():
            bible = p.read_text(encoding="utf-8")
            break
    return {"project_id": project_id, "meta": meta, "hardcode": hardcode, "bible": bible, "path": str(base)}
