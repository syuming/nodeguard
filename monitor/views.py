import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import Device, DeviceLog, Company, UserProfile, DowntimeRecord, MonitorCheck, EmailConfig
from .forms import DeviceForm, CompanyForm, UserProfileForm, AdminSetPasswordForm, UserCreateForm, UserProfileMetaForm, MonitorCheckForm
from .utils import check_device, send_email_with_config

# ── 持續監控全域狀態 ──────────────────────────────────────────────────────────
_monitor_thread = None
_monitor_stop = threading.Event()
MONITOR_INTERVAL = 3   # 每隔幾秒檢查一次（預設 3 秒）


def _monitor_loop():
    from django.utils import timezone as tz
    while not _monitor_stop.is_set():
        now = tz.now()
        devices = list(Device.objects.all())
        for d in devices:
            if _monitor_stop.is_set():
                break
            if d.last_checked is None or (now - d.last_checked).total_seconds() >= MONITOR_INTERVAL:
                try:
                    check_device(d)
                except Exception:
                    pass
        _monitor_stop.wait(1)   # 每 1 秒輪詢一次，支援最低 1 秒間隔


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_profile(user):
    """Return UserProfile, creating a default one if missing.
    Django superuser 自動對應到 admin 角色。
    """
    default_role = "admin" if user.is_superuser else "company_manager"
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": default_role})
    # 若已存在但 superuser 尚未設為 admin，自動修正
    if user.is_superuser and not profile.is_admin:
        profile.role = "admin"
        profile.save(update_fields=["role"])
    return profile


def get_visible_devices(user):
    """Return Device queryset scoped to the user's permission."""
    profile = get_profile(user)
    if profile.is_admin:
        return Device.objects.select_related("company").all()
    if profile.company:
        return Device.objects.select_related("company").filter(company=profile.company)
    return Device.objects.none()


def can_access_device(user, device):
    """Check whether user may access a specific device."""
    profile = get_profile(user)
    if profile.is_admin:
        return True
    return profile.company is not None and device.company_id == profile.company_id


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get("next", "/"))
        messages.error(request, "帳號或密碼錯誤")
    return render(request, "monitor/login.html")


def logout_view(request):
    logout(request)
    return redirect("/login/")


@login_required
def profile_edit(request):
    profile = get_profile(request.user)
    form = UserProfileForm(request.POST or None, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "個人資料已更新")
        return redirect("/profile/")
    return render(request, "monitor/profile_edit.html", {"form": form, "profile": profile})


@login_required
def user_list(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    users = User.objects.select_related("profile", "profile__company").exclude(pk=request.user.pk).order_by("username")
    return render(request, "monitor/user_list.html", {"users": users, "profile": profile})


@login_required
def user_add(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    form = UserCreateForm(request.POST or None)
    if form.is_valid():
        d = form.cleaned_data
        user = User.objects.create_user(
            username=d["username"],
            password=d["password1"],
            first_name=d["first_name"],
            last_name=d["last_name"],
            email=d["email"],
        )
        UserProfile.objects.update_or_create(user=user, defaults={"role": d["role"], "company": d["company"]})

        if "send_email" in request.POST and d["email"]:
            company_name = d["company"].name if d["company"] else "（未指定）"
            try:
                send_email_with_config(
                    subject="【NodeGuard】您的帳號已建立",
                    body=(
                        f"您好，\n\n"
                        f"您的 NodeGuard 帳號已建立，以下是登入資訊：\n\n"
                        f"  帳號：{d['username']}\n"
                        f"  密碼：{d['password1']}\n"
                        f"  所屬公司：{company_name}\n\n"
                        f"請登入後盡快修改密碼。\n\n"
                        f"系統管理者"
                    ),
                    to_list=[d["email"]],
                )
                messages.success(request, f"使用者 {user.username} 已新增，帳號密碼已寄送至 {d['email']}")
            except Exception as e:
                messages.warning(request, f"使用者 {user.username} 已新增，但 Email 寄送失敗：{e}")
        else:
            messages.success(request, f"使用者 {user.username} 已新增")

        return redirect("/users/")
    return render(request, "monitor/user_add.html", {"form": form, "profile": profile})


@login_required
def user_edit(request, pk):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    target = get_object_or_404(User.objects.select_related("profile", "profile__company"), pk=pk)
    target_profile = target.profile

    info_form = UserProfileForm(request.POST if "save_info" in request.POST else None, instance=target)
    meta_initial = {"role": target_profile.role, "company": target_profile.company}
    meta_form = UserProfileMetaForm(request.POST if "save_info" in request.POST else None, initial=meta_initial)
    pw_form = AdminSetPasswordForm(request.POST if "save_password" in request.POST else None)

    if "save_info" in request.POST and info_form.is_valid() and meta_form.is_valid():
        info_form.save()
        target_profile.role    = meta_form.cleaned_data["role"]
        target_profile.company = meta_form.cleaned_data["company"]
        target_profile.save(update_fields=["role", "company"])
        messages.success(request, f"{target.username} 的資料已更新")
        return redirect(f"/users/{pk}/edit/")

    if "save_password" in request.POST and pw_form.is_valid():
        target.set_password(pw_form.cleaned_data["new_password1"])
        target.save()
        messages.success(request, f"{target.username} 的密碼已更新")
        return redirect(f"/users/{pk}/edit/")

    return render(request, "monitor/user_edit.html", {
        "target": target, "info_form": info_form, "meta_form": meta_form,
        "pw_form": pw_form, "profile": profile
    })


@login_required
def change_password(request):
    profile = get_profile(request.user)
    form = PasswordChangeForm(request.user, request.POST or None)
    if form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        messages.success(request, "密碼已成功更新")
        return redirect("/")
    return render(request, "monitor/change_password.html", {"form": form, "profile": profile})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    profile = get_profile(request.user)
    devices = get_visible_devices(request.user)
    total   = devices.count()
    online  = devices.filter(status="online").count()
    offline = devices.filter(status="offline").count()
    warning = devices.filter(status="warning").count()
    alerts  = devices.filter(status__in=["offline", "warning"]).order_by("status", "company__name", "name")

    company_stats = []
    if profile.is_admin:
        for company in Company.objects.all().order_by("name"):
            cd = devices.filter(company=company)
            company_stats.append({
                "company": company,
                "total":   cd.count(),
                "online":  cd.filter(status="online").count(),
                "offline": cd.filter(status="offline").count(),
                "warning": cd.filter(status="warning").count(),
            })

    return render(request, "monitor/dashboard.html", {
        "total": total,
        "online": online,
        "offline": offline,
        "warning": warning,
        "alerts": alerts,
        "profile": profile,
        "company_stats": company_stats,
    })


# ── Device Detail ─────────────────────────────────────────────────────────────

@login_required
def device_detail(request, pk):
    device = get_object_or_404(Device.objects.select_related("company"), pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    logs = device.logs.all()[:100]
    downtimes = device.downtimes.all()[:50]
    checks = device.checks.all()
    check_form = MonitorCheckForm()
    profile = get_profile(request.user)
    return render(request, "monitor/device_detail.html", {
        "device": device, "logs": logs, "downtimes": downtimes,
        "checks": checks, "check_form": check_form, "profile": profile
    })


# ── Device CRUD ───────────────────────────────────────────────────────────────

@login_required
def device_add(request):
    profile = get_profile(request.user)
    initial_company_pk = request.GET.get("company")
    form = DeviceForm(request.POST or None, user_profile=profile, initial_company_pk=initial_company_pk)
    if form.is_valid():
        device = form.save()
        MonitorCheck.objects.create(device=device, check_type="ping", interval=3, enabled=True)
        _dpk = device.pk
        def _bg_check():
            from .models import Device as _D
            try:
                check_device(_D.objects.get(pk=_dpk))
            except Exception:
                pass
        threading.Thread(target=_bg_check, daemon=True).start()
        messages.success(request, "設備已新增")
        company_pk = form.cleaned_data.get("company")
        if company_pk:
            return redirect(f"/company/{company_pk.pk}/")
        return redirect("/")
    return render(request, "monitor/device_form.html", {
        "form": form, "title": "新增設備", "profile": profile
    })


@login_required
def device_edit(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    profile = get_profile(request.user)
    form = DeviceForm(request.POST or None, instance=device, user_profile=profile)
    if form.is_valid():
        form.save()
        messages.success(request, "設備已更新")
        return redirect(f"/device/{pk}/")
    return render(request, "monitor/device_form.html", {
        "form": form, "title": "編輯設備", "profile": profile
    })


@login_required
@require_POST
def device_delete(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    device.delete()
    messages.success(request, "設備已刪除")
    return redirect("/")


# ── Company CRUD（僅系統管理者） ───────────────────────────────────────────────

@login_required
def company_detail(request, pk):
    profile = get_profile(request.user)
    company = get_object_or_404(Company, pk=pk)
    # 公司管理者只能看自己的公司
    if not profile.is_admin and (profile.company is None or profile.company_id != pk):
        raise Http404
    devices = Device.objects.filter(company=company).order_by("name")
    status_counts = {s: devices.filter(status=s).count() for s in ("online", "warning", "offline", "unknown")}
    return render(request, "monitor/company_detail.html", {
        "company": company, "devices": devices, "profile": profile, **status_counts
    })


@login_required
def company_list(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    companies = Company.objects.order_by("name")
    return render(request, "monitor/company_list.html", {
        "companies": companies, "profile": profile
    })


@login_required
def company_add(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    form = CompanyForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "公司已新增")
        return redirect("/company/")
    return render(request, "monitor/company_form.html", {
        "form": form, "title": "新增公司", "profile": profile
    })


@login_required
def company_edit(request, pk):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    company = get_object_or_404(Company, pk=pk)
    form = CompanyForm(request.POST or None, instance=company)
    if form.is_valid():
        form.save()
        messages.success(request, "公司已更新")
        return redirect("/company/")
    return render(request, "monitor/company_form.html", {
        "form": form, "title": "編輯公司", "profile": profile
    })


@login_required
@require_POST
def company_delete(request, pk):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    company = get_object_or_404(Company, pk=pk)
    company.delete()
    messages.success(request, "公司已刪除")
    return redirect("/company/")


# ── API ───────────────────────────────────────────────────────────────────────

@login_required
def api_device_status(request):
    from django.utils import timezone as tz
    devices = get_visible_devices(request.user).select_related("company")
    result = []
    for d in devices:
        result.append({
            "id": d.id,
            "name": d.name,
            "ip_address": d.ip_address,
            "status": d.status,
            "last_checked": tz.localtime(d.last_checked).strftime("%Y-%m-%d %H:%M:%S") if d.last_checked else None,
            "company__name": d.company.name if d.company else None,
        })
    return JsonResponse({"devices": result})


@login_required
def api_device_detail_status(request, pk):
    """回傳單一設備的狀態、last_checked，以及各監控項目的 last_status"""
    from django.utils import timezone as tz
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    checks = list(device.checks.values("id", "last_status", "last_message", "last_checked"))
    for c in checks:
        if c["last_checked"]:
            c["last_checked"] = tz.localtime(c["last_checked"]).strftime("%m-%d %H:%M")
    return JsonResponse({
        "status": device.status,
        "last_checked": tz.localtime(device.last_checked).strftime("%Y-%m-%d %H:%M:%S") if device.last_checked else None,
        "checks": checks,
    })


@login_required
@require_POST
def api_check_device(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404

    def run():
        check_device(device)

    threading.Thread(target=run, daemon=True).start()
    return JsonResponse({"status": "checking", "device_id": pk})


@login_required
@require_POST
def api_check_all(request):
    devices = list(get_visible_devices(request.user))

    def run():
        for d in devices:
            check_device(d)

    threading.Thread(target=run, daemon=True).start()
    return JsonResponse({"status": "checking", "count": len(devices)})


@login_required
def api_device_logs(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    from django.utils import timezone as tz
    logs = list(device.logs.values("id", "level", "message", "raw_output", "created_at")[:50])
    for log in logs:
        log["created_at"] = tz.localtime(log["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
    return JsonResponse({"logs": logs})


@login_required
@require_POST
def api_monitor_toggle(request):
    global _monitor_thread, _monitor_stop
    if _monitor_thread and _monitor_thread.is_alive():
        _monitor_stop.set()
        _monitor_thread = None
        return JsonResponse({"monitoring": False, "interval": MONITOR_INTERVAL})
    else:
        _monitor_stop.clear()
        _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        _monitor_thread.start()
        return JsonResponse({"monitoring": True, "interval": MONITOR_INTERVAL})


@login_required
def api_monitor_status(request):
    running = _monitor_thread is not None and _monitor_thread.is_alive()
    return JsonResponse({"monitoring": running, "interval": MONITOR_INTERVAL})


@login_required
@require_POST
def api_snmp_add_checks(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    import json
    body = json.loads(request.body or b"{}")
    community = body.get("community", "public")
    port      = int(body.get("port", 161))
    version   = int(body.get("version", 2))
    interval  = int(body.get("interval", 60))
    interfaces = body.get("interfaces", [])
    created = 0
    OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
    for iface in interfaces:
        idx = iface.get("index")
        descr = iface.get("descr", f"if{idx}")
        oid = f"{OID_IF_OPER_STATUS}.{idx}" if idx else ""
        MonitorCheck.objects.create(
            device=device,
            check_type="snmp",
            snmp_community=community,
            snmp_version=version,
            snmp_port=port,
            snmp_oid=oid,
            snmp_label=descr,
            interval=interval,
            enabled=True,
        )
        created += 1
    return JsonResponse({"ok": True, "created": created})


@login_required
@require_POST
def api_snmp_scan(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    import json
    from monitor.utils import snmp_scan_interfaces
    body = json.loads(request.body or b"{}")
    community = body.get("community", "public")
    port      = int(body.get("port", 161))
    try:
        interfaces = snmp_scan_interfaces(device.ip_address, community=community, port=port)
        return JsonResponse({"ok": True, "interfaces": interfaces})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


# ── MonitorCheck CRUD ─────────────────────────────────────────────────────────

@login_required
@require_POST
def monitor_check_add(request, device_pk):
    device = get_object_or_404(Device, pk=device_pk)
    if not can_access_device(request.user, device):
        raise Http404
    form = MonitorCheckForm(request.POST)
    if form.is_valid():
        check = form.save(commit=False)
        check.device = device
        check.save()
        messages.success(request, "監控項目已新增")
        # 立即觸發一次背景檢查，讓狀態馬上更新而不是等到下一輪監控
        _device_pk = device.pk
        def _bg_check():
            from .models import Device as _Device
            try:
                check_device(_Device.objects.get(pk=_device_pk))
            except Exception:
                pass
        threading.Thread(target=_bg_check, daemon=True).start()
    else:
        for field_errors in form.errors.values():
            for e in field_errors:
                messages.error(request, e)
    return redirect(f"/device/{device_pk}/?tab=monitors")


@login_required
@require_POST
def monitor_check_delete(request, check_pk):
    check = get_object_or_404(MonitorCheck, pk=check_pk)
    if not can_access_device(request.user, check.device):
        raise Http404
    device_pk = check.device_id
    check.delete()
    messages.success(request, "監控項目已刪除")
    return redirect(f"/device/{device_pk}/?tab=monitors")


@login_required
@require_POST
def api_monitor_check_edit(request, check_pk):
    import json
    check = get_object_or_404(MonitorCheck, pk=check_pk)
    if not can_access_device(request.user, check.device):
        raise Http404
    body = json.loads(request.body or b"{}")
    check.port                = body.get("port") or None
    check.ssh_username        = body.get("ssh_username", "")
    check.url                 = body.get("url", "")
    check.expected_status_code = int(body.get("expected_status_code") or 200)
    check.snmp_community      = body.get("snmp_community", "public")
    check.snmp_port           = int(body.get("snmp_port") or 161)
    check.interval            = int(body.get("interval") or 60)
    if "snmp_label" in body:
        check.snmp_label = body["snmp_label"]
    if "snmp_oid" in body:
        check.snmp_oid = body["snmp_oid"]
    check.save()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def monitor_check_toggle(request, check_pk):
    check = get_object_or_404(MonitorCheck, pk=check_pk)
    if not can_access_device(request.user, check.device):
        raise Http404
    check.enabled = not check.enabled
    check.save(update_fields=["enabled"])
    return redirect(f"/device/{check.device_id}/?tab=monitors")


# ── Email 設定（僅系統管理者） ─────────────────────────────────────────────────

@login_required
def email_settings(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    cfg = EmailConfig.get_config()

    if request.method == "POST" and "save_config" in request.POST:
        cfg.method     = request.POST.get("method", "tls")
        cfg.host       = request.POST.get("host", "").strip()
        cfg.port       = int(request.POST.get("port") or 587)
        cfg.username   = request.POST.get("username", "").strip()
        cfg.from_email = request.POST.get("from_email", "").strip()
        cfg.enabled    = request.POST.get("enabled") == "on"
        # Only update password if a new one was submitted
        new_pw = request.POST.get("password", "")
        if new_pw:
            cfg.password = new_pw
        cfg.save()
        messages.success(request, "Email 設定已儲存")
        return redirect("/settings/email/")

    return render(request, "monitor/email_settings.html", {"cfg": cfg, "profile": profile})


@login_required
@require_POST
def email_test(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    to = request.POST.get("to", "").strip()
    if not to:
        messages.error(request, "請填寫收件者 Email")
        return redirect("/settings/email/")
    try:
        send_email_with_config(
            subject="【NodeGuard】測試郵件",
            body="這是一封來自 NodeGuard 的測試郵件，如果您收到此郵件，代表 Email 設定正確。",
            to_list=[to],
        )
        messages.success(request, f"測試郵件已寄送至 {to}")
    except Exception as e:
        messages.error(request, f"寄送失敗：{e}")
    return redirect("/settings/email/")


# ── 版本更新 ──────────────────────────────────────────────────────────────────
_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
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
    script = Path(__file__).resolve().parent.parent / "update.sh"
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
