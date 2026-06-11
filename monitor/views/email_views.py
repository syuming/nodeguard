"""Email 設定與測試寄送（僅系統管理者）。"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ..models import EmailConfig
from ..utils import send_email_with_config
from .helpers import get_profile


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
