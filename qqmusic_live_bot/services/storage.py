from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStorage:
    def __init__(self, path: Path, default: dict[str, Any]):
        self.path = path
        self.default = default
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(self.default, ensure_ascii=False))
        try:
            return json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            return json.loads(json.dumps(self.default, ensure_ascii=False))

    def save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class MemoryService:
    def __init__(self, path: Path):
        self.store = JsonStorage(
            path,
            {
                "users": {},
                "room_notes": [],
            },
        )
        self.data = self.store.load()

    def touch_user(self, username: str, event_type: str, detail: str) -> None:
        if not username:
            return
        users = self.data.setdefault("users", {})
        profile = users.setdefault(username, {"gift_count": 0, "chat_count": 0, "notes": []})
        if event_type == "gift":
            profile["gift_count"] = int(profile.get("gift_count", 0)) + 1
        if event_type == "chat":
            profile["chat_count"] = int(profile.get("chat_count", 0)) + 1
        if detail:
            profile.setdefault("notes", []).append(detail[:60])
            profile["notes"] = profile["notes"][-5:]
        self.store.save(self.data)

    def add_room_note(self, note: str) -> None:
        if not note:
            return
        notes = self.data.setdefault("room_notes", [])
        if note not in notes:
            notes.append(note)
            self.data["room_notes"] = notes[-10:]
            self.store.save(self.data)


