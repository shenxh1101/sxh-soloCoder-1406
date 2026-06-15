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

    def get_available_machines(self, order: Order) -> List[PrintingMachine]:
        return [m for m in self.machines if m.can_print(order.paper_grammage)]

    def schedule_all(self) -> List[ScheduleSlot]:
        self.machine_schedules = {m.machine_id: [] for m in self.machines}

        urgent_orders = sorted(
            [o for o in self.orders if o.is_urgent and o.status == OrderStatus.PENDING],
            key=lambda o: o.delivery_date
        )
        normal_orders = sorted(
            [o for o in self.orders if not o.is_urgent and o.status == OrderStatus.PENDING],
            key=lambda o: o.delivery_date
        )

        all_orders = urgent_orders + normal_orders

        for order in all_orders:
            self._schedule_order(order)

        all_slots = []
        for slots in self.machine_schedules.values():
            all_slots.extend(slots)
        return all_slots

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
            order.start_time = best_slot.start_time
            order.end_time = best_slot.end_time
            order.status = OrderStatus.SCHEDULED
            return best_slot

        return None

    def _find_best_slot_on_machine(self, order: Order, machine: PrintingMachine) -> Tuple[Optional[ScheduleSlot], Optional[datetime]]:
        production_hours = order.production_hours(machine.speed_per_hour)
        if production_hours == float('inf'):
            return None, None

        slots = self.machine_schedules[machine.machine_id]
        today_start = get_work_start(datetime.now())

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

        best_slot = None
        best_end = None

        first_slot_start = slots[0].start_time
        if first_slot_start > today_start:
            gap_hours = (first_slot_start - today_start).total_seconds() / 3600.0
            setup_time = SETUP_TIME_MINUTES
            required_hours = production_hours + setup_time / 60.0
            if gap_hours >= required_hours:
                start = today_start
                start_with_setup = start + timedelta(minutes=setup_time)
                end = add_work_hours(start_with_setup, production_hours)
                if end <= first_slot_start:
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
                setup_time = 0 if prev_grammage == order.paper_grammage else SETUP_TIME_MINUTES
                start_with_setup = after_end + timedelta(minutes=setup_time)
                if start_with_setup.hour >= WORK_END_HOUR or start_with_setup.hour < WORK_START_HOUR:
                    start_with_setup = get_work_start(after_end + timedelta(days=1))
                    setup_time = SETUP_TIME_MINUTES if prev_grammage != order.paper_grammage else 0
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

        original_ends: Dict[str, datetime] = {}
        for order in self.orders:
            if order.order_id != urgent_order.order_id and order.end_time:
                original_ends[order.order_id] = order.end_time

        for order in self.orders:
            if order.status == OrderStatus.SCHEDULED or order.status == OrderStatus.IN_PRODUCTION:
                order.status = OrderStatus.PENDING
                order.assigned_machine = None
                order.start_time = None
                order.end_time = None

        completed_orders = [o for o in self.orders if o.status == OrderStatus.COMPLETED]
        for co in completed_orders:
            self.orders.remove(co)

        self.schedule_all()

        for co in completed_orders:
            self.orders.append(co)

        affected_orders = []
        for order in self.orders:
            if order.order_id != urgent_order.order_id and order.end_time:
                orig_end = original_ends.get(order.order_id)
                if orig_end and order.end_time > orig_end:
                    delay_days = (order.end_time.date() - orig_end.date()).days
                    affected_orders.append({
                        'order_id': order.order_id,
                        'original_end': orig_end,
                        'new_end': order.end_time,
                        'delay_days': delay_days
                    })

        return {
            'urgent_order': urgent_order,
            'affected_orders': affected_orders
        }

    def get_material_merge_suggestions(self) -> List[Dict]:
        suggestions = []

        for machine_id, slots in self.machine_schedules.items():
            if not slots:
                continue

            i = 0
            while i < len(slots):
                current_grammage = slots[i].order.paper_grammage
                group = [slots[i]]
                j = i + 1

                while j < len(slots):
                    if slots[j].order.paper_grammage == current_grammage:
                        gap = (slots[j].start_time - slots[j-1].end_time).total_seconds() / 60.0
                        if gap <= 0:
                            group.append(slots[j])
                            j += 1
                        else:
                            break
                    else:
                        break

                if len(group) >= 2:
                    total_sheets = sum(s.order.sheet_count for s in group)
                    saved_setups = (len(group) - 1) * SETUP_TIME_MINUTES
                    suggestions.append({
                        'machine_id': machine_id,
                        'paper_grammage': current_grammage,
                        'orders': [s.order.order_id for s in group],
                        'total_sheets': total_sheets,
                        'saved_setup_minutes': saved_setups
                    })

                i = j if j > i + 1 else i + 1

        return suggestions

    def mark_order_completed(self, order_id: str) -> bool:
        for order in self.orders:
            if order.order_id == order_id:
                order.status = OrderStatus.COMPLETED
                return True
        return False

    def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        return [o for o in self.orders if o.status == status]

    def get_all_slots(self) -> List[ScheduleSlot]:
        all_slots = []
        for slots in self.machine_schedules.values():
            all_slots.extend(slots)
        return all_slots

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


