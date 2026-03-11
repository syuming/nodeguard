import threading
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import Device, DeviceLog
from .forms import DeviceForm
from .utils import check_device


# ── Auth ────────────────────────────────────────────────────────────────────

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


# ── Dashboard ────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    devices = Device.objects.all().order_by("name")
    total = devices.count()
    online = devices.filter(status="online").count()
    offline = devices.filter(status="offline").count()
    warning = devices.filter(status="warning").count()
    return render(request, "monitor/dashboard.html", {
        "devices": devices,
        "total": total,
        "online": online,
        "offline": offline,
        "warning": warning,
    })


# ── Device Detail ─────────────────────────────────────────────────────────────

@login_required
def device_detail(request, pk):
    device = get_object_or_404(Device, pk=pk)
    logs = device.logs.all()[:100]
    return render(request, "monitor/device_detail.html", {"device": device, "logs": logs})


# ── Device CRUD ───────────────────────────────────────────────────────────────

@login_required
def device_add(request):
    form = DeviceForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "設備已新增")
        return redirect("/")
    return render(request, "monitor/device_form.html", {"form": form, "title": "新增設備"})


@login_required
def device_edit(request, pk):
    device = get_object_or_404(Device, pk=pk)
    form = DeviceForm(request.POST or None, instance=device)
    if form.is_valid():
        form.save()
        messages.success(request, "設備已更新")
        return redirect(f"/device/{pk}/")
    return render(request, "monitor/device_form.html", {"form": form, "title": "編輯設備"})


@login_required
@require_POST
def device_delete(request, pk):
    device = get_object_or_404(Device, pk=pk)
    device.delete()
    messages.success(request, "設備已刪除")
    return redirect("/")


# ── API ───────────────────────────────────────────────────────────────────────

@login_required
def api_device_status(request):
    """Return all device statuses as JSON for polling"""
    devices = Device.objects.values("id", "name", "ip_address", "status", "last_checked")
    return JsonResponse({"devices": list(devices)})


@login_required
@require_POST
def api_check_device(request, pk):
    """Trigger a manual check for a single device"""
    device = get_object_or_404(Device, pk=pk)

    def run():
        check_device(device)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return JsonResponse({"status": "checking", "device_id": pk})


@login_required
@require_POST
def api_check_all(request):
    """Trigger check for all devices"""
    devices = Device.objects.all()

    def run():
        for d in devices:
            check_device(d)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return JsonResponse({"status": "checking", "count": devices.count()})


@login_required
def api_device_logs(request, pk):
    """Return latest 50 logs for a device as JSON"""
    device = get_object_or_404(Device, pk=pk)
    logs = list(device.logs.values("id", "level", "message", "raw_output", "created_at")[:50])
    for log in logs:
        log["created_at"] = log["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    return JsonResponse({"logs": logs})
