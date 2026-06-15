from dataclasses import dataclass
from datetime import datetime, date, timedelta, time
from typing import List, Dict, Tuple, Optional
from models import ScheduleSlot, PrintingMachine, OrderStatus
from scheduler import WORK_START_HOUR, WORK_END_HOUR
from work_calendar import WorkCalendar, Shift, ShiftType


STATUS_BLOCKS = {
    OrderStatus.COMPLETED: '■',
    OrderStatus.IN_PRODUCTION: '█',
    OrderStatus.NOT_STARTED: '▓',
    OrderStatus.PENDING: '□',
    OrderStatus.PAUSED: '▒',
}

STATUS_LABELS = {
    OrderStatus.COMPLETED: '已完成',
    OrderStatus.IN_PRODUCTION: '生产中',
    OrderStatus.NOT_STARTED: '未开工',
    OrderStatus.PENDING: '待排产',
    OrderStatus.PAUSED: '暂停中',
}

DAY_SHIFT_BG = ' '
NIGHT_SHIFT_BG = '·'
TIME_CHARS_PER_HOUR = 2
DAILY_TIME_CHARS_PER_HOUR = 4


@dataclass
class DisplayPeriod:
    date_label: date
    shift_name: str
    shift_type: ShiftType
    start_dt: datetime
    end_dt: datetime
    is_next_day: bool
    width_hours: float


def _get_single_shift_periods(start_date: date, end_date: date) -> List[DisplayPeriod]:
    periods = []
    current = start_date
    while current <= end_date:
        start_dt = datetime.combine(current, time(WORK_START_HOUR, 0))
        end_dt = datetime.combine(current, time(WORK_END_HOUR, 0))
        periods.append(DisplayPeriod(
            date_label=current,
            shift_name='白班',
            shift_type=ShiftType.DAY,
            start_dt=start_dt,
            end_dt=end_dt,
            is_next_day=False,
            width_hours=WORK_END_HOUR - WORK_START_HOUR
        ))
        current += timedelta(days=1)
    return periods


def _get_calendar_periods(start_date: date, end_date: date,
                          calendar: WorkCalendar) -> List[DisplayPeriod]:
    periods = []
    scan_start = datetime.combine(start_date - timedelta(days=1), time(0, 0))
    scan_end = datetime.combine(end_date + timedelta(days=2), time(0, 0))
    working_periods = calendar.get_working_periods(scan_start, scan_end)

    for (s, e, shift) in working_periods:
        period_date = s.date()
        is_next_day = False
        if period_date < start_date:
            period_date = start_date
            is_next_day = True
        if period_date > end_date:
            continue
        actual_start = max(s, datetime.combine(period_date, time(0, 0)))
        actual_end = min(e, datetime.combine(period_date + timedelta(days=1), time(0, 0)))
        if actual_start >= actual_end:
            continue
        if shift.start_time > shift.end_time and e.date() > s.date():
            night_part_start = datetime.combine(s.date(), shift.start_time)
            night_part_end = datetime.combine(s.date() + timedelta(days=1), time(0, 0))
            if start_date <= s.date() <= end_date:
                periods.append(DisplayPeriod(
                    date_label=s.date(),
                    shift_name=shift.name,
                    shift_type=shift.shift_type,
                    start_dt=night_part_start,
                    end_dt=night_part_end,
                    is_next_day=False,
                    width_hours=(night_part_end - night_part_start).total_seconds() / 3600
                ))
            next_day_part_start = datetime.combine(e.date(), time(0, 0))
            next_day_part_end = datetime.combine(e.date(), shift.end_time)
            if start_date <= e.date() <= end_date:
                periods.append(DisplayPeriod(
                    date_label=e.date(),
                    shift_name=shift.name,
                    shift_type=shift.shift_type,
                    start_dt=next_day_part_start,
                    end_dt=next_day_part_end,
                    is_next_day=True,
                    width_hours=(next_day_part_end - next_day_part_start).total_seconds() / 3600
                ))
        else:
            periods.append(DisplayPeriod(
                date_label=period_date,
                shift_name=shift.name,
                shift_type=shift.shift_type,
                start_dt=actual_start,
                end_dt=actual_end,
                is_next_day=is_next_day,
                width_hours=(actual_end - actual_start).total_seconds() / 3600
            ))
    unique = {}
    for p in periods:
        key = (p.date_label, p.shift_name, p.is_next_day)
        if key not in unique:
            unique[key] = p
        else:
            existing = unique[key]
            existing.start_dt = min(existing.start_dt, p.start_dt)
            existing.end_dt = max(existing.end_dt, p.end_dt)
            existing.width_hours = (existing.end_dt - existing.start_dt).total_seconds() / 3600
    return sorted(unique.values(), key=lambda x: (x.date_label, x.start_dt))


def _is_order_delayed_calendar(order, calendar: Optional[WorkCalendar]) -> bool:
    if not order.end_time:
        return False
    if calendar is None:
        return order.is_delayed
    end_date = order.end_time.date()
    return end_date > order.delivery_date


def _format_shift_header(period: DisplayPeriod) -> str:
    marker = "(次日)" if period.is_next_day else ""
    label = f"{period.shift_name}{marker}"
    if period.shift_type == ShiftType.NIGHT:
        return f"[{label}]"
    return label


def _get_bg_char(period: DisplayPeriod) -> str:
    if period.shift_type == ShiftType.NIGHT:
        return NIGHT_SHIFT_BG
    return DAY_SHIFT_BG


def generate_gantt_chart(machines: List[PrintingMachine],
                         machine_schedules: Dict[str, List[ScheduleSlot]],
                         start_date: date = None,
                         end_date: date = None,
                         current_time: datetime = None,
                         calendar: Optional[WorkCalendar] = None) -> str:
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

    is_dual_shift = calendar is not None

    if is_dual_shift:
        display_periods = _get_calendar_periods(start_date, end_date, calendar)
    else:
        display_periods = _get_single_shift_periods(start_date, end_date)

    lines = []
    title = "印刷机生产排程甘特图"
    lines.append("=" * 120)
    lines.append(title.center(120))
    lines.append("=" * 120)
    lines.append(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M')} | "
                 f"显示范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}"
                 f"{' | 模式: 双班制' if is_dual_shift else ' | 模式: 单班制'}")
    lines.append("")

    date_range = []
    current = start_date
    while current <= end_date:
        date_range.append(current)
        current += timedelta(days=1)

    period_widths = []
    for dp in display_periods:
        w = max(2, int(round(dp.width_hours * TIME_CHARS_PER_HOUR)))
        period_widths.append(w)
    total_time_width = sum(period_widths) + 2 * len(period_widths)

    machine_col_width = 12
    date_header = "机器".ljust(machine_col_width)
    shift_header = " " * machine_col_width
    date_to_periods: Dict[date, List[Tuple[int, DisplayPeriod]]] = {}
    for idx, dp in enumerate(display_periods):
        if dp.date_label not in date_to_periods:
            date_to_periods[dp.date_label] = []
        date_to_periods[dp.date_label].append((idx, dp))

    period_idx = 0
    for d in date_range:
        if d not in date_to_periods:
            date_str = d.strftime("%m-%d")
            if d == current_time.date():
                date_str = f"▶{date_str}"
            col_w = (WORK_END_HOUR - WORK_START_HOUR) * TIME_CHARS_PER_HOUR + 2
            if is_dual_shift:
                col_w = 20
            date_header += date_str.center(col_w)
            shift_header += "休".center(col_w)
            continue
        day_periods = date_to_periods[d]
        total_w = sum(period_widths[i] + 2 for i, _ in day_periods)
        date_str = d.strftime("%m-%d")
        if d == current_time.date():
            date_str = f"▶{date_str}"
        date_header += date_str.center(total_w)
        for i, dp in day_periods:
            w = period_widths[i] + 2
            shift_header += _format_shift_header(dp).center(w)
    lines.append(date_header)
    lines.append(shift_header)
    lines.append("-" * (machine_col_width + total_time_width))

    time_ruler = " " * machine_col_width
    for idx, dp in enumerate(display_periods):
        w = period_widths[idx]
        ruler = ""
        start_h = dp.start_dt.hour + dp.start_dt.minute / 60.0
        end_h = dp.end_dt.hour + dp.end_dt.minute / 60.0
        if dp.end_dt.date() > dp.start_dt.date():
            end_h = 24
        hours_count = int(round(end_h - start_h))
        for h in range(hours_count):
            hour_val = int(start_h) + h
            display_h = hour_val % 24
            ruler += f"{display_h:2d}"
        if len(ruler) < w:
            ruler = ruler + " " * (w - len(ruler))
        elif len(ruler) > w:
            ruler = ruler[:w]
        time_ruler += " " + ruler + " "
    lines.append(time_ruler)
    lines.append("-" * (machine_col_width + total_time_width))

    now_line_markers = []
    for idx, dp in enumerate(display_periods):
        if dp.start_dt <= current_time < dp.end_dt:
            hours_from_start = (current_time - dp.start_dt).total_seconds() / 3600.0
            offset = int(hours_from_start * TIME_CHARS_PER_HOUR)
            offset = max(0, min(offset, period_widths[idx] - 1))
            now_line_markers.append((idx, offset))

    for machine in machines:
        machine_line = machine.name[:machine_col_width - 2].ljust(machine_col_width)
        slots = machine_schedules.get(machine.machine_id, [])

        for p_idx, dp in enumerate(display_periods):
            w = period_widths[p_idx]
            bg = _get_bg_char(dp)
            day_str_list = [bg] * w

            for slot in slots:
                slot_start = max(slot.start_time, dp.start_dt)
                slot_end = min(slot.end_time, dp.end_dt)
                if slot_end <= dp.start_dt or slot_start >= dp.end_dt:
                    continue

                hours_from_start = (slot_start - dp.start_dt).total_seconds() / 3600.0
                duration_hours = (slot_end - slot_start).total_seconds() / 3600.0
                start_offset = int(hours_from_start * TIME_CHARS_PER_HOUR)
                end_offset = start_offset + int(duration_hours * TIME_CHARS_PER_HOUR)
                start_offset = max(0, min(start_offset, w))
                end_offset = max(0, min(end_offset, w))

                order = slot.order
                status = order.status
                block_char = STATUS_BLOCKS.get(status, '█')
                order_label = order.order_id[:4]
                label_len = len(order_label)

                for i in range(start_offset, end_offset):
                    if i < start_offset + label_len and (end_offset - start_offset) >= label_len:
                        day_str_list[i] = order_label[i - start_offset]
                    else:
                        day_str_list[i] = block_char

                if slot.setup_time_minutes > 0:
                    setup_chars = int(slot.setup_time_minutes / 60.0 * TIME_CHARS_PER_HOUR)
                    setup_end = min(start_offset + setup_chars, end_offset)
                    for i in range(start_offset, setup_end):
                        if i < w and not (i < start_offset + label_len and (end_offset - start_offset) >= label_len):
                            if i < w:
                                day_str_list[i] = "░"

                is_delayed = _is_order_delayed_calendar(order, calendar)
                if is_delayed and status != OrderStatus.COMPLETED:
                    mid_pos = start_offset + min(4, (end_offset - start_offset) // 2)
                    if mid_pos < w:
                        day_str_list[mid_pos] = '!'

            for (m_idx, m_off) in now_line_markers:
                if m_idx == p_idx:
                    marker_pos = min(m_off, w - 1)
                    if day_str_list[marker_pos] == bg:
                        day_str_list[marker_pos] = '│'

            day_str = "".join(day_str_list)
            machine_line += "│" + day_str + "│"

        lines.append(machine_line)

    lines.append("-" * (machine_col_width + total_time_width))

    legend_parts = []
    for status, char in STATUS_BLOCKS.items():
        legend_parts.append(f"{char}{STATUS_LABELS[status]}")
    legend_parts.append("░换单")
    legend_parts.append("!延期风险")
    legend_parts.append("│当前时间")
    if is_dual_shift:
        legend_parts.append(f"{DAY_SHIFT_BG * 2}白班区域")
        legend_parts.append(f"{NIGHT_SHIFT_BG * 2}夜班区域")
    legend = "  图例: " + "  ".join(legend_parts)
    lines.append(legend)
    lines.append("")

    return "\n".join(lines)


def generate_daily_gantt(machines: List[PrintingMachine],
                         machine_schedules: Dict[str, List[ScheduleSlot]],
                         target_date: date,
                         current_time: datetime = None,
                         calendar: Optional[WorkCalendar] = None) -> str:
    if current_time is None:
        current_time = datetime.now()

    is_dual_shift = calendar is not None

    lines = []
    title = f"生产排程 - {target_date.strftime('%Y年%m月%d日')}"
    mode_str = "双班制视图" if is_dual_shift else "单班制视图"
    lines.append("=" * 110)
    lines.append(f"{title.center(110)}")
    lines.append(f"({mode_str})".center(110))
    lines.append("=" * 110)
    lines.append(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    if is_dual_shift:
        day_start = datetime.combine(target_date, time(0, 0))
        day_end = datetime.combine(target_date + timedelta(days=1), time(0, 0))
        total_hours = 24
        display_periods = _get_calendar_periods(target_date, target_date, calendar)
    else:
        work_hours = WORK_END_HOUR - WORK_START_HOUR
        total_hours = work_hours
        day_start = datetime.combine(target_date, time(WORK_START_HOUR, 0))
        day_end = datetime.combine(target_date, time(WORK_END_HOUR, 0))
        display_periods = _get_single_shift_periods(target_date, target_date)

    chars_per_hour = DAILY_TIME_CHARS_PER_HOUR
    total_width = int(total_hours * chars_per_hour)

    shift_bg_map = {}
    for dp in display_periods:
        start_offset = int((dp.start_dt - day_start).total_seconds() / 3600.0 * chars_per_hour)
        end_offset = int((dp.end_dt - day_start).total_seconds() / 3600.0 * chars_per_hour)
        bg = _get_bg_char(dp)
        for i in range(max(0, start_offset), min(total_width, end_offset)):
            shift_bg_map[i] = (bg, dp)

    time_ruler = " " * 16
    shift_ruler = " " * 16
    base_hour = 0 if is_dual_shift else WORK_START_HOUR
    for h in range(int(total_hours)):
        display_h = base_hour + h
        time_ruler += f"{display_h:02d}时".ljust(chars_per_hour)

    if is_dual_shift:
        for i in range(total_width):
            if i in shift_bg_map:
                bg, dp = shift_bg_map[i]
                center_pos = i % chars_per_hour
                if center_pos == 0:
                    shift_ruler += dp.shift_name[0] if dp.shift_name else " "
                else:
                    shift_ruler += bg
            else:
                shift_ruler += " "
        lines.append(shift_ruler)
    lines.append(time_ruler)

    now_offset = None
    if target_date == current_time.date():
        if is_dual_shift:
            hours_from_start = (current_time - day_start).total_seconds() / 3600.0
            if 0 <= hours_from_start < 24:
                now_offset = int(hours_from_start * chars_per_hour)
        else:
            if WORK_START_HOUR <= current_time.hour < WORK_END_HOUR:
                now_offset = (current_time.hour - WORK_START_HOUR) * chars_per_hour
                now_offset += int(current_time.minute / 60.0 * chars_per_hour)

    if now_offset is not None:
        now_line = " " * 16 + " " * now_offset + "│"
        lines.append(now_line)
    lines.append("-" * (16 + total_width))

    for machine in machines:
        slots = machine_schedules.get(machine.machine_id, [])
        day_slots = [s for s in slots if s.start_time < day_end and s.end_time > day_start]

        machine_name = machine.name[:14].ljust(14) + " │"
        default_bg = DAY_SHIFT_BG if not is_dual_shift else " "
        day_chars = [default_bg] * total_width

        if is_dual_shift:
            for i in range(total_width):
                if i in shift_bg_map:
                    day_chars[i] = shift_bg_map[i][0]

        for slot in day_slots:
            slot_start = max(slot.start_time, day_start)
            slot_end = min(slot.end_time, day_end)
            if slot_start >= slot_end:
                continue

            hours_from_start = (slot_start - day_start).total_seconds() / 3600.0
            duration_hours = (slot_end - slot_start).total_seconds() / 3600.0
            start_pos = int(hours_from_start * chars_per_hour)
            end_pos = start_pos + int(duration_hours * chars_per_hour)
            start_pos = max(0, min(start_pos, total_width))
            end_pos = max(0, min(end_pos, total_width))

            order = slot.order
            status = order.status
            block_char = STATUS_BLOCKS.get(status, '█')
            order_id_short = order.order_id[:6]
            label_len = len(order_id_short)

            for i in range(start_pos, end_pos):
                if i - start_pos < label_len and (end_pos - start_pos) >= label_len:
                    day_chars[i] = order_id_short[i - start_pos]
                else:
                    day_chars[i] = block_char

            if slot.setup_time_minutes > 0:
                setup_minutes = min(slot.setup_time_minutes, (slot_end - slot_start).total_seconds() / 60.0)
                setup_chars = int(setup_minutes / 60.0 * chars_per_hour)
                for i in range(start_pos, min(start_pos + setup_chars, end_pos)):
                    if i < total_width and not (i - start_pos < label_len and (end_pos - start_pos) >= label_len):
                        day_chars[i] = "░"

            is_delayed = _is_order_delayed_calendar(order, calendar)
            if is_delayed and status != OrderStatus.COMPLETED:
                mid = start_pos + min(3, (end_pos - start_pos) // 2)
                if mid < total_width:
                    day_chars[mid] = '!'

        if now_offset is not None:
            now_pos = min(now_offset, total_width - 1)
            if day_chars[now_pos] in (DAY_SHIFT_BG, NIGHT_SHIFT_BG, " "):
                day_chars[now_pos] = '│'

        machine_line = machine_name + "".join(day_chars) + "│"
        lines.append(machine_line)

    lines.append("-" * (16 + total_width))
    lines.append("")
    lines.append("订单详情:")

    for machine in machines:
        slots = machine_schedules.get(machine.machine_id, [])
        day_slots = [s for s in slots if s.start_time < day_end and s.end_time > day_start]
        if day_slots:
            lines.append(f"\n【{machine.name}】")
            for slot in sorted(day_slots, key=lambda s: s.start_time):
                start_str = slot.start_time.strftime("%H:%M")
                end_str = slot.end_time.strftime("%H:%M")
                order = slot.order
                setup_info = f" (换单{slot.setup_time_minutes}分钟)" if slot.setup_time_minutes > 0 else ""
                delay_info = ""
                is_delayed = _is_order_delayed_calendar(order, calendar)
                if is_delayed and order.status != OrderStatus.COMPLETED:
                    delay_info = f" ⚠延期{order.delay_days}天"
                status_info = f" [{STATUS_LABELS.get(order.status, '')}]"
                urgent_info = " [紧急]" if order.is_urgent else ""
                progress_info = ""
                if order.status == OrderStatus.IN_PRODUCTION:
                    progress_info = f" 进度:{order.progress:.0%}"

                shift_info = ""
                if is_dual_shift:
                    if order.start_shift and order.end_shift and order.start_shift != order.end_shift:
                        shift_info = f" 班次:{order.start_shift}→{order.end_shift}"
                    elif order.start_shift:
                        shift_info = f" 班次:{order.start_shift}"
                    elif order.shift:
                        shift_info = f" 班次:{order.shift}"

                lines.append(f"  {order.order_id}: {start_str}-{end_str} "
                             f"纸张:{order.paper_grammage}g "
                             f"印张:{order.sheet_count}{setup_info}"
                             f"{status_info}{urgent_info}{progress_info}{delay_info}{shift_info}")

    legend_parts = []
    for status, char in STATUS_BLOCKS.items():
        legend_parts.append(f"{char}{STATUS_LABELS[status]}")
    legend_parts.append("░换单")
    legend_parts.append("!延期风险")
    legend_parts.append("│当前时间")
    if is_dual_shift:
        legend_parts.append(f"{DAY_SHIFT_BG * 2}白班")
        legend_parts.append(f"{NIGHT_SHIFT_BG * 2}夜班")
    lines.append("")
    lines.append("  图例: " + "  ".join(legend_parts))
    lines.append("")

    return "\n".join(lines)
