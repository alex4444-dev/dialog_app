from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class User:
    username: str
    password_hash: str
    public_key: str
    registered_at: datetime
    last_seen: datetime

@dataclass
class Session:
    session_id: str
    username: str
    created_at: datetime
    expires_at: datetime

@dataclass
class Peer:
    peer_id: str
    address: str
    port: int
    last_seen: datetime
    is_connected: bool