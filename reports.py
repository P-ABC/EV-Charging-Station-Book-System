"""reports.py — สร้างรายงาน .txt 3 ชุดจากข้อมูลไบนารี

รายงานทั้ง 3 ไฟล์
----------------
1. ``report_points.txt`` — สถานะหัวชาร์จรายหัว
2. ``report_stats.txt``  — สถิติราคา กำลังไฟ และกิจกรรม
3. ``report_system.txt`` — สถานะระบบไฟล์และดัชนี

รายงาน ``report_stats.txt`` แสดงเฉพาะตารางกิจกรรมล่าสุด (TABLE 2)
และ Summary; รายงานอื่นแสดงตารางข้อมูลและ Summary

ทุกไฟล์อ้างอิงข้อมูลจาก 3 ไฟล์ไบนารีเสมอ (เกณฑ์ข้อ 3):
``charge_points.dat`` + ``charge_points.log`` + ``index.dat``

ข้อความในตารางเป็นภาษาอังกฤษเพื่อให้แนวคอลัมน์ตรงกันใน text editors
ที่จัดวางสระและวรรณยุกต์ภาษาไทยต่างกัน
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import models
from report import (
    RECENT_ACTIVITY_LIMIT,
    alignment_mode_name,
    compute_summary,
    format_timestamp,
    measure,
    render_table,
    set_alignment_mode,
    truncate_to_width,
)

# ---------------------------------------------------------------------------
# ค่าคงที่ชื่อไฟล์และแหล่งที่มาของข้อมูล
# ---------------------------------------------------------------------------
REPORT_POINTS_NAME = "report_points.txt"
REPORT_STATS_NAME = "report_stats.txt"
REPORT_SYSTEM_NAME = "report_system.txt"
ALL_REPORT_NAMES = (REPORT_POINTS_NAME, REPORT_STATS_NAME, REPORT_SYSTEM_NAME)

SOURCE_POINT_FILE = models.DATA_FILE_NAME
SOURCE_LOG_FILE = models.LOG_FILE_NAME
SOURCE_INDEX_FILE = models.INDEX_FILE_NAME

# ความกว้างสูงสุดของตารางข้อมูลหัวชาร์จและช่องสถานที่
MAIN_TABLE_MAX_WIDTH = 190
MAIN_TABLE_LOCATION_WIDTH = 70

_LOCATION_LABELS = {
    "สยามพารากอน ชั้น B1": "Siam Paragon, Level B1",
    "เซ็นทรัลเวิลด์ ลาน P2": "CentralWorld, Parking P2",
    "ICONSIAM ชั้น G": "ICONSIAM, Level G",
    "เมกาบางนา โซน A": "Mega Bangna, Zone A",
    "เซ็นทรัลพระราม 9": "Central Rama 9",
    "บิกกิ้ง สาทร ชั้น 2": "Biking Sathorn, Level 2",
    "ลาดพร้าว ไทยรัฐ 2": "Lat Phrao, Thairath 2",
    "เอเชีย เซนเทอร์ ชั้น G": "Asia Center, Level G",
    "เซ็นทรัล พหมโพธิยา": "Central Phom Phothiya",
    "พารากอน โครงการเก่า": "Paragon, Former Project",
    "สถานีชาร์จไฟฟ้าสยามพารากอนชั้นใต้ดินโครงการใหม่และลานจอดรถ":
        "Siam Paragon EV Station, New Basement Project and Parking Lot",
}


def _full_location(point: models.ChargePoint,
                   locations: Optional[Dict[int, str]]) -> str:
    """คืนชื่อสถานที่ตั้งแบบเต็มของ record สำหรับแสดงในรายงาน"""
    if locations:
        full = locations.get(point.point_id)
        if full:
            return full
    return point.location


def english_location_label(location: str) -> Optional[str]:
    """Return a known English location label, or None for custom locations."""
    return _LOCATION_LABELS.get(location)


def _header(data_dir: str) -> List[str]:
    """สร้างส่วนหัวของรายงาน"""
    return [
        f"Generated At : {format_timestamp(models.now_timestamp())}",
        f"App Version  : {models.APP_VERSION}",
        f"Endianness   : {models.BYTE_ORDER_LABEL}",
        f"Encoding     : {models.ENCODING_LABEL} (ไฟล์รายงานใช้ UTF-8)",
        f"Data Dir     : {data_dir}",
    ]


def _rule(width: int) -> str:
    """สร้างเส้นคั่นหัวข้อ"""
    return "-" * width


def _summary_section(summary_rows: Sequence[Sequence[str]]) -> List[str]:
    """สร้างส่วนสรุปของรายงาน"""
    return [
        "[SUMMARY] Summary",
        "-" * 62,
        *render_table(["Item", "Value"], list(summary_rows)),
    ]


def _align_section_rules(lines: Sequence[str]) -> List[str]:
    """ปรับเส้นคั่นหัวข้อให้ยาวเท่ากับตารางที่อยู่ถัดไป"""
    result = list(lines)
    index = 0

    while index < len(result) - 1:
        line = result[index]

        if (line.lstrip().startswith("[")
                and not line.startswith(("+", "|"))
                and result[index + 1]
                and set(result[index + 1]) == {"-"}):
            
            rule_index = index + 1
            cursor = rule_index + 1
            table_start = None

            while cursor < len(result):
                current = result[cursor]

                if current.startswith(("+", "|")):
                    table_start = cursor
                    break

                if current.lstrip().startswith("["):
                    break

                cursor += 1

            table_width = 0

            if table_start is not None:
                cursor = table_start

                while (cursor < len(result)
                       and result[cursor].startswith(("+", "|"))):
                    table_width = max(
                        table_width,
                        measure(result[cursor])
                    )
                    cursor += 1

            target_width = (
                table_width
                if table_width
                else measure(line)
            )

            if table_width and len(result[rule_index]) != target_width:
                result[rule_index] = _rule(target_width)

            index = cursor
            continue

        index += 1

    return result


def _write_report(path: str, lines: Sequence[str]) -> str:
    """เขียนรายงานลงไฟล์ .txt"""
    content = "\n".join(_align_section_rules(lines)) + "\n"

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())

    return content


def build_report_points(data_dir: str,
                        points: Sequence[models.ChargePoint],
                        log_entries: Sequence[models.LogEntry],
                        index_map: Dict[int, int],
                        store_valid: bool = True,
                        log_valid: bool = True,
                        index_valid: bool = True,
                        locations: Optional[Dict[int, str]] = None
                        ) -> List[str]:
    """สร้างรายงานชุดที่ 1: สถานะหัวชาร์จรายหัว"""

    summary = compute_summary(points)

    # หาเวลา UPDATE ล่าสุดของแต่ละ Point จาก charge_points.log
    latest_update = {}

    for entry in log_entries:
        if entry.op_code == models.OP_UPDATE:
            latest_update[entry.point_id] = entry.ts

    lines = _header(data_dir)
    lines.append("")

    # ---- ตารางข้อมูลจริง --------------------------------------------
    lines.append("[TABLE 1] All charging points (including deleted records)")
    lines.append("-" * 62)

    rows = []

    for point in points:
        location = _full_location(point, locations)
        english_location = english_location_label(location)
        table_location = english_location or location

        rows.append([
            str(point.point_id),
            point.station_code,
            truncate_to_width(
                table_location,
                MAIN_TABLE_LOCATION_WIDTH
            ),
            point.plug_type,
            f"{point.power_kw:.1f}",
            f"{point.price_per_kwh:.2f}",
            point.status_text,
            point.booked_text,
            format_timestamp(
                latest_update.get(
                    point.point_id,
                    point.updated_at
                )
            ).replace(" (+07:00)", ""),
        ])

    lines.extend(render_table(
        [
            "PtID",
            "Station",
            "Location",
            "Plug",
            "Power",
            "Price",
            "Status",
            "Booked",
            "Updated",
        ],
        rows,
        max_width=MAIN_TABLE_MAX_WIDTH
    ))

    lines.append("")

    # ---- ส่วนสรุป ---------------------------------------------------
    inactive = [
        p for p in points
        if not p.is_deleted and p.status != 1
    ]

    booked_active = [
        p for p in points
        if not p.is_deleted
        and p.status == 1
        and p.is_booked == 1
    ]

    summary_rows = [
        ["Total Points (records)", str(summary["total"])],
        ["Active Points", str(summary["active"])],
        ["Inactive Points (maintenance)", str(len(inactive))],
        ["Deleted Points (soft delete)", str(summary["deleted"])],
        ["Currently Booked (all statuses)", str(summary["booked"])],
        ["Booked Active Points", str(len(booked_active))],
        ["Available Now (Active & not booked)",
         str(summary["available"])],
        ["Free Slots (reuseable)", str(summary["free_slots"])],
        [f"Records in {SOURCE_INDEX_FILE}",
         f"{len(index_map)} records"],
        ["Binary sources (.dat)",
         f"{SOURCE_POINT_FILE}, {SOURCE_INDEX_FILE}"],
        ["Source files",
         f"{SOURCE_POINT_FILE}, {SOURCE_LOG_FILE}, {SOURCE_INDEX_FILE}"],
    ]

    lines.extend(_summary_section(summary_rows))

    return lines


def build_report_stats(data_dir: str,
                       points: Sequence[models.ChargePoint],
                       log_entries: Sequence[models.LogEntry],
                       index_map: Dict[int, int],
                       store_valid: bool = True,
                       log_valid: bool = True,
                       index_valid: bool = True,
                       locations: Optional[Dict[int, str]] = None
                       ) -> List[str]:
    """สร้างรายงานชุดที่ 2: สถิติราคา กำลังไฟ และกิจกรรม"""

    active_points = [
        p for p in points
        if not p.is_deleted and p.status == 1
    ]

    powers = [p.power_kw for p in active_points]
    prices = [p.price_per_kwh for p in active_points]

    count = len(active_points)

    stats = {"count": count}

    if powers:
        stats["min"] = min(powers)
        stats["max"] = max(powers)
        stats["avg"] = sum(powers) / len(powers)
        stats["price_avg"] = sum(prices) / len(prices)
    else:
        stats["min"] = 0.0
        stats["max"] = 0.0
        stats["avg"] = 0.0
        stats["price_avg"] = 0.0

    plug_counts: Dict[str, int] = {}

    for point in active_points:
        plug_counts[point.plug_type] = (
            plug_counts.get(point.plug_type, 0) + 1
        )

    op_counts = {
        models.OP_ADD: 0,
        models.OP_UPDATE: 0,
        models.OP_DELETE: 0,
        models.OP_VIEW: 0,
    }

    for entry in log_entries:
        if entry.op_code in op_counts:
            op_counts[entry.op_code] += 1

    recent = list(
        log_entries[-RECENT_ACTIVITY_LIMIT:]
    )

    points_by_id = {
        p.point_id: p
        for p in points
    }

    lines = _header(data_dir)
    lines.append("")

    # ---- TABLE 2: Recent log activity ----------------------------------
    lines.append(
        f"[TABLE 2] Recent activity from {SOURCE_LOG_FILE} "
        f"(latest {len(recent)} records)"
    )
    lines.append("-" * 62)

    recent_rows = []

    for entry in sorted(
        recent,
        key=lambda item: item.ts,
        reverse=True
    ):
        point = points_by_id.get(entry.point_id)

        recent_rows.append([
            format_timestamp(entry.ts),
            entry.op_name,
            str(entry.point_id),
            point.status_text if point else "-",
            point.booked_text if point else "-",
            f"{point.price_per_kwh:.2f}" if point else "-",
            (
                "Found in index"
                if entry.point_id in index_map
                else "Missing from index"
            ),
        ])

    lines.extend(render_table(
        [
            "Timestamp",
            "Operation",
            "PtID",
            "Status",
            "Booked",
            "Price",
            "Index check",
        ],
        recent_rows
    ))

    lines.append("")

    # ---- Summary -------------------------------------------------------
    summary_rows = [
        ["Recent Activity Records", str(len(recent))],
        ["Total Log Events", str(len(log_entries))],
        ["ADD Events", str(op_counts[models.OP_ADD])],
        ["UPDATE Events", str(op_counts[models.OP_UPDATE])],
        ["DELETE Events", str(op_counts[models.OP_DELETE])],
        ["VIEW Events", str(op_counts[models.OP_VIEW])],
        [
            "Events Found in Index",
            str(sum(
                1
                for entry in recent
                if entry.point_id in index_map
            )),
        ],
        [
            "Events Missing from Index",
            str(sum(
                1
                for entry in recent
                if entry.point_id not in index_map
            )),
        ],
        [
            f"Records in {SOURCE_INDEX_FILE}",
            f"{len(index_map)} records",
        ],
        [
            "Source files",
            f"{SOURCE_POINT_FILE}, "
            f"{SOURCE_LOG_FILE}, "
            f"{SOURCE_INDEX_FILE}",
        ],
    ]

    lines.extend(_summary_section(summary_rows))

    return lines


def build_report_system(
    data_dir: str,
    points: Sequence[models.ChargePoint],
    log_entries: Sequence[models.LogEntry],
    index_map: Dict[int, int],
    store_valid: bool = True,
    log_valid: bool = True,
    index_valid: bool = True,
    locations: Optional[Dict[int, str]] = None
) -> List[str]:
    """สร้างรายงานชุดที่ 3: สถานะระบบและความพร้อมใช้งานของจุดชาร์จ"""

    # จุดชาร์จที่ยังไม่ถูกลบ
    active_points = [
        point for point in points
        if not point.is_deleted
    ]

    # จุดที่ Active และยังว่าง
    available_points = [
        point for point in active_points
        if point.status == 1
        and point.is_booked == 0
    ]

    # จุดที่ Active และกำลังถูกจอง
    booked_points = [
        point for point in active_points
        if point.status == 1
        and point.is_booked == 1
    ]

    # จุดที่ไม่พร้อมใช้งาน
    inactive_points = [
        point for point in active_points
        if point.status != 1
    ]

    # จำนวนจุดที่ถูกลบ
    deleted_points = [
        point for point in points
        if point.is_deleted
    ]

    lines = _header(data_dir)
    lines.append("")

    # ---------------------------------------------------------------
    # รายละเอียดรายงาน
    # ---------------------------------------------------------------
    lines.append("[REPORT] Charging Point Availability & System Status")
    lines.append("-" * 62)
    lines.append(
        "This report shows the current availability and status "
        "of charging points."
    )
    lines.append(
        "Deleted charging points are excluded from the availability table."
    )
    lines.append("")

    # ---------------------------------------------------------------
    # TABLE 1
    # ---------------------------------------------------------------
    lines.append("[TABLE 1] Current Charging Point Status")
    lines.append("-" * 62)

    rows = []

    for point in active_points:

        location = _full_location(point, locations)
        english_location = english_location_label(location)
        table_location = english_location or location

        if point.status != 1:
            status_text = "Inactive"
            booking_text = "-"
        elif point.is_booked == 1:
            status_text = "Active"
            booking_text = "Booked"
        else:
            status_text = "Active"
            booking_text = "Available"

        rows.append([
            str(point.point_id),
            point.station_code,
            truncate_to_width(
                table_location,
                MAIN_TABLE_LOCATION_WIDTH
            ),
            point.plug_type,
            f"{point.power_kw:.1f}",
            f"{point.price_per_kwh:.2f}",
            status_text,
            booking_text,
        ])

    lines.extend(render_table(
        [
            "PtID",
            "Station",
            "Location",
            "Plug",
            "Power",
            "Price",
            "Status",
            "Booking",
        ],
        rows,
        max_width=MAIN_TABLE_MAX_WIDTH
    ))

    lines.append("")

    # ---------------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------------
    summary_rows = [
        [
            "Active Charging Points",
            str(len(active_points))
        ],
        [
            "Available Now",
            str(len(available_points))
        ],
        [
            "Currently Booked",
            str(len(booked_points))
        ],
        [
            "Inactive Points",
            str(len(inactive_points))
        ],
        [
            "Deleted Points",
            str(len(deleted_points))
        ],
        [
            "Log Events",
            str(len(log_entries))
        ],
        [
            f"Records in {SOURCE_INDEX_FILE}",
            str(len(index_map))
        ],
        [
            "Binary sources",
            f"{SOURCE_POINT_FILE}, "
            f"{SOURCE_LOG_FILE}, "
            f"{SOURCE_INDEX_FILE}"
        ],
        [
            "Source files",
            f"{SOURCE_POINT_FILE}, "
            f"{SOURCE_LOG_FILE}, "
            f"{SOURCE_INDEX_FILE}"
        ],
    ]

    lines.extend(_summary_section(summary_rows))

    return lines


def generate_all_reports(data_dir: str,
                         points: Sequence[models.ChargePoint],
                         log_entries: Sequence[models.LogEntry],
                         index_map: Dict[int, int],
                         store_valid: bool = True,
                         log_valid: bool = True,
                         index_valid: bool = True,
                         locations: Optional[Dict[int, str]] = None
                         ) -> Dict[str, str]:
    """สร้างรายงานทั้ง 3 ชุดเป็นไฟล์ .txt แยกกัน"""

    builders = (
        (REPORT_POINTS_NAME, build_report_points),
        (REPORT_STATS_NAME, build_report_stats),
        (REPORT_SYSTEM_NAME, build_report_system),
    )

    created: Dict[str, str] = {}

    previous_alignment = alignment_mode_name()
    set_alignment_mode(True)

    try:
        for file_name, builder in builders:
            path = os.path.join(data_dir, file_name)

            lines = builder(
                data_dir,
                points,
                log_entries,
                index_map,
                store_valid=store_valid,
                log_valid=log_valid,
                index_valid=index_valid,
                locations=locations,
            )

            _write_report(path, lines)
            created[file_name] = path

    finally:
        set_alignment_mode(
            previous_alignment == "smart"
        )

    return created


def report_uses_multiple_sources(file_name: str) -> bool:
    """ตรวจว่ารายงานชุดนี้ดึงข้อมูลจากไฟล์อย่างน้อย 2 ไฟล์"""

    return file_name in ALL_REPORT_NAMES