from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def app_version(request):
    return {"app_version": _VERSION_FILE.read_text().strip()}
