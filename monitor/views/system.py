"""版本更新、系統重啟、重複 IP log 與網路先期檢測。"""
import ipaddress
import json
import subprocess
import time
import urllib.request
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import Device
from .helpers import get_profile

# 專案根目錄（manage.py 所在層）
BASE_DIR = Path(__file__).resolve().parent.parent.parent


_VERSION_FILE = BASE_DIR / "VERSION"
_GITHUB_VERSION_URL = "https://raw.githubusercontent.com/syuming/nodeguard/main/VERSION"
_ver_cache: dict = {"latest": None, "ts": 0.0}
_VER_CACHE_TTL = 1800  # 30 分鐘


def _parse_ver(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)


@login_required
def api_version_check(request):
    current = _VERSION_FILE.read_text().strip()
    now = time.time()
    if _ver_cache["latest"] and now - _ver_cache["ts"] < _VER_CACHE_TTL:
        latest = _ver_cache["latest"]
    else:
        try:
            with urllib.request.urlopen(_GITHUB_VERSION_URL, timeout=5) as resp:
                latest = resp.read().decode().strip()
            _ver_cache["latest"] = latest
            _ver_cache["ts"] = now
        except Exception:
            return JsonResponse({"current": current, "latest": None, "has_update": False})
    has_update = _parse_ver(latest) > _parse_ver(current)
    return JsonResponse({"current": current, "latest": latest, "has_update": has_update})


@login_required
@require_POST
def api_system_update(request):
    if not hasattr(request.user, "profile") or request.user.profile.role != "admin":
        return JsonResponse({"error": "無權限"}, status=403)
    script = BASE_DIR / "update.sh"
    if not script.exists():
        return JsonResponse({"error": "找不到 update.sh"}, status=500)
    subprocess.Popen(
        ["bash", str(script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return JsonResponse({"status": "started"})


@login_required
@require_POST
def api_system_restart(request):
    if not hasattr(request.user, "profile") or request.user.profile.role != "admin":
        return JsonResponse({"error": "無權限"}, status=403)
    app_dir = BASE_DIR
    subprocess.Popen(
        ["bash", "-c", f'bash "{app_dir}/stop.sh" && bash "{app_dir}/start.sh"'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return JsonResponse({"status": "restarting"})


@login_required
def api_changelog(request):
    changelog_file = BASE_DIR / "CHANGELOG.md"
    try:
        text = changelog_file.read_text(encoding="utf-8")
    except Exception:
        return JsonResponse({"releases": []})

    releases = []
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                releases.append(current)
            header = line[3:].strip()          # e.g. "v1.3.9 — 2026-06-02"
            parts = header.replace("—", "—").split("—")
            version = parts[0].strip().lstrip("v")
            date = parts[1].strip() if len(parts) > 1 else ""
            current = {"version": version, "date": date, "changes": []}
        elif line.startswith("- ") and current is not None:
            current["changes"].append(line[2:].strip())
    if current:
        releases.append(current)

    return JsonResponse({"releases": releases})


@login_required
def duplicate_ip_log(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    log_file = BASE_DIR / "duplicate_ip.log"
    lines = []
    if log_file.exists():
        raw = log_file.read_text(encoding="utf-8").strip().splitlines()
        lines = list(reversed(raw))  # 最新在前
    return render(request, "monitor/duplicate_ip_log.html", {
        "profile": profile, "lines": lines, "log_file": str(log_file),
    })


@login_required
def api_duplicate_ip_log(request):
    if not hasattr(request.user, "profile") or request.user.profile.role != "admin":
        return JsonResponse({"error": "無權限"}, status=403)
    log_file = BASE_DIR / "duplicate_ip.log"
    lines = []
    if log_file.exists():
        raw = log_file.read_text(encoding="utf-8").strip().splitlines()
        lines = list(reversed(raw))[:20]  # 最新 20 筆
    return JsonResponse({"lines": lines})


@login_required
def api_check_ip(request):
    ip         = request.GET.get("ip", "").strip()
    company_id = request.GET.get("company_id", "").strip()
    exclude_id = request.GET.get("exclude_id", "").strip()
    if not ip or not company_id:
        return JsonResponse({"exists": False})
    profile = get_profile(request.user)
    if not profile.is_admin and str(profile.company_id) != company_id:
        return JsonResponse({"exists": False})
    qs = Device.objects.filter(ip_address=ip, company_id=company_id)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    device = qs.select_related("company").first()
    if device:
        return JsonResponse({"exists": True, "device_name": device.name})
    return JsonResponse({"exists": False})


def _validate_ip(ip: str):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


@login_required
@require_POST
def api_ping_check(request):
    body = json.loads(request.body)
    ip = body.get("ip", "").strip()
    if not _validate_ip(ip):
        return JsonResponse({"error": "IP 格式錯誤"}, status=400)
    try:
        result = subprocess.run(
            ["ping", "-c", "4", "-W", "2", ip],
            capture_output=True, text=True, timeout=15
        )
        return JsonResponse({"output": result.stdout or result.stderr, "success": result.returncode == 0})
    except subprocess.TimeoutExpired:
        return JsonResponse({"output": "逾時（超過 15 秒）", "success": False})


@login_required
@require_POST
def api_traceroute_check(request):
    body = json.loads(request.body)
    ip = body.get("ip", "").strip()
    if not _validate_ip(ip):
        return JsonResponse({"error": "IP 格式錯誤"}, status=400)
    for cmd in [["traceroute", "-m", "15", "-w", "2", ip], ["tracepath", "-m", "15", ip]]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return JsonResponse({"output": result.stdout or result.stderr, "success": result.returncode == 0})
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return JsonResponse({"output": "逾時（超過 60 秒）", "success": False})
    return JsonResponse({"error": "找不到 traceroute 或 tracepath 指令"}, status=500)
