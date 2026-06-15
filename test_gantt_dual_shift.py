from datetime import datetime, date, time, timedelta
from models import ScheduleSlot, PrintingMachine, Order, OrderStatus
from work_calendar import WorkCalendar, Shift, ShiftType
from gantt import generate_gantt_chart, generate_daily_gantt


def create_test_data():
    machines = [
        PrintingMachine("M001", "印刷机A", 80, 300, 5000),
        PrintingMachine("M002", "印刷机B", 100, 350, 6000),
    ]

    target_date = date(2026, 6, 15)

    order1 = Order(
        order_id="ORD-001",
        paper_grammage=157,
        sheet_count=10000,
        delivery_date=target_date,
        status=OrderStatus.IN_PRODUCTION,
        is_urgent=True,
        scheduled_start=datetime.combine(target_date, time(8, 30)),
        scheduled_end=datetime.combine(target_date, time(11, 30)),
        start_shift="白班",
        end_shift="白班",
    )

    order2 = Order(
        order_id="ORD-002",
        paper_grammage=200,
        sheet_count=8000,
        delivery_date=target_date - timedelta(days=1),
        status=OrderStatus.NOT_STARTED,
        scheduled_start=datetime.combine(target_date, time(22, 0)),
        scheduled_end=datetime.combine(target_date + timedelta(days=1), time(2, 0)),
        start_shift="夜班",
        end_shift="夜班",
    )

    order3 = Order(
        order_id="ORD-003",
        paper_grammage=250,
        sheet_count=15000,
        delivery_date=target_date + timedelta(days=1),
        status=OrderStatus.IN_PRODUCTION,
        scheduled_start=datetime.combine(target_date, time(20, 0)),
        scheduled_end=datetime.combine(target_date, time(23, 30)),
        start_shift="夜班",
        end_shift="夜班",
    )

    order4 = Order(
        order_id="ORD-004",
        paper_grammage=128,
        sheet_count=12000,
        delivery_date=target_date + timedelta(days=1),
        status=OrderStatus.NOT_STARTED,
        scheduled_start=datetime.combine(target_date + timedelta(days=1), time(0, 30)),
        scheduled_end=datetime.combine(target_date + timedelta(days=1), time(4, 0)),
        start_shift="夜班",
        end_shift="夜班",
    )

    machine_schedules = {
        "M001": [
            ScheduleSlot("M001", order1, order1.scheduled_start, order1.scheduled_end, 30),
            ScheduleSlot("M001", order2, order2.scheduled_start, order2.scheduled_end, 20),
        ],
        "M002": [
            ScheduleSlot("M002", order3, order3.scheduled_start, order3.scheduled_end, 30),
            ScheduleSlot("M002", order4, order4.scheduled_start, order4.scheduled_end, 20),
        ],
    }

    return machines, machine_schedules, target_date


def test_single_shift():
    print("=" * 80)
    print("【测试1：单班制（calendar=None）- 验证向后兼容性】")
    print("=" * 80)
    machines, machine_schedules, target_date = create_test_data()

    chart = generate_gantt_chart(
        machines=machines,
        machine_schedules=machine_schedules,
        start_date=target_date,
        end_date=target_date + timedelta(days=1),
        current_time=datetime.combine(target_date, time(10, 0)),
        calendar=None
    )
    print(chart)

    daily = generate_daily_gantt(
        machines=machines,
        machine_schedules=machine_schedules,
        target_date=target_date,
        current_time=datetime.combine(target_date, time(10, 0)),
        calendar=None
    )
    print(daily)


def test_dual_shift():
    print("=" * 80)
    print("【测试2：双班制 - 验证双班制显示】")
    print("=" * 80)
    machines, machine_schedules, target_date = create_test_data()

    calendar = WorkCalendar()
    calendar.set_shifts([
        Shift("白班", time(8, 0), time(20, 0), ShiftType.DAY),
        Shift("夜班", time(20, 0), time(8, 0), ShiftType.NIGHT),
    ])

    chart = generate_gantt_chart(
        machines=machines,
        machine_schedules=machine_schedules,
        start_date=target_date,
        end_date=target_date + timedelta(days=1),
        current_time=datetime.combine(target_date, time(22, 30)),
        calendar=calendar
    )
    print(chart)

    daily = generate_daily_gantt(
        machines=machines,
        machine_schedules=machine_schedules,
        target_date=target_date,
        current_time=datetime.combine(target_date, time(22, 30)),
        calendar=calendar
    )
    print(daily)


def test_dual_shift_next_day():
    print("=" * 80)
    print("【测试3：双班制 - 验证次日夜班显示】")
    print("=" * 80)
    machines, machine_schedules, target_date = create_test_data()

    calendar = WorkCalendar()
    calendar.set_shifts([
        Shift("白班", time(8, 0), time(20, 0), ShiftType.DAY),
        Shift("夜班", time(20, 0), time(8, 0), ShiftType.NIGHT),
    ])

    daily = generate_daily_gantt(
        machines=machines,
        machine_schedules=machine_schedules,
        target_date=target_date + timedelta(days=1),
        current_time=datetime.combine(target_date + timedelta(days=1), time(1, 0)),
        calendar=calendar
    )
    print(daily)


if __name__ == "__main__":
    test_single_shift()
    test_dual_shift()
    test_dual_shift_next_day()
    print("\n" + "=" * 80)
    print("所有测试完成！")
    print("=" * 80)
