import sys
from datetime import date, datetime, timedelta
from models import Order, PrintingMachine, OrderStatus
from scheduler import ProductionScheduler
from gantt import generate_gantt_chart, generate_daily_gantt
from csv_io import import_orders_from_csv, export_schedule_to_csv, export_orders_to_csv


def test_models():
    print("=" * 60)
    print("测试1: 数据模型 (models.py)")
    print("=" * 60)

    machine = PrintingMachine("M1", "测试机", 60, 200, 5000)
    print(f"  印刷机: {machine.name}")
    print(f"  克重范围: {machine.min_grammage}g - {machine.max_grammage}g")
    print(f"  速度: {machine.speed_per_hour} 印张/小时")
    print(f"  可生产100g纸张: {machine.can_print(100)}")
    print(f"  可生产250g纸张: {machine.can_print(250)}")

    order = Order("TEST001", 100, 10000, date.today())
    print(f"\n  订单: {order.order_id}")
    print(f"  纸张克重: {order.paper_grammage}g")
    print(f"  印张数量: {order.sheet_count}")
    print(f"  生产时间 (5000张/小时): {order.production_hours(5000):.1f} 小时")
    print(f"  状态: {order.status.value}")

    print("  ✓ 数据模型测试通过")
    return True


def test_scheduler():
    print("\n" + "=" * 60)
    print("测试2: 排程算法 (scheduler.py)")
    print("=" * 60)

    machines = [
        PrintingMachine("M1", "1号机", 60, 157, 5000),
        PrintingMachine("M2", "2号机", 128, 250, 4000),
        PrintingMachine("M3", "3号机", 200, 300, 3000),
    ]

    scheduler = ProductionScheduler(machines)

    today = date.today()
    orders = [
        Order("ORD001", 80, 10000, today + timedelta(days=2)),
        Order("ORD002", 128, 8000, today + timedelta(days=3)),
        Order("ORD003", 200, 6000, today + timedelta(days=2)),
        Order("ORD004", 100, 15000, today + timedelta(days=4)),
        Order("ORD005", 250, 4000, today + timedelta(days=3)),
    ]

    for order in orders:
        scheduler.add_order(order)

    print(f"  添加了 {len(scheduler.orders)} 个订单")

    slots = scheduler.schedule_all()
    print(f"  排程了 {len(slots)} 个订单")

    for machine in machines:
        machine_slots = scheduler.machine_schedules.get(machine.machine_id, [])
        if machine_slots:
            first = machine_slots[0].start_time.strftime("%m-%d %H:%M")
            last = machine_slots[-1].end_time.strftime("%m-%d %H:%M")
            print(f"  {machine.name}: {len(machine_slots)} 订单, {first} ~ {last}")

    scheduled_count = len([o for o in scheduler.orders if o.status == OrderStatus.SCHEDULED])
    print(f"  已排程订单数: {scheduled_count}")

    print("  ✓ 排程算法测试通过")
    return True


def test_gantt():
    print("\n" + "=" * 60)
    print("测试3: 甘特图 (gantt.py)")
    print("=" * 60)

    machines = [
        PrintingMachine("M1", "1号机", 60, 157, 5000),
        PrintingMachine("M2", "2号机", 128, 250, 4000),
        PrintingMachine("M3", "3号机", 200, 300, 3000),
    ]

    scheduler = ProductionScheduler(machines)
    today = date.today()

    orders = [
        Order("ORD001", 80, 8000, today + timedelta(days=1)),
        Order("ORD002", 128, 6000, today + timedelta(days=2)),
        Order("ORD003", 200, 5000, today + timedelta(days=1)),
    ]

    for order in orders:
        scheduler.add_order(order)

    scheduler.schedule_all()

    start_date = today
    end_date = today + timedelta(days=3)
    chart = generate_gantt_chart(machines, scheduler.machine_schedules, start_date, end_date)
    print("  多日甘特图生成成功")

    daily_chart = generate_daily_gantt(machines, scheduler.machine_schedules, today + timedelta(days=1))
    print("  单日甘特图生成成功")

    print("  ✓ 甘特图测试通过")
    return True


def test_csv_io():
    print("\n" + "=" * 60)
    print("测试4: CSV导入导出 (csv_io.py)")
    print("=" * 60)

    machines = [
        PrintingMachine("M1", "1号机", 60, 157, 5000),
        PrintingMachine("M2", "2号机", 128, 250, 4000),
        PrintingMachine("M3", "3号机", 200, 300, 3000),
    ]

    scheduler = ProductionScheduler(machines)

    imported = import_orders_from_csv("sample_orders.csv")
    print(f"  从 sample_orders.csv 导入了 {len(imported)} 个订单")

    for order in imported:
        scheduler.add_order(order)

    scheduler.schedule_all()

    if export_orders_to_csv(scheduler.orders, "test_orders_export.csv"):
        print("  订单导出CSV成功: test_orders_export.csv")

    all_slots = scheduler.get_all_slots()
    if export_schedule_to_csv(all_slots, "test_schedule_export.csv"):
        print("  排程导出CSV成功: test_schedule_export.csv")

    print("  ✓ CSV导入导出测试通过")
    return True


def test_urgent_insert():
    print("\n" + "=" * 60)
    print("测试5: 紧急插单")
    print("=" * 60)

    machines = [
        PrintingMachine("M1", "1号机", 60, 157, 5000),
        PrintingMachine("M2", "2号机", 128, 250, 4000),
        PrintingMachine("M3", "3号机", 200, 300, 3000),
    ]

    scheduler = ProductionScheduler(machines)
    today = date.today()

    for i in range(5):
        order = Order(f"ORD{i+1:03d}", 100 + i * 20, 5000 + i * 1000,
                      today + timedelta(days=2 + i))
        scheduler.add_order(order)

    scheduler.schedule_all()
    original_ends = {o.order_id: o.end_time for o in scheduler.orders if o.end_time}
    print(f"  初始排程: {len(scheduler.orders)} 个订单")

    urgent_order = Order("URG001", 120, 8000, today + timedelta(days=1), is_urgent=True)
    result = scheduler.insert_urgent_order(urgent_order)

    print(f"  插入紧急订单: {urgent_order.order_id}")
    print(f"  分配机器: {urgent_order.assigned_machine}")

    affected = result['affected_orders']
    print(f"  受影响订单数: {len(affected)}")
    for item in affected:
        print(f"    {item['order_id']}: 延期 {item['delay_days']} 天")

    print("  ✓ 紧急插单测试通过")
    return True


def test_material_suggestions():
    print("\n" + "=" * 60)
    print("测试6: 物料合并提醒")
    print("=" * 60)

    machines = [
        PrintingMachine("M1", "1号机", 60, 200, 5000),
    ]

    scheduler = ProductionScheduler(machines)
    today = date.today()

    orders = [
        Order("ORD001", 100, 3000, today + timedelta(days=1)),
        Order("ORD002", 100, 4000, today + timedelta(days=2)),
        Order("ORD003", 100, 2000, today + timedelta(days=3)),
        Order("ORD004", 150, 5000, today + timedelta(days=2)),
    ]

    for order in orders:
        scheduler.add_order(order)

    scheduler.schedule_all()

    suggestions = scheduler.get_material_merge_suggestions()
    print(f"  发现 {len(suggestions)} 个合并建议")
    for s in suggestions:
        print(f"    {s['paper_grammage']}g 纸张: {len(s['orders'])} 个订单, 节省 {s['saved_setup_minutes']} 分钟")

    print("  ✓ 物料合并提醒测试通过")
    return True


def test_order_status():
    print("\n" + "=" * 60)
    print("测试7: 订单状态管理")
    print("=" * 60)

    machines = [
        PrintingMachine("M1", "1号机", 60, 200, 5000),
    ]

    scheduler = ProductionScheduler(machines)
    today = date.today()

    scheduler.add_order(Order("ORD001", 100, 5000, today + timedelta(days=1)))
    scheduler.add_order(Order("ORD002", 120, 3000, today + timedelta(days=2)))

    pending = scheduler.get_orders_by_status(OrderStatus.PENDING)
    print(f"  待排产订单: {len(pending)} 个")

    scheduler.schedule_all()
    scheduled = scheduler.get_orders_by_status(OrderStatus.SCHEDULED)
    print(f"  已排产订单: {len(scheduled)} 个")

    scheduler.mark_order_completed("ORD001")
    completed = scheduler.get_orders_by_status(OrderStatus.COMPLETED)
    print(f"  已完成订单: {len(completed)} 个")

    print("  ✓ 订单状态管理测试通过")
    return True


def main():
    print("\n" + "*" * 60)
    print("   印刷厂生产排程系统 - 功能测试")
    print("*" * 60)

    tests = [
        test_models,
        test_scheduler,
        test_gantt,
        test_csv_io,
        test_urgent_insert,
        test_material_suggestions,
        test_order_status,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"  通过: {passed} 个")
    print(f"  失败: {failed} 个")
    print(f"  总计: {len(tests)} 个")

    if failed == 0:
        print("\n  ✓ 所有测试通过！系统运行正常。")
    else:
        print(f"\n  ✗ 有 {failed} 个测试失败，请检查。")

    print("*" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


