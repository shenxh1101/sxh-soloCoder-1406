from datetime import datetime, date, timedelta, time
from typing import List, Dict, Tuple, Optional
from models import Order, PrintingMachine, ScheduleSlot, OrderStatus


SETUP_TIME_MINUTES = 30
WORK_START_HOUR = 8
WORK_END_HOUR = 20


def get_work_start(dt: datetime) -> datetime:
    return datetime.combine(dt.date(), time(WORK_START_HOUR, 0))


def get_work_end(dt: datetime) -> datetime:
    return datetime.combine(dt.date(), time(WORK_END_HOUR, 0))


def is_within_work_hours(dt: datetime) -> bool:
    return WORK_START_HOUR <= dt.hour < WORK_END_HOUR


def add_work_hours(start_dt: datetime, hours: float) -> datetime:
    current = start_dt
    remaining_hours = hours

    while remaining_hours > 0:
        if current.hour >= WORK_END_HOUR:
            current = datetime.combine(current.date() + timedelta(days=1), time(WORK_START_HOUR, 0))
            continue
        if current.hour < WORK_START_HOUR:
            current = datetime.combine(current.date(), time(WORK_START_HOUR, 0))
            continue

        day_end = get_work_end(current)
        available_hours = (day_end - current).total_seconds() / 3600.0

        if remaining_hours <= available_hours:
            current += timedelta(hours=remaining_hours)
            remaining_hours = 0
        else:
            remaining_hours -= available_hours
            current = datetime.combine(current.date() + timedelta(days=1), time(WORK_START_HOUR, 0))

    return current


class ProductionScheduler:
    def __init__(self, machines: List[PrintingMachine]):
        self.machines = machines
        self.machine_schedules: Dict[str, List[ScheduleSlot]] = {m.machine_id: [] for m in machines}
        self.orders: List[Order] = []

    def add_order(self, order: Order) -> None:
        self.orders.append(order)

    def remove_order(self, order_id: str) -> bool:
        for i, order in enumerate(self.orders):
            if order.order_id == order_id:
                if order.status not in (OrderStatus.COMPLETED, OrderStatus.IN_PRODUCTION):
                    self.orders.pop(i)
                    return True
                else:
                    return False
        return False

    def get_available_machines(self, order: Order) -> List[PrintingMachine]:
        return [m for m in self.machines if m.can_print(order.paper_grammage)]

    def update_order_status_by_time(self, current_time: datetime = None) -> Dict[str, int]:
        if current_time is None:
            current_time = datetime.now()

        stats = {
            'started': 0,
            'completed': 0,
            'no_change': 0
        }

        for order in self.orders:
            if order.status == OrderStatus.COMPLETED:
                stats['no_change'] += 1
                continue

            if order.status == OrderStatus.IN_PRODUCTION:
                if order.actual_end and order.actual_end <= current_time:
                    order.status = OrderStatus.COMPLETED
                    order.completed_sheets = order.sheet_count
                    stats['completed'] += 1
                else:
                    stats['no_change'] += 1
                continue

            if order.status == OrderStatus.NOT_STARTED:
                if order.actual_start and order.actual_start <= current_time:
                    order.status = OrderStatus.IN_PRODUCTION
                    stats['started'] += 1
                elif (order.scheduled_start and order.scheduled_start <= current_time
                      and (order.scheduled_end is None or order.scheduled_end > current_time)):
                    order.status = OrderStatus.IN_PRODUCTION
                    stats['started'] += 1
                elif order.scheduled_end and order.scheduled_end <= current_time:
                    order.status = OrderStatus.COMPLETED
                    order.completed_sheets = order.sheet_count
                    stats['completed'] += 1
                else:
                    stats['no_change'] += 1
                continue

            stats['no_change'] += 1

        return stats

    def mark_order_started(self, order_id: str, start_time: datetime = None) -> bool:
        if start_time is None:
            start_time = datetime.now()

        for order in self.orders:
            if order.order_id == order_id:
                if order.status == OrderStatus.COMPLETED:
                    return False
                order.actual_start = start_time
                order.status = OrderStatus.IN_PRODUCTION
                return True
        return False

    def mark_order_completed(self, order_id: str, end_time: datetime = None, completed_sheets: int = None) -> bool:
        if end_time is None:
            end_time = datetime.now()

        for order in self.orders:
            if order.order_id == order_id:
                order.actual_end = end_time
                if completed_sheets is not None:
                    order.completed_sheets = completed_sheets
                else:
                    order.completed_sheets = order.sheet_count
                order.status = OrderStatus.COMPLETED
                return True
        return False

    def update_order_progress(self, order_id: str, completed_sheets: int) -> bool:
        for order in self.orders:
            if order.order_id == order_id:
                order.completed_sheets = min(completed_sheets, order.sheet_count)
                if order.completed_sheets >= order.sheet_count:
                    order.status = OrderStatus.COMPLETED
                    if order.actual_end is None:
                        order.actual_end = datetime.now()
                return True
        return False

    def schedule_all(self, reschedule_all: bool = True) -> Dict:
        result = {
            'scheduled_count': 0,
            'locked_count': 0,
            'delayed_orders': [],
            'bottleneck_machines': []
        }

        self.update_order_status_by_time()

        if reschedule_all:
            self.machine_schedules = {m.machine_id: [] for m in self.machines}

            locked_orders = [o for o in self.orders
                           if o.status in (OrderStatus.IN_PRODUCTION, OrderStatus.COMPLETED)]
            reschedulable_orders = [o for o in self.orders
                                  if o.status in (OrderStatus.PENDING, OrderStatus.NOT_STARTED)]

            result['locked_count'] = len(locked_orders)

            for order in locked_orders:
                if order.assigned_machine and order.start_time and order.end_time:
                    setup_time = 0
                    if order.actual_start:
                        pass
                    slot = ScheduleSlot(
                        machine_id=order.assigned_machine,
                        order=order,
                        start_time=order.start_time,
                        end_time=order.end_time,
                        setup_time_minutes=setup_time
                    )
                    self.machine_schedules[order.assigned_machine].append(slot)

            for machine_id in self.machine_schedules:
                self.machine_schedules[machine_id].sort(key=lambda s: s.start_time)

            urgent_orders = sorted(
                [o for o in reschedulable_orders if o.is_urgent],
                key=lambda o: (o.delivery_date, -o.sheet_count)
            )
            normal_orders = sorted(
                [o for o in reschedulable_orders if not o.is_urgent],
                key=lambda o: (o.delivery_date, -o.sheet_count)
            )

            all_to_schedule = urgent_orders + normal_orders

            for order in all_to_schedule:
                slot = self._schedule_order(order)
                if slot:
                    result['scheduled_count'] += 1
        else:
            pending_orders = [o for o in self.orders if o.status == OrderStatus.PENDING]
            urgent_orders = sorted(
                [o for o in pending_orders if o.is_urgent],
                key=lambda o: o.delivery_date
            )
            normal_orders = sorted(
                [o for o in pending_orders if not o.is_urgent],
                key=lambda o: o.delivery_date
            )
            for order in urgent_orders + normal_orders:
                slot = self._schedule_order(order)
                if slot:
                    result['scheduled_count'] += 1

        delay_analysis = self.analyze_delay_risks()
        result['delayed_orders'] = delay_analysis['delayed_orders']
        result['at_risk_orders'] = delay_analysis['at_risk_orders']
        result['bottleneck_machines'] = delay_analysis['bottleneck_machines']
        result['suggestions'] = delay_analysis['suggestions']

        return result

    def _schedule_order(self, order: Order) -> Optional[ScheduleSlot]:
        available_machines = self.get_available_machines(order)
        if not available_machines:
            return None

        best_slot = None
        best_end_time = None
        best_machine = None

        for machine in available_machines:
            slot, end_time = self._find_best_slot_on_machine(order, machine)
            if slot is None:
                continue
            if best_end_time is None or end_time < best_end_time:
                best_end_time = end_time
                best_slot = slot
                best_machine = machine

        if best_slot and best_machine:
            self.machine_schedules[best_machine.machine_id].append(best_slot)
            self.machine_schedules[best_machine.machine_id].sort(key=lambda s: s.start_time)
            order.assigned_machine = best_machine.machine_id
            order.scheduled_start = best_slot.start_time
            order.scheduled_end = best_slot.end_time
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.NOT_STARTED
            return best_slot

        return None

    def _find_best_slot_on_machine(self, order: Order, machine: PrintingMachine) -> Tuple[Optional[ScheduleSlot], Optional[datetime]]:
        production_hours = order.production_hours(machine.speed_per_hour)
        if production_hours == float('inf'):
            return None, None

        slots = self.machine_schedules[machine.machine_id]
        now = datetime.now()
        today_start = get_work_start(now)

        best_slot = None
        best_end = None

        if not slots:
            start = today_start
            setup_time = SETUP_TIME_MINUTES
            start_with_setup = start + timedelta(minutes=setup_time)
            end = add_work_hours(start_with_setup, production_hours)
            slot = ScheduleSlot(
                machine_id=machine.machine_id,
                order=order,
                start_time=start,
                end_time=end,
                setup_time_minutes=setup_time
            )
            return slot, end

        first_slot = slots[0]
        if first_slot.start_time > today_start:
            gap_hours = (first_slot.start_time - today_start).total_seconds() / 3600.0
            setup_time = SETUP_TIME_MINUTES
            required_hours = production_hours + setup_time / 60.0
            if gap_hours >= required_hours:
                start = today_start
                start_with_setup = start + timedelta(minutes=setup_time)
                end = add_work_hours(start_with_setup, production_hours)
                if end <= first_slot.start_time:
                    slot = ScheduleSlot(
                        machine_id=machine.machine_id,
                        order=order,
                        start_time=start,
                        end_time=end,
                        setup_time_minutes=setup_time
                    )
                    return slot, end

        for i in range(len(slots)):
            current_slot = slots[i]
            prev_grammage = current_slot.order.paper_grammage

            if i == len(slots) - 1:
                after_end = current_slot.end_time
                if after_end < today_start:
                    after_end = today_start

                setup_time = 0 if prev_grammage == order.paper_grammage else SETUP_TIME_MINUTES
                start_with_setup = after_end + timedelta(minutes=setup_time)

                if start_with_setup.hour >= WORK_END_HOUR or start_with_setup.hour < WORK_START_HOUR:
                    start_with_setup = get_work_start(after_end + timedelta(days=1))
                    setup_time = 0 if prev_grammage == order.paper_grammage else SETUP_TIME_MINUTES
                    start_with_setup = start_with_setup + timedelta(minutes=setup_time)

                end = add_work_hours(start_with_setup, production_hours)
                slot = ScheduleSlot(
                    machine_id=machine.machine_id,
                    order=order,
                    start_time=after_end,
                    end_time=end,
                    setup_time_minutes=setup_time
                )
                if best_end is None or end < best_end:
                    best_slot = slot
                    best_end = end
            else:
                next_slot = slots[i + 1]
                gap_start = current_slot.end_time
                gap_end = next_slot.start_time

                if gap_start >= gap_end:
                    continue

                gap_seconds = (gap_end - gap_start).total_seconds()
                setup_time = 0 if prev_grammage == order.paper_grammage else SETUP_TIME_MINUTES
                total_required_hours = production_hours + setup_time / 60.0

                if gap_seconds >= total_required_hours * 3600:
                    start = gap_start
                    start_with_setup = start + timedelta(minutes=setup_time)
                    end = add_work_hours(start_with_setup, production_hours)
                    if end <= gap_end:
                        slot = ScheduleSlot(
                            machine_id=machine.machine_id,
                            order=order,
                            start_time=start,
                            end_time=end,
                            setup_time_minutes=setup_time
                        )
                        if best_end is None or end < best_end:
                            best_slot = slot
                            best_end = end

        return best_slot, best_end

    def insert_urgent_order(self, urgent_order: Order) -> Dict:
        urgent_order.is_urgent = True
        urgent_order.status = OrderStatus.PENDING
        self.add_order(urgent_order)

        original_schedule: Dict[str, Tuple[Optional[datetime], Optional[datetime], Optional[str]]] = {}
        for order in self.orders:
            if order.order_id != urgent_order.order_id:
                original_schedule[order.order_id] = (
                    order.scheduled_start,
                    order.scheduled_end,
                    order.assigned_machine
                )

        schedule_result = self.schedule_all(reschedule_all=True)

        affected_orders = []
        for order in self.orders:
            if order.order_id != urgent_order.order_id and order.scheduled_end:
                orig = original_schedule.get(order.order_id)
                if orig and orig[1] and order.scheduled_end > orig[1]:
                    delay_seconds = (order.scheduled_end - orig[1]).total_seconds()
                    delay_days = int(delay_seconds / 86400)
                    delay_hours = int((delay_seconds % 86400) / 3600)
                    affected_orders.append({
                        'order_id': order.order_id,
                        'original_end': orig[1],
                        'new_end': order.scheduled_end,
                        'delay_days': delay_days,
                        'delay_hours': delay_hours,
                        'original_machine': orig[2],
                        'new_machine': order.assigned_machine
                    })

        return {
            'urgent_order': urgent_order,
            'affected_orders': affected_orders,
            'schedule_result': schedule_result
        }

    def analyze_delay_risks(self) -> Dict:
        result = {
            'delayed_orders': [],
            'at_risk_orders': [],
            'bottleneck_machines': [],
            'suggestions': []
        }

        now = datetime.now()

        for order in self.orders:
            if order.status == OrderStatus.COMPLETED:
                continue

            if not order.scheduled_end:
                continue

            scheduled_end_date = order.scheduled_end.date()
            delivery_date = order.delivery_date

            if scheduled_end_date > delivery_date:
                delay_days = (scheduled_end_date - delivery_date).days
                result['delayed_orders'].append({
                    'order': order,
                    'delay_days': delay_days,
                    'scheduled_end': order.scheduled_end,
                    'delivery_date': delivery_date,
                    'machine': order.assigned_machine
                })
            elif scheduled_end_date == delivery_date:
                result['at_risk_orders'].append({
                    'order': order,
                    'risk_level': 'high',
                    'reason': '计划完成日与交货日同一天'
                })
            elif (delivery_date - scheduled_end_date).days <= 1:
                result['at_risk_orders'].append({
                    'order': order,
                    'risk_level': 'medium',
                    'reason': '缓冲时间不足1天'
                })

        machine_load: Dict[str, Dict] = {}
        for machine in self.machines:
            slots = self.machine_schedules.get(machine.machine_id, [])
            total_hours = 0
            active_slots = [s for s in slots if s.order.status != OrderStatus.COMPLETED]
            for slot in active_slots:
                total_hours += (slot.end_time - slot.start_time).total_seconds() / 3600.0

            if active_slots:
                first_start = min(s.start_time for s in active_slots)
                last_end = max(s.end_time for s in active_slots)
                total_days = (last_end.date() - first_start.date()).days + 1
                available_hours = total_days * (WORK_END_HOUR - WORK_START_HOUR)
                utilization = total_hours / available_hours if available_hours > 0 else 0

                machine_load[machine.machine_id] = {
                    'machine': machine,
                    'total_hours': total_hours,
                    'order_count': len(active_slots),
                    'utilization': utilization,
                    'makespan_days': total_days
                }

        sorted_machines = sorted(machine_load.items(), key=lambda x: -x[1]['utilization'])
        for machine_id, load in sorted_machines:
            if load['utilization'] > 0.9:
                result['bottleneck_machines'].append({
                    **load,
                    'bottleneck_level': 'critical'
                })
                if load['order_count'] >= 3:
                    late_orders = [o for o in result['delayed_orders'] if o['machine'] == machine_id]
                    if late_orders:
                        for delay_info in late_orders:
                            order = delay_info['order']
                            alt_machines = self.get_available_machines(order)
                            for alt in alt_machines:
                                if alt.machine_id != machine_id:
                                    alt_load = machine_load.get(alt.machine_id, {})
                                    if alt_load.get('utilization', 0) < 0.7:
                                        result['suggestions'].append({
                                            'type': 'reassign',
                                            'order_id': order.order_id,
                                            'from_machine': machine_id,
                                            'to_machine': alt.machine_id,
                                            'reason': f'{machine_id} 利用率 {load["utilization"]:.0%}，{alt.machine_id} 仅 {alt_load.get("utilization", 0):.0%}'
                                        })
            elif load['utilization'] > 0.75:
                result['bottleneck_machines'].append({
                    **load,
                    'bottleneck_level': 'warning'
                })

        for delay_info in result['delayed_orders']:
            order = delay_info['order']
            if order.status == OrderStatus.NOT_STARTED:
                result['suggestions'].append({
                    'type': 'priority',
                    'order_id': order.order_id,
                    'reason': f'延期 {delay_info["delay_days"]} 天，建议提升优先级'
                })

        merge_suggestions = self.get_material_merge_suggestions()
        for suggestion in merge_suggestions:
            if suggestion['saved_setup_minutes'] >= 60:
                result['suggestions'].append({
                    'type': 'merge',
                    **suggestion,
                    'reason': f'合并生产可节省 {suggestion["saved_setup_minutes"]} 分钟换单时间'
                })

        return result

    def get_material_merge_suggestions(self) -> List[Dict]:
        suggestions = []

        for machine_id, slots in self.machine_schedules.items():
            if not slots:
                continue

            sorted_slots = sorted(slots, key=lambda s: s.start_time)

            i = 0
            while i < len(sorted_slots):
                current_grammage = sorted_slots[i].order.paper_grammage
                current_machine = machine_id
                group = [sorted_slots[i]]
                j = i + 1

                while j < len(sorted_slots):
                    if sorted_slots[j].order.paper_grammage == current_grammage:
                        gap = (sorted_slots[j].start_time - sorted_slots[j-1].end_time).total_seconds() / 60.0
                        if gap <= 5:
                            group.append(sorted_slots[j])
                            j += 1
                        else:
                            break
                    else:
                        break

                if len(group) >= 2:
                    total_sheets = sum(s.order.sheet_count for s in group)
                    saved_setups = (len(group) - 1) * SETUP_TIME_MINUTES
                    suggestions.append({
                        'machine_id': current_machine,
                        'paper_grammage': current_grammage,
                        'orders': [s.order.order_id for s in group],
                        'total_sheets': total_sheets,
                        'saved_setup_minutes': saved_setups
                    })

                i = j if j > i + 1 else i + 1

        return suggestions

    def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        return [o for o in self.orders if o.status == status]

    def get_active_production_orders(self) -> List[Order]:
        return [o for o in self.orders if o.status == OrderStatus.IN_PRODUCTION]

    def get_all_slots(self) -> List[ScheduleSlot]:
        all_slots = []
        for slots in self.machine_schedules.values():
            all_slots.extend(slots)
        return sorted(all_slots, key=lambda s: (s.machine_id, s.start_time))

    def get_date_range(self) -> Tuple[date, date]:
        all_dates = []
        for slots in self.machine_schedules.values():
            for slot in slots:
                all_dates.append(slot.start_time.date())
                all_dates.append(slot.end_time.date())
        if not all_dates:
            today = date.today()
            return today, today
        return min(all_dates), max(all_dates)

    def get_machine_current_order(self, machine_id: str, current_time: datetime = None) -> Optional[Order]:
        if current_time is None:
            current_time = datetime.now()

        slots = self.machine_schedules.get(machine_id, [])
        for slot in slots:
            if slot.start_time <= current_time <= slot.end_time:
                return slot.order
        return None


