"""首頁儀表板。"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..models import Company, Device
from .helpers import get_profile, get_visible_devices


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

    orphan_count = Device.objects.filter(company__isnull=True).count() if profile.is_admin else 0

    return render(request, "monitor/dashboard.html", {
        "total": total,
        "online": online,
        "offline": offline,
        "warning": warning,
        "alerts": alerts,
        "profile": profile,
        "company_stats": company_stats,
        "orphan_count": orphan_count,
    })
