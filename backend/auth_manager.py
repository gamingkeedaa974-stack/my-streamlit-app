"""
auth_manager.py
Handles user authentication, JWT token creation, and user storage.
"""
import os
import json
import hashlib
import jwt
from datetime import datetime, timedelta
from typing import Optional
class AuthManager:
    def __init__(self, users_file: str = "users.json", secret_key: str = "nse_bot_super_secret_2024"):
        self.users_file = users_file
        self.secret_key = secret_key
        # Create default admin user if file doesn't exist
        if not os.path.exists(users_file):
            default_users = {
                "admin": self._hash_password("password123")
            }
            with open(users_file, 'w') as f:
                json.dump(default_users, f, indent=4)
    def _hash_password(self, password: str) -> str:
        """Simple SHA-256 hashing (use bcrypt in production)."""
        return hashlib.sha256(password.encode()).hexdigest()
    def verify_user(self, username: str, password: str) -> bool:
        if not os.path.exists(self.users_file):
            return False
        with open(self.users_file, 'r') as f:
            users = json.load(f)
        return users.get(username) == self._hash_password(password)
    def create_token(self, username: str) -> str:
        payload = {
            "user_id": username,
            "exp": datetime.utcnow() + timedelta(hours=12)  # Token expires in 12 hours
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    def verify_token(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload.get("user_id")
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    def register_user(self, username: str, password: str) -> bool:
        if not os.path.exists(self.users_file):
            users = {}
        else:
            with open(self.users_file, 'r') as f:
                users = json.load(f)
        if username in users:
            return False  # User already exists
        users[username] = self._hash_password(password)
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=4)
        return True