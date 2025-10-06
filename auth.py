from __future__ import annotations
import os
from typing import Optional, Dict

AK_PATHS = [
    os.path.expanduser("~/.apikeys"),
    os.path.expanduser("~/.config/apikeys"),
]

def parse_apikeys(path: str) -> list[dict]:
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            tokens = s.split()
            kv = {}
            i = 0
            while i < len(tokens) - 1:
                key = tokens[i].lower()
                val = tokens[i+1]
                if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
                    val = val[1:-1]
                kv[key] = val
                i += 2
            kv.setdefault("name", "")
            kv.setdefault("label", "")
            kv.setdefault("apikey", "")
            kv.setdefault("secret", "")
            kv.setdefault("password", "")
            entries.append(kv)
    return entries

def load_api_credentials(exchange_name: str, preferred_label: Optional[str] = None) -> Dict[str, Optional[str]]:
    entries = []
    for p in AK_PATHS:
        if os.path.exists(p):
            entries = parse_apikeys(p)
            if entries:
                break

    if not entries:
        return {"apiKey": None, "secret": None, "password": None}

    def match(e, by_name=None, by_label=None):
        if by_name is not None and e.get("name", "") != by_name:
            return False
        if by_label is not None and e.get("label", "") != by_label:
            return False
        return True

    if preferred_label:
        for e in entries:
            if match(e, by_name=exchange_name, by_label=preferred_label):
                return {"apiKey": e.get("apikey") or None,
                        "secret": e.get("secret") or None,
                        "password": e.get("password") or None}

    if preferred_label:
        for e in entries:
            if match(e, by_label=preferred_label):
                return {"apiKey": e.get("apikey") or None,
                        "secret": e.get("secret") or None,
                        "password": e.get("password") or None}

    for e in entries:
        if match(e, by_name=exchange_name):
            return {"apiKey": e.get("apikey") or None,
                    "secret": e.get("secret") or None,
                    "password": e.get("password") or None}

    e = entries[0]
    return {"apiKey": e.get("apikey") or None,
            "secret": e.get("secret") or None,
            "password": e.get("password") or None}
