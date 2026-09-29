"""
brain/owner_profile.py
======================

Owner profile for MOROAI.

Stores:
    - Age mode: "adult" (>=18) or "restricted" (<18)
    - When it was set (ISO timestamp)
    - A SHA-256 of the payload for tamper detection

Behavior on integrity failure:
    - Print a warning (not crash)
    - Ask the owner's age interactively
    - If >= 18: recreate profile as adult, allow access
    - If < 18 : recreate profile as restricted, ban 7 days, block access

Rules:
    - MOROAI never modifies this file on its own.
    - Directive D7 (AGE RESPECT) enforces behavior based on this profile.

Inspiration (no code copied):
    - Prime directives pattern: frozen + hash-verified
    - Constitutional AI: immutable owner-set declarations
"""

import os
import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

try:
    from .core_paths import PROJECT_ROOT
except ImportError:
    from core_paths import PROJECT_ROOT


# ============================================================
# Constants
# ============================================================

PROFILE_FILE = ".moroai/owner_profile.json"
BAN_FILE = ".moroai/ban.json"

AGE_MODE_ADULT = "adult"
AGE_MODE_RESTRICTED = "restricted"

BAN_DAYS = 7


# ============================================================
# Profile
# ============================================================

@dataclass(frozen=True)
class OwnerProfile:
    age_mode: str
    set_at: str
    integrity_hash: str

    @property
    def is_adult(self) -> bool:
        return self.age_mode == AGE_MODE_ADULT

    @property
    def is_restricted(self) -> bool:
        return self.age_mode == AGE_MODE_RESTRICTED


# ============================================================
# Paths
# ============================================================

def _profile_path(project_root: Optional[str] = None) -> str:
    root = os.path.abspath(project_root or PROJECT_ROOT)
    return os.path.join(root, PROFILE_FILE)


def _ban_path(project_root: Optional[str] = None) -> str:
    root = os.path.abspath(project_root or PROJECT_ROOT)
    return os.path.join(root, BAN_FILE)


# ============================================================
# Hashing
# ============================================================

def _compute_hash(age_mode: str, set_at: str) -> str:
    payload = f"{age_mode}|{set_at}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ============================================================
# Profile: existence / load / create
# ============================================================

def profile_exists(project_root: Optional[str] = None) -> bool:
    return os.path.exists(_profile_path(project_root))


def load_profile(project_root: Optional[str] = None) -> Optional[OwnerProfile]:
    """
    Load profile. Returns None if it doesn't exist.
    Raises ValueError if tampering detected.
    """
    path = _profile_path(project_root)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    age_mode = data.get("age_mode", "")
    set_at = data.get("set_at", "")
    stored_hash = data.get("integrity_hash", "")

    if age_mode not in (AGE_MODE_ADULT, AGE_MODE_RESTRICTED):
        raise ValueError(f"Invalid age_mode in profile: {age_mode!r}")

    expected = _compute_hash(age_mode, set_at)
    if expected != stored_hash:
        raise ValueError("Owner profile integrity check FAILED (tampered).")

    return OwnerProfile(
        age_mode=age_mode,
        set_at=set_at,
        integrity_hash=stored_hash,
    )


def create_profile(
    age: int,
    project_root: Optional[str] = None,
    overwrite: bool = False,
) -> OwnerProfile:
    """Create the owner profile. By default refuses to overwrite."""
    path = _profile_path(project_root)
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"Profile already exists at {path}")

    if age < 0 or age > 150:
        raise ValueError(f"Invalid age: {age}")

    age_mode = AGE_MODE_ADULT if age >= 18 else AGE_MODE_RESTRICTED
    set_at = datetime.now(timezone.utc).isoformat()
    integrity_hash = _compute_hash(age_mode, set_at)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "age_mode": age_mode,
                "set_at": set_at,
                "integrity_hash": integrity_hash,
                "note": (
                    "Set once at first run. To change, delete this file "
                    "manually and re-run: python -m brain.owner_profile setup"
                ),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return OwnerProfile(
        age_mode=age_mode,
        set_at=set_at,
        integrity_hash=integrity_hash,
    )


# ============================================================
# Ban management
# ============================================================

def is_banned(project_root: Optional[str] = None) -> Tuple[bool, int]:
    """
    Return (banned, seconds_remaining).
    Automatically clears expired bans.
    """
    path = _ban_path(project_root)
    if not os.path.exists(path):
        return False, 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        until = datetime.fromisoformat(data["until"])
    except (KeyError, ValueError, json.JSONDecodeError, OSError):
        # Corrupt ban file → treat as not banned, remove it
        try:
            os.remove(path)
        except OSError:
            pass
        return False, 0

    now = datetime.now(timezone.utc)
    if now >= until:
        # Ban expired → clean it up
        try:
            os.remove(path)
        except OSError:
            pass
        return False, 0

    return True, int((until - now).total_seconds())


def create_ban(
    reason: str,
    days: int = BAN_DAYS,
    project_root: Optional[str] = None,
) -> None:
    """Create or extend a ban."""
    path = _ban_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "banned_at": now.isoformat(),
                "until": until.isoformat(),
                "days": days,
                "reason": reason,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def clear_ban(project_root: Optional[str] = None) -> None:
    """Remove the ban file (used for testing/manual reset)."""
    path = _ban_path(project_root)
    if os.path.exists(path):
        os.remove(path)


# ============================================================
# Content rules
# ============================================================

def is_content_allowed(
    content_class: str,
    profile: Optional[OwnerProfile] = None,
) -> bool:
    """Check if a content_class is allowed for the given profile."""
    if profile is None:
        profile = load_profile()
    if profile is None:
        return content_class == "standard"

    if profile.is_adult:
        return True

    return content_class in {"standard", "research", "media"}


# ============================================================
# Interactive handler for integrity failure
# ============================================================

def handle_integrity_failure(
    project_root: Optional[str] = None,
    reason: str = "Profile missing or tampered",
) -> Optional[OwnerProfile]:
    """
    Called when the profile is missing or has been tampered with.

    Behavior:
        - Print a clear warning.
        - Ask the owner's age interactively.
        - If >= 18 : recreate profile as adult, return it, allow.
        - If < 18  : recreate as restricted, ban 7 days, return None.

    Returns:
        OwnerProfile if access is allowed.
        None if access is denied (minor tampering case).
    """
    print()
    print("=" * 60)
    print("  ⚠️  MOROAI — Owner Profile Check")
    print("=" * 60)
    print(f"  {reason}")
    print()
    print("  To continue, please confirm your age.")
    print()

    try:
        raw = input("  Enter your age: ").strip()
        age = int(raw)
    except (ValueError, KeyboardInterrupt, EOFError):
        print("  ❌ Invalid input. Access denied for safety.")
        return None

    if age < 0 or age > 150:
        print("  ❌ Invalid age range. Access denied.")
        return None

    # Recreate profile (overwrite old/tampered one)
    try:
        profile = create_profile(age, project_root=project_root, overwrite=True)
    except Exception as e:
        print(f"  ❌ Could not create profile: {e}")
        return None

    print()
    if profile.is_adult:
        print(f"  ✅ Adult profile confirmed.")
        print(f"     Access granted. All content classes enabled.")
        clear_ban(project_root)
        return profile

    # Minor
    print(f"  ⛔ Age < 18 detected.")
    print(f"     Sensitive content is blocked.")
    print(f"     Because the profile was tampered with, a 7-day ban is applied.")
    create_ban(
        reason="Profile tampering by a minor",
        days=BAN_DAYS,
        project_root=project_root,
    )
    print(f"     Access denied for {BAN_DAYS} days.")
    return None


# ============================================================
# CLI: setup / show / unban
# ============================================================

def _cli_setup() -> None:
    if profile_exists():
        print("⚠️  Owner profile already exists.")
        p = load_profile()
        print(f"    age_mode = {p.age_mode}")
        print(f"    set_at   = {p.set_at}")
        return

    print("=" * 60)
    print("  MOROAI — Owner Profile Setup")
    print("=" * 60)
    raw = input("Enter your age: ").strip()
    try:
        age = int(raw)
    except ValueError:
        print(f"❌ Invalid input: {raw!r}")
        return
    try:
        profile = create_profile(age)
    except ValueError as e:
        print(f"❌ {e}")
        return
    print(f"✅ Profile created: {profile.age_mode}")


def _cli_show() -> None:
    if not profile_exists():
        print("❌ No profile yet. Run: python -m brain.owner_profile setup")
        return
    p = load_profile()
    print(f"Age mode : {p.age_mode}")
    print(f"Set at   : {p.set_at}")
    banned, sec = is_banned()
    print(f"Banned   : {banned} ({sec}s remaining)" if banned else "Banned   : no")


def _cli_unban() -> None:
    clear_ban()
    print("✅ Ban cleared.")


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    import sys
    import tempfile
    import shutil

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "setup":
            _cli_setup()
        elif cmd == "show":
            _cli_show()
        elif cmd == "unban":
            _cli_unban()
        else:
            print(f"Unknown command: {cmd}")
    else:
        tmp = tempfile.mkdtemp()
        try:
            # 1. No profile
            assert profile_exists(tmp) is False
            assert load_profile(tmp) is None
            print("No profile: OK")

            # 2. Adult profile
            p = create_profile(25, project_root=tmp)
            assert p.is_adult
            assert load_profile(tmp).age_mode == "adult"
            print("Adult profile: OK")

            # 3. Content rules for adult
            for cc in ["standard", "research", "media", "sensitive"]:
                assert is_content_allowed(cc, p)
            print("Adult content rules: OK")

            # 4. Tamper detection
            path = _profile_path(tmp)
            with open(path, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["age_mode"] = "restricted"
                f.seek(0); f.truncate()
                json.dump(data, f)
            try:
                load_profile(tmp)
                raise AssertionError("Tampering not detected!")
            except ValueError:
                print("Tamper detection: OK")

            # 5. Ban management
            create_ban("test", days=7, project_root=tmp)
            banned, sec = is_banned(tmp)
            assert banned is True
            assert sec > 0
            print(f"Ban: OK ({sec}s remaining)")

            clear_ban(tmp)
            banned, _ = is_banned(tmp)
            assert banned is False
            print("Unban: OK")

            # 6. Restricted profile
            os.remove(path)
            p3 = create_profile(15, project_root=tmp)
            assert p3.is_restricted
            assert is_content_allowed("standard", p3)
            assert not is_content_allowed("sensitive", p3)
            print("Restricted rules: OK")

            print("\n✅ All owner_profile tests passed.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
