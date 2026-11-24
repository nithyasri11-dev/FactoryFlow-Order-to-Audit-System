import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import (
    VerifyMismatchError,
    VerificationError,
    InvalidHashError
)

from database import get_connection


# Password hashing
password_hasher = PasswordHasher()

# Supported user roles
ROLES = [
    "salesman",
    "admin",
    "production",
    "owner",
    "auditor"
]


def count_users():
    """Return the number of registered users."""

    conn = get_connection()

    try:
        result = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()

        return result[0]

    finally:
        conn.close()


def create_user(username, full_name, password, role):
    """Create a user with a securely hashed password."""

    username = username.strip().lower()
    full_name = full_name.strip()
    role = role.strip().lower()

    if not username or not full_name:
        raise ValueError("Username and full name are required.")

    if role not in ROLES:
        raise ValueError("Invalid user role.")

    if len(password) < 12:
        raise ValueError(
            "Password must contain at least 12 characters."
        )

    password_hash = password_hasher.hash(password)

    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO users
            (username, full_name, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (username, full_name, password_hash, role)
        )

        conn.commit()

        return cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("This username already exists.")

    finally:
        conn.close()


def authenticate_user(username, password):
    """Verify login credentials."""

    username = username.strip().lower()

    conn = get_connection()

    try:
        user = conn.execute(
            """
            SELECT user_id, username, full_name,
                   password_hash, role, active
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

    finally:
        conn.close()

    if not user or not user["active"]:
        return None

    try:
        password_hasher.verify(
            user["password_hash"],
            password
        )

    except (
        VerifyMismatchError,
        VerificationError,
        InvalidHashError
    ):
        return None

    if password_hasher.check_needs_rehash(
        user["password_hash"]
    ):
        new_hash = password_hasher.hash(password)

        conn = get_connection()

        try:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE user_id = ?
                """,
                (new_hash, user["user_id"])
            )

            conn.commit()

        finally:
            conn.close()

    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"]
    }


def get_all_users():
    """Return user details without exposing password hashes."""

    conn = get_connection()

    try:
        users = conn.execute(
            """
            SELECT user_id, username, full_name,
                   role, active, created_at
            FROM users
            ORDER BY user_id
            """
        ).fetchall()

        return [dict(user) for user in users]

    finally:
        conn.close()