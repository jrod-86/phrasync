"""Launch non-interactive media helpers without flashing a Windows console."""
import subprocess


def background_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)
