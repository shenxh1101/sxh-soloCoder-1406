from datetime import datetime, date, timedelta, time
from typing import List, Dict
from models import ScheduleSlot, PrintingMachine
from scheduler import WORK_START_HOUR, WORK_END_HOUR


def generate_gantt_chart(machines: List[PrintingMachine],
                         machine_schedules: Dict[str, List[ScheduleSlot]],
                         start_date: date = None,
                         end_date: date = None) -> str:
    if start_date is None or end_date is None:
        all_dates = []
        for slots in machine_schedules.values():
            for slot in slots:
                all_dates.append(slot.start_time.date())
                all_dates.append(slot.end_time.date())
        if all_dates:
            start_date = min(all_dates)
            end_date = max(all_dates)
        else:
            start_date = date.today()
            end_date = date.today()

    lines = []
    title = "印刷机生产排程甘特图"
    lines.append("=" * 80)
    lines.append(title.center(80))
    lines.append("=" * 80)
    lines.append("")

    date_range = []
    current = start_date
    while current <= end_date:
        date_range.append(current)
        current += timedelta(days=1)

    time_chars_per_hour = 2
    work_hours = WORK_END_HOUR - WORK_START_HOUR
    time_width = work_hours * time_chars_per_hour

    date_header = "机器".ljust(10)
    for d in date_range:
        date_str = d.strftime("%m-%d")
        date_header += date_str.center(time_width + 2)
    lines.append(date_header)
    lines.append("-" * len(date_header))

    time_ruler = " " * 10
    for d in date_range:
        ruler = ""
        for h in range(WORK_START_HOUR, WORK_END_HOUR):
            ruler += f"{h:2d}"
        time_ruler += " " + ruler + " "
    lines.append(time_ruler)
    lines.append("-" * len(date_header))

    for machine in machines:
        machine_line = machine.name.ljust(10)
        slots = machine_schedules.get(machine.machine_id, [])

        for d in date_range:
            day_start = datetime.combine(d, time(WORK_START_HOUR, 0))
            day_end = datetime.combine(d, time(WORK_END_HOUR, 0))

            day_str_list = [" "] * time_width

            for slot in slots:
                slot_start = max(slot.start_time, day_start)
                slot_end = min(slot.end_time, day_end)

                if slot_end <= day_start or slot_start >= day_end:
                    continue

                start_offset = int((slot_start - day_start).total_seconds() / 3600.0 * time_chars_per_hour)
                end_offset = int((slot_end - day_start).total_seconds() / 3600.0 * time_chars_per_hour)
                start_offset = max(0, min(start_offset, time_width))
                end_offset = max(0, min(end_offset, time_width))

                order_label = slot.order.order_id[:4]
                label_len = len(order_label)

                for i in range(start_offset, end_offset):
                    if i < start_offset + label_len:
                        day_str_list[i] = order_label[i - start_offset]
                    else:
                        day_str_list[i] = "█"

                if slot.setup_time_minutes > 0 and slot.start_time >= day_start and slot.start_time < day_end:
                    setup_start = start_offset
                    setup_end = min(start_offset + int(slot.setup_time_minutes / 60.0 * time_chars_per_hour), end_offset)
                    for i in range(setup_start, setup_end):
                        if i < len(day_str_list):
                            day_str_list[i] = "░"

            day_str = "".join(day_str_list)
            machine_line += "│" + day_str + "│"

        lines.append(machine_line)

    lines.append("-" * len(date_header))

    legend = "图例: █生产中 ░换单准备  状态: "
    lines.append(legend)
    lines.append("")

    return "\n".join(lines)


def generate_daily_gantt(machines: List[PrintingMachine],
                         machine_schedules: Dict[str, List[ScheduleSlot]],
                         target_date: date) -> str:
    lines = []
    title = f"生产排程 - {target_date.strftime('%Y年%m月%d日')}"
    lines.append("=" * 80)
    lines.append(title.center(80))
    lines.append("=" * 80)
    lines.append("")

    work_hours = WORK_END_HOUR - WORK_START_HOUR
    chars_per_hour = 4
    total_width = work_hours * chars_per_hour

    time_ruler = " " * 12
    for h in range(WORK_START_HOUR, WORK_END_HOUR):
        time_ruler += f"{h:02d}时".ljust(chars_per_hour)
    lines.append(time_ruler)
    lines.append("-" * (12 + total_width))

    for machine in machines:
        slots = machine_schedules.get(machine.machine_id, [])
        day_slots = [s for s in slots if s.start_time.date() <= target_date and s.end_time.date() >= target_date]

        machine_name = machine.name[:10].ljust(10) + " │"
        day_chars = [" "] * total_width

        day_start = datetime.combine(target_date, time(WORK_START_HOUR, 0))
        day_end = datetime.combine(target_date, time(WORK_END_HOUR, 0))

        for slot in day_slots:
            slot_start = max(slot.start_time, day_start)
            slot_end = min(slot.end_time, day_end)

            start_pos = int((slot_start - day_start).total_seconds() / 3600.0 * chars_per_hour)
            end_pos = int((slot_end - day_start).total_seconds() / 3600.0 * chars_per_hour)
            start_pos = max(0, min(start_pos, total_width))
            end_pos = max(0, min(end_pos, total_width))

            order_id_short = slot.order.order_id[:6]
            label_len = len(order_id_short)

            for i in range(start_pos, end_pos):
                if i - start_pos < label_len:
                    day_chars[i] = order_id_short[i - start_pos]
                else:
                    day_chars[i] = "█"

            if slot.setup_time_minutes > 0:
                setup_minutes = min(slot.setup_time_minutes, (slot_end - slot_start).total_seconds() / 60.0)
                setup_chars = int(setup_minutes / 60.0 * chars_per_hour)
                for i in range(start_pos, min(start_pos + setup_chars, end_pos)):
                    if i < total_width:
                        day_chars[i] = "░"

        machine_line = machine_name + "".join(day_chars) + "│"
        lines.append(machine_line)

    lines.append("-" * (12 + total_width))
    lines.append("")
    lines.append("订单详情:")

    for machine in machines:
        slots = machine_schedules.get(machine.machine_id, [])
        day_slots = [s for s in slots if s.start_time.date() <= target_date and s.end_time.date() >= target_date]
        if day_slots:
            lines.append(f"\n【{machine.name}】")
            for slot in day_slots:
                start_str = slot.start_time.strftime("%H:%M")
                end_str = slot.end_time.strftime("%H:%M")
                order = slot.order
                setup_info = f" (换单{slot.setup_time_minutes}分钟)" if slot.setup_time_minutes > 0 else ""
                lines.append(f"  {order.order_id}: {start_str}-{end_str} "
                             f"纸张:{order.paper_grammage}g "
                             f"印张:{order.sheet_count}{setup_info}")

    return "\n".join(lines)


