import sys
import os
import tempfile
from datetime import date, datetime, timedelta
from models import Order, PrintingMachine, OrderStatus
from scheduler import ProductionScheduler
from gantt import generate_gantt_chart, generate_daily_gantt
from csv_io import import_orders_from_csv, export_orders_to_csv, export_schedule_to_csv


def create_test_machines():
    return [
        PrintingMachine("M1", "1号机", 60, 157, 5000),
        PrintingMachine("M2", "2号机", 128, 250, 4000),
        PrintingMachine("M3", "3号机", 200, 300, 3000),
    ]


def test_models_enhanced():
    print("=" * 60)
    print("测试1: 数据模型增强")
    print("=" * 60)

    order = Order("TEST001", 100, 10000, date.today() + timedelta(days=3))

    print(f"  订单状态枚举:")
    print(f"    PENDING: {OrderStatus.PENDING.value}")
    print(f"    NOT_STARTED: {OrderStatus.NOT_STARTED.value}")
    print(f"    IN_PRODUCTION: {OrderStatus.IN_PRODUCTION.value}")
    print(f"    COMPLETED: {OrderStatus.COMPLETED.value}")

    order.scheduled_start = datetime.now()
    order.scheduled_end = datetime.now() + timedelta(hours=2)
    print(f"\n  计划时间属性:")
    print(f"    scheduled_start: {order.scheduled_start}")
    print(f"    scheduled_end: {order.scheduled_end}")
    print(f"    start_time (property): {order.start_time}")
    print(f"    end_time (property): {order.end_time}")

    order.completed_sheets = 5000
    print(f"\n  进度计算:")
    print(f"    completed_sheets: {order.completed_sheets}")
    print(f"    sheet_count: {order.sheet_count}")
    print(f"    progress: {order.progress:.0%}")

    order.delivery_date = date.today() - timedelta(days=1)
    print(f"\n  延期判断:")
    print(f"    delivery_date: {order.delivery_date}")
    print(f"    scheduled_end: {order.scheduled_end.date()}")
    print(f"    is_delayed: {order.is_delayed}")
    print(f"    delay_days: {order.delay_days}")

    print("  ✓ 数据模型增强测试通过")
    return True


def test_rolling_reschedule():
    print("\n" + "=" * 60)
    print("测试2: 滚动重排")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    orders1 = [
        Order("ORD001", 80, 10000, today + timedelta(days=2)),
        Order("ORD002", 128, 8000, today + timedelta(days=3)),
        Order("ORD003", 200, 6000, today + timedelta(days=2)),
    ]

    for order in orders1:
        scheduler.add_order(order)

    result1 = scheduler.schedule_all(reschedule_all=True)
    print(f"  第一次排程: {result1['scheduled_count']} 个订单")
    assert result1['scheduled_count'] == 3, "第一次排程应该有3个订单"

    scheduled_orders = [o for o in scheduler.orders if o.status == OrderStatus.NOT_STARTED]
    print(f"  未开工订单数: {len(scheduled_orders)}")

    scheduler.mark_order_started("ORD001")
    in_production = scheduler.get_active_production_orders()
    print(f"  标记 ORD001 开工后，生产中订单数: {len(in_production)}")
    assert len(in_production) == 1, "应该有1个生产中订单"

    new_orders = [
        Order("ORD004", 100, 12000, today + timedelta(days=1)),
        Order("ORD005", 157, 5000, today + timedelta(days=4)),
    ]
    for order in new_orders:
        scheduler.add_order(order)

    result2 = scheduler.schedule_all(reschedule_all=True)
    print(f"  滚动重排结果:")
    print(f"    新排程: {result2['scheduled_count']} 个订单")
    print(f"    锁定订单: {result2['locked_count']} 个 (生产中/已完成)")

    in_production_after = [o for o in scheduler.orders if o.status == OrderStatus.IN_PRODUCTION]
    not_started_after = [o for o in scheduler.orders if o.status == OrderStatus.NOT_STARTED]
    completed_after = [o for o in scheduler.orders if o.status == OrderStatus.COMPLETED]
    print(f"    生产中: {len(in_production_after)} 个")
    print(f"    未开工: {len(not_started_after)} 个")
    print(f"    已完成: {len(completed_after)} 个")
    print(f"    总订单: {len(scheduler.orders)} 个")

    locked_count = len(in_production_after) + len(completed_after)
    assert locked_count >= 1, "锁定订单(生产中+已完成)至少应该有1个"
    assert result2['locked_count'] == locked_count, "返回的锁定数应该等于实际锁定数"
    assert len(scheduler.orders) == 5, "总订单数应该是5"

    all_slots = scheduler.get_all_slots()
    print(f"  排程总槽位数: {len(all_slots)}")
    assert len(all_slots) == 5, "甘特图应该包含所有5个订单"

    print("  ✓ 滚动重排测试通过")
    return True


def test_production_execution():
    print("\n" + "=" * 60)
    print("测试3: 生产执行状态管理")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    scheduler.add_order(Order("ORD001", 100, 10000, today + timedelta(days=3)))
    scheduler.add_order(Order("ORD002", 120, 8000, today + timedelta(days=4)))
    scheduler.schedule_all()

    pending = scheduler.get_orders_by_status(OrderStatus.PENDING)
    not_started = scheduler.get_orders_by_status(OrderStatus.NOT_STARTED)
    print(f"  初始状态: 待排产={len(pending)}, 未开工={len(not_started)}")
    assert len(not_started) == 2, "排程后应该都是未开工状态"

    result = scheduler.mark_order_started("ORD001")
    print(f"  标记 ORD001 开工: {'成功' if result else '失败'}")
    assert result, "标记开工应该成功"

    in_production = scheduler.get_active_production_orders()
    print(f"  生产中订单: {[o.order_id for o in in_production]}")
    assert in_production[0].order_id == "ORD001", "ORD001应该在生产中"
    assert in_production[0].actual_start is not None, "应该有实际开工时间"

    result = scheduler.update_order_progress("ORD001", 3000)
    order = [o for o in scheduler.orders if o.order_id == "ORD001"][0]
    print(f"  更新进度到 3000/10000: 进度={order.progress:.0%}")
    assert order.progress == 0.3, "进度应该是30%"

    result = scheduler.update_order_progress("ORD001", 10000)
    print(f"  更新进度到 10000/10000: 状态={order.status.value}")
    assert order.status == OrderStatus.COMPLETED, "进度完成后应该自动标记为已完成"

    scheduler.add_order(Order("ORD003", 150, 5000, today + timedelta(days=5)))
    scheduler.schedule_all()
    scheduler.mark_order_started("ORD003")
    result = scheduler.mark_order_completed("ORD003", completed_sheets=5000)
    order3 = [o for o in scheduler.orders if o.order_id == "ORD003"][0]
    print(f"  直接标记 ORD003 完工: 状态={order3.status.value}")
    assert order3.status == OrderStatus.COMPLETED, "应该标记为已完成"
    assert order3.actual_end is not None, "应该有实际完工时间"

    print("  ✓ 生产执行状态管理测试通过")
    return True


def test_auto_status_update():
    print("\n" + "=" * 60)
    print("测试4: 自动状态更新")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    now = datetime.now()

    past_order = Order("PAST001", 100, 1000, date.today())
    past_order.scheduled_start = now - timedelta(hours=5)
    past_order.scheduled_end = now - timedelta(hours=3)
    past_order.status = OrderStatus.NOT_STARTED
    past_order.assigned_machine = "M1"
    scheduler.add_order(past_order)

    current_order = Order("CURR001", 120, 2000, date.today())
    current_order.scheduled_start = now - timedelta(hours=2)
    current_order.scheduled_end = now + timedelta(hours=1)
    current_order.status = OrderStatus.NOT_STARTED
    current_order.assigned_machine = "M2"
    scheduler.add_order(current_order)

    future_order = Order("FUTU001", 150, 3000, date.today())
    future_order.scheduled_start = now + timedelta(hours=3)
    future_order.scheduled_end = now + timedelta(hours=5)
    future_order.status = OrderStatus.NOT_STARTED
    future_order.assigned_machine = "M3"
    scheduler.add_order(future_order)

    result = scheduler.update_order_status_by_time(now)
    print(f"  自动更新结果: 开工={result['started']}, 完工={result['completed']}, 无变化={result['no_change']}")

    assert result['started'] >= 1, "应该至少有1个订单自动开工"
    assert result['completed'] >= 1, "应该至少有1个订单自动完工"

    past = [o for o in scheduler.orders if o.order_id == "PAST001"][0]
    curr = [o for o in scheduler.orders if o.order_id == "CURR001"][0]
    futu = [o for o in scheduler.orders if o.order_id == "FUTU001"][0]

    print(f"  PAST001 状态: {past.status.value} (应该是已完成)")
    print(f"  CURR001 状态: {curr.status.value} (应该是生产中)")
    print(f"  FUTU001 状态: {futu.status.value} (应该是未开工)")

    assert past.status == OrderStatus.COMPLETED, "过期订单应该自动完工"
    assert curr.status == OrderStatus.IN_PRODUCTION, "进行中订单应该自动开工"
    assert futu.status == OrderStatus.NOT_STARTED, "未来订单应该保持未开工"

    print("  ✓ 自动状态更新测试通过")
    return True


def test_delay_risk_analysis():
    print("\n" + "=" * 60)
    print("测试5: 延误风险分析")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    for i in range(8):
        order = Order(f"DLY{i+1:03d}", 100 + (i % 3) * 30,
                      15000 + i * 1000, today + timedelta(days=1))
        scheduler.add_order(order)

    scheduler.schedule_all(reschedule_all=True)
    analysis = scheduler.analyze_delay_risks()

    print(f"  延期订单: {len(analysis['delayed_orders'])} 个")
    for d in analysis['delayed_orders']:
        print(f"    {d['order'].order_id}: 延期 {d['delay_days']} 天, 机器: {d['machine']}")

    print(f"  风险订单: {len(analysis['at_risk_orders'])} 个")
    for r in analysis['at_risk_orders']:
        print(f"    {r['order'].order_id}: {r['risk_level']} - {r['reason']}")

    print(f"  瓶颈机器: {len(analysis['bottleneck_machines'])} 台")
    for b in analysis['bottleneck_machines']:
        print(f"    {b['machine'].machine_id}: 利用率 {b['utilization']:.0%}, "
              f"{b['order_count']} 个订单, {b['bottleneck_level']}")

    print(f"  优化建议: {len(analysis['suggestions'])} 条")
    for i, s in enumerate(analysis['suggestions'][:5], 1):
        if s['type'] == 'reassign':
            print(f"    {i}. 调整机器: {s['order_id']} {s['from_machine']}→{s['to_machine']}")
        elif s['type'] == 'priority':
            print(f"    {i}. 提升优先级: {s['order_id']}")
        elif s['type'] == 'merge':
            print(f"    {i}. 合并生产: {s['paper_grammage']}g, {len(s['orders'])}个订单")

    assert len(analysis['delayed_orders']) > 0 or len(analysis['at_risk_orders']) > 0, "应该有延期或风险订单"
    assert len(analysis['bottleneck_machines']) > 0, "应该识别出瓶颈机器"

    print("  ✓ 延误风险分析测试通过")
    return True


def test_csv_roundtrip():
    print("\n" + "=" * 60)
    print("测试6: CSV往返导入导出")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    orders = [
        Order("CSV001", 80, 10000, today + timedelta(days=2)),
        Order("CSV002", 128, 8000, today + timedelta(days=3), is_urgent=True),
        Order("CSV003", 200, 6000, today + timedelta(days=4)),
    ]
    for order in orders:
        scheduler.add_order(order)

    scheduler.schedule_all()
    scheduler.mark_order_started("CSV001")

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8-sig') as f:
        export_path = f.name

    try:
        result_export = export_orders_to_csv(scheduler.orders, export_path)
        print(f"  导出 {len(scheduler.orders)} 个订单到: {export_path}")
        assert result_export, "导出应该成功"

        scheduler2 = ProductionScheduler(machines)
        import_result = import_orders_from_csv(export_path, existing_orders=scheduler2.orders)

        print(f"  导入结果统计:")
        print(f"    成功: {import_result['success']}")
        print(f"    重复: {import_result['duplicate']}")
        print(f"    错误: {import_result['invalid']}")

        assert import_result['success'] == 3, "应该成功导入3个订单"
        assert import_result['duplicate'] == 0, "不应该有重复"
        assert import_result['invalid'] == 0, "不应该有错误"

        for order in import_result['orders']:
            scheduler2.add_order(order)

        print(f"  导入后订单数: {len(scheduler2.orders)}")

        orig = [o for o in scheduler.orders if o.order_id == "CSV001"][0]
        imp = [o for o in scheduler2.orders if o.order_id == "CSV001"][0]

        print(f"  数据一致性检查:")
        print(f"    订单号: {orig.order_id} == {imp.order_id}")
        print(f"    克重: {orig.paper_grammage} == {imp.paper_grammage}")
        print(f"    印张: {orig.sheet_count} == {imp.sheet_count}")
        print(f"    紧急: {orig.is_urgent} == {imp.is_urgent}")
        print(f"    状态: {orig.status.value} == {imp.status.value}")

        assert orig.order_id == imp.order_id
        assert orig.paper_grammage == imp.paper_grammage
        assert orig.sheet_count == imp.sheet_count
        assert orig.is_urgent == imp.is_urgent

        import_result2 = import_orders_from_csv(export_path, existing_orders=scheduler2.orders)
        print(f"  重复导入结果: 重复={import_result2['duplicate']}, 成功={import_result2['success']}")
        assert import_result2['duplicate'] == 3, "再次导入应该有3个重复"
        assert import_result2['success'] == 0, "重复导入不应该有新增"

        print("  ✓ CSV往返导入导出测试通过")
        return True

    finally:
        if os.path.exists(export_path):
            os.unlink(export_path)


def test_gantt_enhanced():
    print("\n" + "=" * 60)
    print("测试7: 增强甘特图")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    orders = [
        Order("GNT001", 80, 10000, today + timedelta(days=1)),
        Order("GNT002", 128, 8000, today + timedelta(days=2)),
        Order("GNT003", 200, 6000, today + timedelta(days=1)),
    ]
    for order in orders:
        scheduler.add_order(order)

    scheduler.schedule_all()
    scheduler.mark_order_started("GNT001")

    start_date = today
    end_date = today + timedelta(days=3)
    chart = generate_gantt_chart(machines, scheduler.machine_schedules, start_date, end_date)
    print("  多日甘特图生成成功")
    assert "■" in chart or "█" in chart or "▓" in chart, "应该包含状态方块"
    assert "图例" in chart, "应该包含图例"
    assert "当前时间" in chart, "应该显示当前时间"

    daily_chart = generate_daily_gantt(machines, scheduler.machine_schedules, today)
    print("  单日甘特图生成成功")
    assert "生产中" in daily_chart, "应该包含状态标签"
    assert "订单详情" in daily_chart, "应该包含订单详情"

    all_slots = scheduler.get_all_slots()
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8-sig') as f:
        schedule_path = f.name

    try:
        result = export_schedule_to_csv(all_slots, schedule_path)
        print(f"  排程导出成功: {len(all_slots)} 条记录")
        assert result, "导出应该成功"
    finally:
        if os.path.exists(schedule_path):
            os.unlink(schedule_path)

    print("  ✓ 增强甘特图测试通过")
    return True


def test_modify_delivery_and_reschedule():
    print("\n" + "=" * 60)
    print("测试8: 修改交期后重排")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    order = Order("CHG001", 100, 50000, today + timedelta(days=5))
    scheduler.add_order(order)
    scheduler.schedule_all()

    orig_end = order.scheduled_end
    print(f"  原交期: {order.delivery_date}, 计划完成: {orig_end.strftime('%Y-%m-%d')}")

    new_delivery = today - timedelta(days=2)
    order.delivery_date = new_delivery
    print(f"  修改交期为: {order.delivery_date} (过去的日期)")

    result = scheduler.schedule_all(reschedule_all=True)
    new_end = order.scheduled_end

    print(f"  重排后计划完成: {new_end.strftime('%Y-%m-%d') if new_end else 'N/A'}")
    print(f"  延期天数: {order.delay_days}")
    print(f"  是否延期: {order.is_delayed}")

    delays = [d for d in result['delayed_orders'] if d['order'].order_id == "CHG001"]
    print(f"  出现在延期列表中: {len(delays) > 0}")

    assert order.is_delayed, "交期提前后应该出现延期"

    print("  ✓ 修改交期后重排测试通过")
    return True


def main():
    print("\n" + "*" * 60)
    print("   印刷厂生产排程系统 v2.0 - 功能测试")
    print("*" * 60)

    tests = [
        test_models_enhanced,
        test_rolling_reschedule,
        test_production_execution,
        test_auto_status_update,
        test_delay_risk_analysis,
        test_csv_roundtrip,
        test_gantt_enhanced,
        test_modify_delivery_and_reschedule,
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
        print("\n  ✓ 所有测试通过！系统 v2.0 运行正常。")
    else:
        print(f"\n  ✗ 有 {failed} 个测试失败，请检查。")

    print("*" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


