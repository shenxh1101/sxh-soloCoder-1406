from datetime import datetime, date, timedelta, time
from typing import List, Dict
from models import ScheduleSlot, PrintingMachine, OrderStatus
from scheduler import WORK_START_HOUR, WORK_END_HOUR


STATUS_BLOCKS = {
    OrderStatus.COMPLETED: '■',
    OrderStatus.IN_PRODUCTION: '█',
    OrderStatus.NOT_STARTED: '▓',
    OrderStatus.PENDING: '□',
}

STATUS_LABELS = {
    OrderStatus.COMPLETED: '已完成',
    OrderStatus.IN_PRODUCTION: '生产中',
    OrderStatus.NOT_STARTED: '未开工',
    OrderStatus.PENDING: '待排产',
}


def generate_gantt_chart(machines: List[PrintingMachine],
                         machine_schedules: Dict[str, List[ScheduleSlot]],
                         start_date: date = None,
                         end_date: date = None,
                         current_time: datetime = None) -> str:
    if current_time is None:
        current_time = datetime.now()

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
    lines.append("=" * 100)
    lines.append(title.center(100))
    lines.append("=" * 100)
    lines.append(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M')} | "
                 f"显示范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
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
        if d == current_time.date():
            date_str = f"▶{date_str}"
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

    now_line_marker = None
    if start_date <= current_time.date() <= end_date:
        day_idx = (current_time.date() - start_date).days
        if WORK_START_HOUR <= current_time.hour < WORK_END_HOUR:
            hour_offset = (current_time.hour - WORK_START_HOUR) * time_chars_per_hour
            hour_offset += int(current_time.minute / 60.0 * time_chars_per_hour)
            now_line_marker = (day_idx, hour_offset)

    for machine in machines:
        machine_line = machine.name.ljust(10)
        slots = machine_schedules.get(machine.machine_id, [])

        for day_idx, d in enumerate(date_range):
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

                order = slot.order
                status = order.status
                block_char = STATUS_BLOCKS.get(status, '█')

                order_label = order.order_id[:4]
                label_len = len(order_label)

                for i in range(start_offset, end_offset):
                    if i < start_offset + label_len:
                        day_str_list[i] = order_label[i - start_offset]
                    else:
                        day_str_list[i] = block_char

                if slot.setup_time_minutes > 0:
                    setup_start = start_offset
                    setup_end = min(start_offset + int(slot.setup_time_minutes / 60.0 * time_chars_per_hour), end_offset)
                    for i in range(setup_start, setup_end):
                        if i < len(day_str_list) and i < start_offset + label_len:
                            continue
                        if i < len(day_str_list):
                            day_str_list[i] = "░"

                if order.is_delayed and status != OrderStatus.COMPLETED:
                    mid_pos = start_offset + min(4, (end_offset - start_offset) // 2)
                    if mid_pos < time_width:
                        day_str_list[mid_pos] = '!'

            if now_line_marker and now_line_marker[0] == day_idx:
                marker_pos = min(now_line_marker[1], time_width - 1)
                if day_str_list[marker_pos] == ' ':
                    day_str_list[marker_pos] = '│'

            day_str = "".join(day_str_list)
            machine_line += "│" + day_str + "│"

        lines.append(machine_line)

    lines.append("-" * len(date_header))

    legend_parts = []
    for status, char in STATUS_BLOCKS.items():
        legend_parts.append(f"{char}{STATUS_LABELS[status]}")
    legend_parts.append("░换单")
    legend_parts.append("!延期风险")
    legend_parts.append("│当前时间")
    legend = "  图例: " + "  ".join(legend_parts)
    lines.append(legend)
    lines.append("")

    return "\n".join(lines)


def generate_daily_gantt(machines: List[PrintingMachine],
                         machine_schedules: Dict[str, List[ScheduleSlot]],
                         target_date: date,
                         current_time: datetime = None) -> str:
    if current_time is None:
        current_time = datetime.now()

    lines = []
    title = f"生产排程 - {target_date.strftime('%Y年%m月%d日')}"
    lines.append("=" * 90)
    lines.append(title.center(90))
    lines.append("=" * 90)
    lines.append(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    work_hours = WORK_END_HOUR - WORK_START_HOUR
    chars_per_hour = 4
    total_width = work_hours * chars_per_hour

    time_ruler = " " * 14
    for h in range(WORK_START_HOUR, WORK_END_HOUR):
        time_ruler += f"{h:02d}时".ljust(chars_per_hour)
    lines.append(time_ruler)

    if target_date == current_time.date():
        now_offset = (current_time.hour - WORK_START_HOUR) * chars_per_hour
        now_offset += int(current_time.minute / 60.0 * chars_per_hour)
        now_line = " " * 14 + " " * now_offset + "│"
        lines.append(now_line)
    lines.append("-" * (14 + total_width))

    for machine in machines:
        slots = machine_schedules.get(machine.machine_id, [])
        day_slots = [s for s in slots if s.start_time.date() <= target_date and s.end_time.date() >= target_date]

        machine_name = machine.name[:12].ljust(12) + " │"
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

            order = slot.order
            status = order.status
            block_char = STATUS_BLOCKS.get(status, '█')

            order_id_short = order.order_id[:6]
            label_len = len(order_id_short)

            for i in range(start_pos, end_pos):
                if i - start_pos < label_len:
                    day_chars[i] = order_id_short[i - start_pos]
                else:
                    day_chars[i] = block_char

            if slot.setup_time_minutes > 0:
                setup_minutes = min(slot.setup_time_minutes, (slot_end - slot_start).total_seconds() / 60.0)
                setup_chars = int(setup_minutes / 60.0 * chars_per_hour)
                for i in range(start_pos, min(start_pos + setup_chars, end_pos)):
                    if i < total_width and i - start_pos >= label_len:
                        day_chars[i] = "░"

            if order.is_delayed and status != OrderStatus.COMPLETED:
                mid = start_pos + min(3, (end_pos - start_pos) // 2)
                if mid < total_width and day_chars[mid] == block_char:
                    day_chars[mid] = '!'

        if target_date == current_time.date():
            now_pos = min(now_offset, total_width - 1)
            if day_chars[now_pos] == ' ':
                day_chars[now_pos] = '│'

        machine_line = machine_name + "".join(day_chars) + "│"
        lines.append(machine_line)

    lines.append("-" * (14 + total_width))
    lines.append("")
    lines.append("订单详情:")

    for machine in machines:
        slots = machine_schedules.get(machine.machine_id, [])
        day_slots = [s for s in slots if s.start_time.date() <= target_date and s.end_time.date() >= target_date]
        if day_slots:
            lines.append(f"\n【{machine.name}】")
            for slot in sorted(day_slots, key=lambda s: s.start_time):
                start_str = slot.start_time.strftime("%H:%M")
                end_str = slot.end_time.strftime("%H:%M")
                order = slot.order
                setup_info = f" (换单{slot.setup_time_minutes}分钟)" if slot.setup_time_minutes > 0 else ""
                delay_info = ""
                if order.is_delayed and order.status != OrderStatus.COMPLETED:
                    delay_info = f" ⚠延期{order.delay_days}天"
                status_info = f" [{STATUS_LABELS.get(order.status, '')}]"
                urgent_info = " [紧急]" if order.is_urgent else ""
                progress_info = ""
                if order.status == OrderStatus.IN_PRODUCTION:
                    progress_info = f" 进度:{order.progress:.0%}"

                lines.append(f"  {order.order_id}: {start_str}-{end_str} "
                             f"纸张:{order.paper_grammage}g "
                             f"印张:{order.sheet_count}{setup_info}"
                             f"{status_info}{urgent_info}{progress_info}{delay_info}")

    return "\n".join(lines)


