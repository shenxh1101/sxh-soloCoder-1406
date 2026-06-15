import sys
import os
import tempfile
from datetime import date, datetime, timedelta, time
from models import Order, PrintingMachine, OrderStatus, DowntimeRecord
from work_calendar import WorkCalendar, Shift, ShiftType
from scheduler import ProductionScheduler
from storage import DataStore, ProductionLog, order_to_dict, dict_to_order
from csv_io import export_daily_report_to_csv


def create_test_machines():
    return [
        PrintingMachine("M1", "印刷机1号", 60, 157, 5000),
        PrintingMachine("M2", "印刷机2号", 128, 250, 4000),
        PrintingMachine("M3", "印刷机3号", 200, 300, 3000),
    ]


def test_work_calendar():
    print("=" * 60)
    print("测试1: WorkCalendar 班次日历")
    print("=" * 60)

    cal = WorkCalendar()
    print(f"  默认班次: {len(cal.shifts)} 个")
    for s in cal.shifts:
        print(f"    {s.name}: {s.start_time} ~ {s.end_time}, 每日 {s.daily_hours():.1f} 小时")

    today = date.today()
    assert cal.is_work_day(today), "今天应该是工作日"

    holiday = today + timedelta(days=30)
    cal.add_holiday(holiday)
    assert not cal.is_work_day(holiday), "节假日不应该工作"
    cal.remove_holiday(holiday)
    assert cal.is_work_day(holiday), "删除节假日后应该工作"
    print(f"  节假日管理: OK")

    now = datetime.now()
    next_start = cal.next_working_start(now)
    print(f"  当前时间: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"  下个工作开始: {next_start.strftime('%Y-%m-%d %H:%M')}")

    end = cal.add_hours(next_start, 4.0)
    hours = cal.total_working_hours_between(next_start, end)
    print(f"  4工时后: {end.strftime('%Y-%m-%d %H:%M')}, 实际工时: {hours:.1f}h")
    assert abs(hours - 4.0) < 0.1, "工时计算错误"

    night_shift = Shift("夜班", time(20, 0), time(8, 0), ShiftType.NIGHT)
    cal.set_shifts([cal.shifts[0], night_shift])
    print(f"  设置双班后: {len(cal.shifts)} 个班次")
    assert len(cal.shifts) == 2

    data = cal.to_dict()
    cal2 = WorkCalendar.from_dict(data)
    assert len(cal2.shifts) == 2, "序列化后班次数量应该一致"
    print(f"  日历序列化/反序列化: OK")

    print("✓ WorkCalendar 测试通过\n")
    return True


def test_pause_resume_downtime():
    print("=" * 60)
    print("测试2: 暂停/恢复/异常停机")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    o1 = Order("PAU001", 100, 10000, today + timedelta(days=3))
    scheduler.add_order(o1)
    scheduler.schedule_all(reschedule_all=True)

    scheduler.mark_order_started("PAU001")
    assert o1.status == OrderStatus.IN_PRODUCTION, "登记开工后应该生产中"
    print(f"  登记开工后状态: {o1.status.value}")

    result = scheduler.pause_order("PAU001", "机器需要调试")
    assert result, "暂停应该成功"
    assert o1.status == OrderStatus.PAUSED, "暂停后应该是暂停中"
    print(f"  暂停后状态: {o1.status.value}, 暂停记录: {len(o1.pause_records)} 条")
    assert len(o1.pause_records) >= 1

    result = scheduler.resume_order("PAU001")
    assert result, "恢复应该成功"
    assert o1.status == OrderStatus.IN_PRODUCTION, "恢复后应该生产中"
    print(f"  恢复后状态: {o1.status.value}")

    now = datetime.now()
    scheduler.record_downtime(
        machine_id="M1",
        start_time=now,
        end_time=now + timedelta(hours=2),
        reason="滚筒故障维修",
        downtime_type="unplanned",
        order_id="PAU001"
    )
    assert len(scheduler.downtime_records) == 1, "应该有1条停机记录"
    dt = scheduler.downtime_records[0]
    print(f"  异常停机记录: {dt.reason}, 时长: {dt.duration_minutes} 分钟, 已解决: {dt.is_resolved}")
    assert dt.duration_minutes == 120, "停机时长应为120分钟"
    assert dt.is_resolved, "有结束时间应该已解决"

    print("✓ 暂停/恢复/异常停机 测试通过\n")
    return True


def test_status_sync():
    print("=" * 60)
    print("测试3: 状态自动联动")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    past = Order("SYNC001", 100, 5000, today - timedelta(days=2))
    past.scheduled_start = datetime.now() - timedelta(days=2, hours=4)
    past.scheduled_end = datetime.now() - timedelta(days=2, hours=2)
    past.status = OrderStatus.NOT_STARTED
    past.assigned_machine = "M1"
    scheduler.add_order(past)

    inprod = Order("SYNC002", 100, 10000, today + timedelta(days=1))
    inprod.scheduled_start = datetime.now() - timedelta(hours=1)
    inprod.scheduled_end = datetime.now() + timedelta(hours=1)
    inprod.status = OrderStatus.NOT_STARTED
    inprod.assigned_machine = "M1"
    scheduler.add_order(inprod)

    future = Order("SYNC003", 100, 5000, today + timedelta(days=5))
    future.scheduled_start = datetime.now() + timedelta(days=1)
    future.scheduled_end = datetime.now() + timedelta(days=1, hours=2)
    future.status = OrderStatus.NOT_STARTED
    future.assigned_machine = "M1"
    scheduler.add_order(future)

    result = scheduler.update_order_status_by_time()
    print(f"  自动更新结果: 开工={result['started']}, 完工={result['completed']}, 无变化={result['no_change']}")

    assert past.status == OrderStatus.COMPLETED, f"过期订单应该已完成，实际是{past.status.value}"
    assert inprod.status == OrderStatus.IN_PRODUCTION, f"进行中订单应该生产中，实际是{inprod.status.value}"
    assert future.status == OrderStatus.NOT_STARTED, f"未来订单应该未开工，实际是{future.status.value}"
    print(f"  SYNC001(过去): {past.status.value} ✓")
    print(f"  SYNC002(进行): {inprod.status.value} ✓")
    print(f"  SYNC003(未来): {future.status.value} ✓")

    active = scheduler.get_active_production_orders()
    order_ids = [o.order_id for o in active]
    assert "SYNC002" in order_ids, "查询激活订单应该自动更新状态"
    print(f"  通过查询入口自动同步状态: OK")

    print("✓ 状态自动联动 测试通过\n")
    return True


def test_data_persistence():
    print("=" * 60)
    print("测试4: 数据持久化")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        store = DataStore(data_dir=tmpdir)

        machines = create_test_machines()
        scheduler = ProductionScheduler(machines)
        today = date.today()

        o1 = Order("PER001", 100, 10000, today + timedelta(days=2))
        o2 = Order("PER002", 157, 20000, today + timedelta(days=3))
        scheduler.add_order(o1)
        scheduler.add_order(o2)
        scheduler.schedule_all()
        scheduler.mark_order_started("PER001")

        log = ProductionLog()
        log.add_event("order_added", "PER001", None, "测试订单1")
        log.add_event("schedule_run", None, None, "测试排程")

        saved = store.save_all(
            orders=scheduler.orders,
            machines=scheduler.machines,
            calendar_data=scheduler.calendar.to_dict(),
            production_log=log,
            downtime_records=scheduler.downtime_records
        )
        assert saved, "保存应该成功"
        assert store.has_saved_data(), "应该有已保存数据"
        print(f"  保存数据成功, 文件存在")

        loaded = store.load_all()
        assert loaded["exists"], "加载应该存在数据"
        assert len(loaded["orders"]) == 2, f"应该有2个订单，实际{len(loaded['orders'])}"
        assert len(loaded["machines"]) == 3, "应该有3台机器"
        assert loaded["production_log"] is not None, "应该有生产日志"
        print(f"  加载数据成功: {len(loaded['orders'])} 个订单, {len(loaded['machines'])} 台机器")

        loaded_o1 = [o for o in loaded["orders"] if o.order_id == "PER001"][0]
        assert loaded_o1.status == OrderStatus.IN_PRODUCTION, f"订单状态应该是生产中，实际是{loaded_o1.status.value}"
        assert loaded_o1.actual_start is not None, "实际开工时间应该已保存"
        print(f"  PER001 状态: {loaded_o1.status.value}, 实际开工: {loaded_o1.actual_start.strftime('%Y-%m-%d %H:%M')}")

        events = loaded["production_log"].events
        assert len(events) >= 2, f"应该至少有2条日志事件，实际{len(events)}"
        print(f"  生产日志事件数: {len(events)}")

        backup_path = store.backup()
        assert backup_path is not None and os.path.exists(backup_path), "备份应该成功"
        print(f"  数据备份成功: {os.path.basename(backup_path)}")

    print("✓ 数据持久化 测试通过\n")
    return True


def test_daily_report():
    print("=" * 60)
    print("测试5: 生产日报")
    print("=" * 60)

    machines = create_test_machines()
    scheduler = ProductionScheduler(machines)
    today = date.today()

    o1 = Order("RPT001", 100, 15000, today)
    o2 = Order("RPT002", 128, 8000, today + timedelta(days=1))
    o3 = Order("RPT003", 157, 5000, today - timedelta(days=1))
    scheduler.add_order(o1)
    scheduler.add_order(o2)
    scheduler.add_order(o3)
    scheduler.schedule_all()

    scheduler.mark_order_completed("RPT002", completed_sheets=8000)
    scheduler.mark_order_started("RPT001")

    report = scheduler.generate_daily_report(today)
    print(f"  日报日期: {report['report_date']}")
    print(f"  汇总: {report['summary']}")

    assert report["report_date"] == today
    assert report["summary"]["total_completed"] >= 1, "应该至少1个已完成"
    assert report["summary"]["total_in_production"] >= 1, "应该至少1个生产中"
    assert report["summary"]["total_sheets"] >= 8000, "完成印张应该>=8000"

    for mid, mdata in report["machines"].items():
        print(f"    {mid}: 完成{mdata['completed_count']}单, "
              f"完成印张{mdata['completed_sheets']}, "
              f"在制{mdata['in_production_orders']}, "
              f"延期{mdata['delayed_orders']}, "
              f"利用率{mdata['utilization']:.0%}")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        tmp_path = f.name

    try:
        result = export_daily_report_to_csv(report, tmp_path)
        assert result, "日报导出应该成功"
        assert os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0
        print(f"  日报CSV导出成功: {os.path.basename(tmp_path)}")
    finally:
        os.unlink(tmp_path)

    print("✓ 生产日报 测试通过\n")
    return True


def test_multi_shift_scheduling():
    print("=" * 60)
    print("测试6: 多班次排程")
    print("=" * 60)

    machines = create_test_machines()
    cal = WorkCalendar()
    cal.set_shifts([
        Shift("白班", time(8, 0), time(20, 0), ShiftType.DAY),
        Shift("夜班", time(20, 0), time(8, 0), ShiftType.NIGHT),
    ])
    scheduler = ProductionScheduler(machines, calendar=cal)

    today = date.today()
    for i in range(6):
        order = Order(f"SHF{i:03d}", 100 + i * 10, 8000, today + timedelta(days=2))
        scheduler.add_order(order)

    result = scheduler.schedule_all(reschedule_all=True)
    print(f"  双班排程结果: 排程{result['scheduled_count']}单, 锁定{result['locked_count']}单")

    all_slots = scheduler.get_all_slots()
    print(f"  总排程槽位数: {len(all_slots)}")
    for slot in all_slots:
        print(f"    {slot.order.order_id}: {slot.start_time.strftime('%m-%d %H:%M')} ~ {slot.end_time.strftime('%m-%d %H:%M')} @ {slot.machine_id}")

    start_date, end_date = scheduler.get_date_range()
    span_days = (end_date - start_date).days + 1
    print(f"  排程跨度: {span_days} 天 ({start_date} ~ {end_date})")

    assert result['scheduled_count'] == 6, "6个订单都应该排程成功"

    print("✓ 多班次排程 测试通过\n")
    return True


def main():
    print("\n" + "*" * 60)
    print("   印刷厂生产排程系统 v3.0 - 新增功能测试")
    print("*" * 60)

    tests = [
        ("WorkCalendar 班次日历", test_work_calendar),
        ("暂停/恢复/异常停机", test_pause_resume_downtime),
        ("状态自动联动", test_status_sync),
        ("数据持久化", test_data_persistence),
        ("生产日报", test_daily_report),
        ("多班次排程", test_multi_shift_scheduling),
    ]

    passed = 0
    failed = 0

    for name, test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"✗ 测试失败: {name}")
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"  通过: {passed} 个")
    print(f"  失败: {failed} 个")
    print(f"  总计: {len(tests)} 个")
    print("")

    if failed == 0:
        print("  ✓ 所有 v3.0 新增功能测试通过！")
    else:
        print(f"  ✗ 有 {failed} 个测试失败，请检查。")
    print("*" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
