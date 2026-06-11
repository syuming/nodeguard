"""批量建立設備的共用邏輯（device_bulk_add 與 company_detail 共用）。"""
import logging
import re
import threading

from ..models import Device, MonitorCheck
from ..utils import check_device

_dup_logger = logging.getLogger("nodeguard.duplicate_ip")


def bulk_create_devices(post_data, company, run_initial_check=True):
    """解析 POST 中的 name_N / ip_N 列，批量建立設備。

    重複 IP（全系統範圍）自動略過並寫入 duplicate_ip.log。
    回傳 (created, errors, skipped)：
      created — 建立成功的 Device 列表（已附帶預設 ping 監控）
      errors  — 錯誤訊息字串列表（欄位不完整或建立失敗）
      skipped — 略過的重複 IP 資訊 dict 列表
    """
    row_indices = sorted({
        int(m.group(1))
        for key in post_data
        if (m := re.match(r'^name_(\d+)$', key))
    })

    created, errors, skipped = [], [], []
    for i in row_indices:
        name = post_data.get(f"name_{i}", "").strip()
        ip   = post_data.get(f"ip_{i}", "").strip()
        if not name and not ip:
            continue
        if not name or not ip:
            errors.append(f"第 {i} 筆：名稱和 IP 都必須填寫")
            continue
        existing = Device.objects.filter(ip_address=ip).select_related("company").first()
        if existing:
            skipped.append({
                "row": i, "name": name, "ip": ip,
                "existing_name": existing.name,
                "existing_company": existing.company.name if existing.company else "-",
            })
            _dup_logger.warning(
                "重複 IP 略過 | row=%d name=%s ip=%s existing=%s company=%s",
                i, name, ip, existing.name,
                existing.company.name if existing.company else "-",
            )
            continue
        try:
            device = Device.objects.create(
                name=name, ip_address=ip,
                company=company, device_type="generic",
            )
            # interval=None：跟隨持續監控的全域間隔
            MonitorCheck.objects.create(device=device, check_type="ping", interval=None, enabled=True)
            created.append(device)
        except Exception as e:
            errors.append(f"第 {i} 筆（{name} / {ip}）：{e}")

    if created and run_initial_check:
        pks = [d.pk for d in created]

        def _bg():
            for pk in pks:
                try:
                    check_device(Device.objects.get(pk=pk))
                except Exception:
                    pass
        threading.Thread(target=_bg, daemon=True).start()

    return created, errors, skipped
