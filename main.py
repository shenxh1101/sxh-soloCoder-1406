import sys
from datetime import date, datetime, timedelta, time
from models import Order, PrintingMachine, OrderStatus, DowntimeRecord
from scheduler import ProductionScheduler
from work_calendar import WorkCalendar, Shift, ShiftType
from storage import DataStore, ProductionLog
from gantt import generate_gantt_chart, generate_daily_gantt
from csv_io import import_orders_from_csv, export_orders_to_csv, export_schedule_to_csv, export_daily_report_to_csv


def create_default_machines():
    return [
        PrintingMachine("M1", "印刷机1号", 60, 157, 5000),
        PrintingMachine("M2", "印刷机2号", 128, 250, 4000),
        PrintingMachine("M3", "印刷机3号", 200, 300, 3000),
    ]


def _format_shift_info(order):
    if order.start_shift and order.end_shift:
        if order.start_shift == order.end_shift:
            return f"班次:{order.start_shift}"
        else:
            return f"班次:{order.start_shift}→{order.end_shift}（跨班）"
    elif hasattr(order, 'shift') and order.shift:
        return f"班次:{order.shift}"
    return ""


def _format_pause_info(order):
    parts = []
    if order.pause_count > 0:
        parts.append(f"暂停{order.pause_count}次 累计{order.total_pause_minutes}分钟")
    if order.pause_delay_minutes > 0:
        parts.append(f"影响完工+{order.pause_delay_minutes}分钟")
    return "  ".join(parts)


def print_menu():
    print("\n" + "=" * 65)
    print("       印刷厂生产排程系统 v3.0")
    print("=" * 65)
    print("  ┌───────────── 订单管理 ─────────────┐  ┌───────────── 生产执行 ─────────────┐")
    print("  │  1. 查看所有订单      2. 添加订单   │  │  7. 登记开工        8. 登记完工     │")
    print("  │  3. 修改订单交期    12. 延误风险   │  │  9. 更新进度       10. 自动更新状态  │")
    print("  └─────────────────────────────────────┘  └────────────────────────────────────┘")
    print("  ┌───────────── 排程计划 ─────────────┐  ┌───────────── 数据交换 ─────────────┐")
    print("  │  4. 执行滚动排程     5. 紧急插单   │  │ 13. 导入订单CSV   14. 导出排程CSV   │")
    print("  │  6. 查看甘特图     11. 物料提醒    │  │ 15. 导出订单CSV                     │")
    print("  │ 23. 产能预估视图                      │  │                                    │")
    print("  └─────────────────────────────────────┘  └────────────────────────────────────┘")
    print("  ┌───────────── 班次日历 ─────────────┐  ┌───────────── 数据管理 ─────────────┐")
    print("  │ 16. 班次设置       17. 节假日管理   │  │ 20. 保存数据       21. 加载数据     │")
    print("  │ 18. 登记暂停       19. 异常停机登记 │  │ 22. 生产日报导出                   │")
    print("  └─────────────────────────────────────┘  └────────────────────────────────────┘")
    print("  0. 退出系统")
    print("=" * 65)


def view_all_orders(scheduler: ProductionScheduler):
    if not scheduler.orders:
        print("\n暂无订单。")
        return

    scheduler.update_order_status_by_time()

    print("\n" + "=" * 140)
    print("所有订单列表")
    print("-" * 140)
    print(f"{'订单号':<12} {'克重':<6} {'印张':<10} {'交货日期':<12} {'状态':<10} {'紧急':<6} "
          f"{'机器':<8} {'计划开始':<16} {'计划结束':<16} {'进度':<8} {'延期':<6} {'班次/暂停':<30}")
    print("-" * 140)

    for order in sorted(scheduler.orders, key=lambda o: (o.delivery_date, -o.is_urgent)):
        urgent = "是" if order.is_urgent else "否"
        machine = order.assigned_machine or "-"
        s_start = order.scheduled_start.strftime("%m-%d %H:%M") if order.scheduled_start else "-"
        s_end = order.scheduled_end.strftime("%m-%d %H:%M") if order.scheduled_end else "-"
        progress = f"{order.progress:.0%}" if order.status == OrderStatus.IN_PRODUCTION else "-"
        delay = f"{order.delay_days}天" if order.is_delayed and order.status != OrderStatus.COMPLETED else "-"

        shift_info = _format_shift_info(order)
        pause_info = _format_pause_info(order)
        extra_parts = [p for p in [shift_info, pause_info] if p]
        extra_info = "  ".join(extra_parts) if extra_parts else "-"

        line = f"{order.order_id:<12} {order.paper_grammage:<5}g {order.sheet_count:<10} " \
               f"{order.delivery_date.strftime('%Y-%m-%d'):<12} {order.status.value:<10} {urgent:<6} " \
               f"{machine:<8} {s_start:<16} {s_end:<16} {progress:<8} {delay:<6} {extra_info:<30}"

        if order.is_delayed and order.status != OrderStatus.COMPLETED:
            line = "⚠️  " + line
        elif order.is_urgent and order.status != OrderStatus.COMPLETED:
            line = "⚡ " + line
        elif order.status == OrderStatus.PAUSED:
            line = "⏸️  " + line

        print(line)

    print("-" * 140)
    status_counts = {
        '待排产': len(scheduler.get_orders_by_status(OrderStatus.PENDING)),
        '未开工': len(scheduler.get_orders_by_status(OrderStatus.NOT_STARTED)),
        '生产中': len(scheduler.get_orders_by_status(OrderStatus.IN_PRODUCTION)),
        '暂停中': len(scheduler.get_orders_by_status(OrderStatus.PAUSED)),
        '已完成': len(scheduler.get_orders_by_status(OrderStatus.COMPLETED)),
    }
    total_paused_orders = sum(1 for o in scheduler.orders if o.pause_count > 0 and o.status != OrderStatus.COMPLETED)
    print(f"总计: {len(scheduler.orders)} 个订单 | "
          f"待排产:{status_counts['待排产']} "
          f"未开工:{status_counts['未开工']} "
          f"生产中:{status_counts['生产中']} "
          f"暂停中:{status_counts['暂停中']} "
          f"已完成:{status_counts['已完成']}"
          + (f" | 历史暂停:{total_paused_orders}" if total_paused_orders > 0 else ""))
    print("=" * 140)


def add_order(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 添加新订单 ---")
    try:
        order_id = input("订单号: ").strip()
        if not order_id:
            print("错误: 订单号不能为空！")
            return

        for o in scheduler.orders:
            if o.order_id == order_id:
                print(f"错误: 订单号 {order_id} 已存在！")
                return

        paper_grammage = int(input("纸张克重 (60-300g): "))
        if paper_grammage < 60 or paper_grammage > 300:
            print("错误: 纸张克重必须在60g-300g之间！")
            return

        sheet_count = int(input("印张数量: "))
        if sheet_count <= 0:
            print("错误: 印张数量必须大于0！")
            return

        delivery_date_str = input("交货日期 (YYYY-MM-DD): ").strip()
        try:
            delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d").date()
        except ValueError:
            print("错误: 日期格式不正确！")
            return

        is_urgent_str = input("是否紧急订单? (y/N): ").strip().lower()
        is_urgent = is_urgent_str in ('y', 'yes', '是')

        order = Order(
            order_id=order_id,
            paper_grammage=paper_grammage,
            sheet_count=sheet_count,
            delivery_date=delivery_date,
            is_urgent=is_urgent
        )

        available_machines = scheduler.get_available_machines(order)
        if not available_machines:
            print(f"警告: 没有机器可以生产 {paper_grammage}g 的纸张！")
            confirm = input("是否仍要添加? (y/N): ").strip().lower()
            if confirm not in ('y', 'yes', '是'):
                return

        scheduler.add_order(order)
        production_log.add_event('order_added', order_id, None, f"添加订单: 克重{paper_grammage}g, 印张{sheet_count}")
        print(f"\n订单 {order_id} 添加成功！建议执行 [4. 执行滚动排程] 更新计划。")

    except ValueError:
        print("错误: 输入格式不正确！")


def modify_order_delivery(scheduler: ProductionScheduler):
    print("\n--- 修改订单交期 ---")
    view_all_orders(scheduler)

    order_id = input("\n请输入要修改的订单号: ").strip()
    order = None
    for o in scheduler.orders:
        if o.order_id == order_id:
            order = o
            break

    if not order:
        print("未找到该订单！")
        return

    if order.status == OrderStatus.COMPLETED:
        print("错误: 已完成订单无法修改交期！")
        return

    print(f"当前订单: {order.order_id} - 纸张:{order.paper_grammage}g "
          f"印张:{order.sheet_count} 当前交期:{order.delivery_date.strftime('%Y-%m-%d')} "
          f"状态:{order.status.value}")

    if order.status == OrderStatus.IN_PRODUCTION:
        print("警告: 该订单正在生产中，修改交期可能影响后续排程！")

    new_date_str = input("新的交货日期 (YYYY-MM-DD): ").strip()
    try:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
    except ValueError:
        print("错误: 日期格式不正确！")
        return

    order.delivery_date = new_date
    print(f"\n订单 {order_id} 交期已更新为 {new_date.strftime('%Y-%m-%d')}")
    print("建议执行 [4. 执行滚动排程] 重新计算计划。")


def run_schedule(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 执行滚动排程 ---")

    total_orders = len(scheduler.orders)
    locked_count = len([o for o in scheduler.orders
                      if o.status in (OrderStatus.IN_PRODUCTION, OrderStatus.COMPLETED, OrderStatus.PAUSED)])
    pending_count = len([o for o in scheduler.orders
                        if o.status in (OrderStatus.PENDING, OrderStatus.NOT_STARTED)])

    print(f"当前总订单数: {total_orders}")
    print(f"  - 锁定订单 (生产中/暂停中/已完成): {locked_count}")
    print(f"  - 待排程订单: {pending_count}")

    if pending_count == 0 and locked_count == 0:
        print("\n没有订单可以排程，请先添加订单。")
        return

    confirm = input(f"\n是否重新排程所有 {pending_count} 个未完成订单? (Y/n): ").strip().lower()
    if confirm and confirm not in ('y', 'yes', '是'):
        print("已取消排程。")
        return

    result = scheduler.schedule_all(reschedule_all=True)
    production_log.add_event('schedule_run', None, None, f"执行滚动排程, 排程{result['scheduled_count']}个订单")

    print(f"\n{'='*60}")
    print("排程完成！")
    print(f"{'='*60}")
    print(f"  新排程订单数: {result['scheduled_count']}")
    print(f"  锁定订单数: {result['locked_count']}")

    print(f"\n机器负荷摘要:")
    for machine in scheduler.machines:
        machine_slots = [s for s in scheduler.machine_schedules.get(machine.machine_id, [])
                        if s.order.status != OrderStatus.COMPLETED]
        if machine_slots:
            first_start = min(s.start_time for s in machine_slots)
            last_end = max(s.end_time for s in machine_slots)
            total_hours = sum((s.end_time - s.start_time).total_seconds() / 3600.0 for s in machine_slots)
            total_days = (last_end.date() - first_start.date()).days + 1
            day_start = datetime.combine(first_start.date(), time(0, 0))
            day_end = datetime.combine(last_end.date() + timedelta(days=1), time(0, 0))
            available_hours = scheduler.calendar.total_working_hours_between(day_start, day_end)
            utilization = total_hours / available_hours if available_hours > 0 else 0
            print(f"  {machine.name}: {len(machine_slots)} 单, "
                  f"{first_start.strftime('%m-%d')} ~ {last_end.strftime('%m-%d')}, "
                  f"时长 {total_hours:.1f}h, 利用率 {utilization:.0%}")

    delayed = result.get('delayed_orders', [])
    if delayed:
        print(f"\n⚠️  延期订单 ({len(delayed)} 个):")
        for d in delayed:
            order = d['order']
            print(f"  {order.order_id}: 延期 {d['delay_days']} 天 "
                  f"(计划完成: {d['scheduled_end'].strftime('%Y-%m-%d')}, "
                  f"交期: {d['delivery_date'].strftime('%Y-%m-%d')})")

    suggestions = result.get('suggestions', [])
    if suggestions:
        print(f"\n💡 优化建议 ({len(suggestions)} 条):")
        for i, s in enumerate(suggestions[:5], 1):
            if s['type'] == 'reassign':
                print(f"  {i}. 订单 {s['order_id']}: 从 {s['from_machine']} 调整到 {s['to_machine']}")
                print(f"     {s['reason']}")
            elif s['type'] == 'priority':
                print(f"  {i}. 订单 {s['order_id']}: {s['reason']}")
            elif s['type'] == 'merge':
                print(f"  {i}. 合并 {s['paper_grammage']}g 纸张订单: {', '.join(s['orders'])}")
                print(f"     可节省 {s['saved_setup_minutes']} 分钟")

    print(f"\n提示: 可使用 [6. 查看甘特图] 查看详细排程，或 [12. 延误风险] 查看完整分析。")


def view_gantt(scheduler: ProductionScheduler):
    scheduler.update_order_status_by_time()

    print("\n--- 查看甘特图 ---")
    print("  1. 多日概览甘特图")
    print("  2. 单日详细甘特图")
    print("  3. 查看当前生产中的订单")
    choice = input("请选择 (1-3, 默认1): ").strip() or "1"

    if choice == "1":
        start_date_str = input("开始日期 (YYYY-MM-DD, 回车默认今天): ").strip()
        end_date_str = input("结束日期 (YYYY-MM-DD, 回车默认+7天): ").strip()

        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            else:
                start_date = date.today()

            if end_date_str:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            else:
                end_date = start_date + timedelta(days=7)

            chart = generate_gantt_chart(
                scheduler.machines,
                scheduler.machine_schedules,
                start_date,
                end_date,
                calendar=scheduler.calendar
            )
            print("\n" + chart)
        except ValueError:
            print("错误: 日期格式不正确！")

    elif choice == "2":
        date_str = input("查看日期 (YYYY-MM-DD, 回车默认今天): ").strip()
        try:
            if date_str:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            else:
                target_date = date.today()

            chart = generate_daily_gantt(
                scheduler.machines,
                scheduler.machine_schedules,
                target_date,
                calendar=scheduler.calendar
            )
            print("\n" + chart)
        except ValueError:
            print("错误: 日期格式不正确！")

    elif choice == "3":
        active_orders = scheduler.get_active_production_orders()
        if not active_orders:
            print("\n当前没有正在生产的订单。")
        else:
            print(f"\n当前正在生产的订单 ({len(active_orders)} 个):")
            print("-" * 80)
            for order in active_orders:
                machine = next((m for m in scheduler.machines if m.machine_id == order.assigned_machine), None)
                machine_name = machine.name if machine else order.assigned_machine
                progress = order.progress
                expected_end = order.scheduled_end.strftime('%Y-%m-%d %H:%M') if order.scheduled_end else "-"
                print(f"  订单: {order.order_id}")
                print(f"    机器: {machine_name}  纸张: {order.paper_grammage}g  印张: {order.sheet_count}")
                print(f"    进度: {progress:.0%} ({order.completed_sheets}/{order.sheet_count})")
                print(f"    计划完成: {expected_end}")
                if order.is_delayed:
                    print(f"    ⚠️  已延期 {order.delay_days} 天")
                print("")


def insert_urgent_order(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 紧急插单 ---")
    try:
        order_id = input("紧急订单号: ").strip()
        if not order_id:
            print("错误: 订单号不能为空！")
            return

        for o in scheduler.orders:
            if o.order_id == order_id:
                print(f"错误: 订单号 {order_id} 已存在！")
                return

        paper_grammage = int(input("纸张克重 (60-300g): "))
        if paper_grammage < 60 or paper_grammage > 300:
            print("错误: 纸张克重必须在60g-300g之间！")
            return

        sheet_count = int(input("印张数量: "))
        if sheet_count <= 0:
            print("错误: 印张数量必须大于0！")
            return

        delivery_date_str = input("交货日期 (YYYY-MM-DD): ").strip()
        try:
            delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d").date()
        except ValueError:
            print("错误: 日期格式不正确！")
            return

        urgent_order = Order(
            order_id=order_id,
            paper_grammage=paper_grammage,
            sheet_count=sheet_count,
            delivery_date=delivery_date,
            is_urgent=True
        )

        print(f"\n插入紧急订单后将重新排程所有未完成订单...")
        result = scheduler.insert_urgent_order(urgent_order)
        production_log.add_event('order_added', order_id, None, f"紧急插单: 克重{paper_grammage}g, 印张{sheet_count}")
        production_log.add_event('schedule_run', None, None, "紧急插单后重新排程")

        print(f"\n{'='*60}")
        print("紧急插单完成！")
        print(f"{'='*60}")
        print(f"  紧急订单: {urgent_order.order_id}")
        print(f"  分配机器: {urgent_order.assigned_machine}")
        print(f"  计划开始: {urgent_order.scheduled_start.strftime('%Y-%m-%d %H:%M') if urgent_order.scheduled_start else '未排程'}")
        print(f"  计划结束: {urgent_order.scheduled_end.strftime('%Y-%m-%d %H:%M') if urgent_order.scheduled_end else '未排程'}")

        affected = result['affected_orders']
        if affected:
            print(f"\n受影响订单 ({len(affected)} 个):")
            print("-" * 80)
            print(f"{'订单号':<12} {'原完成':<17} {'新完成':<17} {'延期':<8} {'机器变更':<12}")
            print("-" * 80)
            for item in affected:
                delay_str = f"{item['delay_days']}天{item['delay_hours']}时" if item['delay_days'] + item['delay_hours'] > 0 else "0天"
                machine_change = ""
                if item['original_machine'] != item['new_machine']:
                    machine_change = f"{item['original_machine']}→{item['new_machine']}"
                print(f"{item['order_id']:<12} "
                      f"{item['original_end'].strftime('%m-%d %H:%M'):<17} "
                      f"{item['new_end'].strftime('%m-%d %H:%M'):<17} "
                      f"{delay_str:<8} {machine_change:<12}")
        else:
            print("\n其他订单不受影响。")

    except ValueError:
        print("错误: 输入格式不正确！")


def filter_orders_by_status(scheduler: ProductionScheduler):
    print("\n--- 按状态筛选订单 ---")
    print("  1. 待排产")
    print("  2. 未开工 (已排产)")
    print("  3. 生产中")
    print("  4. 暂停中")
    print("  5. 已完成")
    choice = input("请选择 (1-5): ").strip()

    status_map = {
        '1': OrderStatus.PENDING,
        '2': OrderStatus.NOT_STARTED,
        '3': OrderStatus.IN_PRODUCTION,
        '4': OrderStatus.PAUSED,
        '5': OrderStatus.COMPLETED,
    }

    status = status_map.get(choice)
    if not status:
        print("无效选择！")
        return

    orders = scheduler.get_orders_by_status(status)
    if not orders:
        print(f"\n没有{status.value}的订单。")
        return

    print(f"\n{status.value}订单列表 ({len(orders)} 个):")
    print("-" * 130)
    print(f"{'订单号':<12} {'克重':<6} {'印张':<10} {'交货日期':<12} {'机器':<8} {'计划结束':<16} {'进度':<8} {'班次/暂停':<40}")
    print("-" * 130)
    for order in sorted(orders, key=lambda o: o.delivery_date):
        machine = order.assigned_machine or "-"
        s_end = order.scheduled_end.strftime("%m-%d %H:%M") if order.scheduled_end else "-"
        progress = f"{order.progress:.0%}" if order.status == OrderStatus.IN_PRODUCTION else "-"
        shift_info = _format_shift_info(order)
        pause_info = _format_pause_info(order)
        extra_parts = [p for p in [shift_info, pause_info] if p]
        extra_info = "  ".join(extra_parts) if extra_parts else "-"
        print(f"{order.order_id:<12} {order.paper_grammage:<5}g {order.sheet_count:<10} "
              f"{order.delivery_date.strftime('%Y-%m-%d'):<12} {machine:<8} {s_end:<16} {progress:<8} {extra_info:<40}")


def mark_order_started(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 登记订单开工 ---")
    not_started = scheduler.get_orders_by_status(OrderStatus.NOT_STARTED)

    if not not_started:
        print("没有可开工的订单。请先排程。")
        return

    print("可开工的订单:")
    for i, order in enumerate(not_started, 1):
        machine = next((m.name for m in scheduler.machines if m.machine_id == order.assigned_machine),
                       order.assigned_machine)
        start = order.scheduled_start.strftime("%m-%d %H:%M") if order.scheduled_start else "-"
        print(f"  {i}. {order.order_id} - 纸张:{order.paper_grammage}g 印张:{order.sheet_count} "
              f"机器:{machine} 计划开始:{start}")

    try:
        choice = input("\n请输入订单序号或订单号: ").strip()
        target_order = None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(not_started):
                target_order = not_started[idx]
        else:
            for order in not_started:
                if order.order_id == choice:
                    target_order = order
                    break

        if target_order:
            time_str = input("开工时间 (YYYY-MM-DD HH:MM, 回车默认当前时间): ").strip()
            if time_str:
                try:
                    start_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    print("错误: 时间格式不正确，使用当前时间。")
                    start_time = None
            else:
                start_time = None

            if scheduler.mark_order_started(target_order.order_id, start_time):
                actual_time = start_time or datetime.now()
                production_log.add_event('order_started', target_order.order_id, target_order.assigned_machine,
                                      f"订单开工: {target_order.order_id} 开工时间: {actual_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"订单 {target_order.order_id} 已登记开工，开工时间: {actual_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                print("标记失败！")
        else:
            print("未找到该订单！")
    except ValueError:
        print("输入无效！")


def mark_order_completed_ui(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 登记订单完工 ---")
    in_production = scheduler.get_orders_by_status(OrderStatus.IN_PRODUCTION)
    not_started = scheduler.get_orders_by_status(OrderStatus.NOT_STARTED)
    all_eligible = in_production + not_started

    if not all_eligible:
        print("没有可登记完工的订单。")
        return

    print("可登记完工的订单:")
    for i, order in enumerate(all_eligible, 1):
        machine = next((m.name for m in scheduler.machines if m.machine_id == order.assigned_machine),
                       order.assigned_machine)
        progress = f"进度:{order.progress:.0%}" if order.status == OrderStatus.IN_PRODUCTION else "未开工"
        print(f"  {i}. {order.order_id} - {order.status.value} - 纸张:{order.paper_grammage}g "
              f"机器:{machine} {progress}")

    try:
        choice = input("\n请输入订单序号或订单号: ").strip()
        target_order = None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_eligible):
                target_order = all_eligible[idx]
        else:
            for order in all_eligible:
                if order.order_id == choice:
                    target_order = order
                    break

        if target_order:
            time_str = input("完工时间 (YYYY-MM-DD HH:MM, 回车默认当前时间): ").strip()
            end_time = None
            if time_str:
                try:
                    end_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    print("错误: 时间格式不正确，使用当前时间。")

            sheets_str = input(f"完成印张数量 (回车默认全部 {target_order.sheet_count}): ").strip()
            completed_sheets = None
            if sheets_str:
                try:
                    completed_sheets = int(sheets_str)
                except ValueError:
                    print("错误: 印张数格式不正确，使用默认值。")

            if scheduler.mark_order_completed(target_order.order_id, end_time, completed_sheets):
                actual_time = end_time or datetime.now()
                sheets = completed_sheets or target_order.sheet_count
                production_log.add_event('order_completed', target_order.order_id, target_order.assigned_machine,
                                      f"订单完工: {target_order.order_id} 完成印张: {sheets}")
                print(f"订单 {target_order.order_id} 已登记完工，完工时间: {actual_time.strftime('%Y-%m-%d %H:%M')}，完成印张: {sheets}")
            else:
                print("标记失败！")
        else:
            print("未找到该订单！")
    except ValueError:
        print("输入无效！")


def update_order_progress_ui(scheduler: ProductionScheduler):
    print("\n--- 更新订单进度 ---")
    in_production = scheduler.get_orders_by_status(OrderStatus.IN_PRODUCTION)

    if not in_production:
        print("没有正在生产的订单。")
        return

    print("正在生产的订单:")
    for i, order in enumerate(in_production, 1):
        machine = next((m.name for m in scheduler.machines if m.machine_id == order.assigned_machine),
                       order.assigned_machine)
        print(f"  {i}. {order.order_id} - 纸张:{order.paper_grammage}g "
              f"印张:{order.completed_sheets}/{order.sheet_count} ({order.progress:.0%}) "
              f"机器:{machine}")

    try:
        choice = input("\n请输入订单序号或订单号: ").strip()
        target_order = None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(in_production):
                target_order = in_production[idx]
        else:
            for order in in_production:
                if order.order_id == choice:
                    target_order = order
                    break

        if target_order:
            print(f"当前进度: {target_order.progress:.0%} ({target_order.completed_sheets}/{target_order.sheet_count})")
            sheets_str = input("已完成印张数量: ").strip()
            try:
                completed_sheets = int(sheets_str)
                if scheduler.update_order_progress(target_order.order_id, completed_sheets):
                    print(f"订单 {target_order.order_id} 进度已更新为 "
                          f"{target_order.progress:.0%} ({target_order.completed_sheets}/{target_order.sheet_count})")
                    if target_order.status == OrderStatus.COMPLETED:
                        print("订单已全部完成，自动标记为已完成状态。")
                else:
                    print("更新失败！")
            except ValueError:
                print("错误: 印张数格式不正确！")
        else:
            print("未找到该订单！")
    except ValueError:
        print("输入无效！")


def auto_update_status(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 自动更新订单状态 ---")
    now = datetime.now()
    result = scheduler.update_order_status_by_time(now)

    production_log.add_event('status_auto_updated', None, None,
                          f"自动更新: 开工{result['started']}个, 完工{result['completed']}个")

    print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)
    print(f"  自动开工: {result['started']} 个订单")
    print(f"  自动完工: {result['completed']} 个订单")
    print(f"  无变化: {result['no_change']} 个订单")
    print("-" * 40)
    print(f"当前状态统计:")
    print(f"  待排产: {len(scheduler.get_orders_by_status(OrderStatus.PENDING))}")
    print(f"  未开工: {len(scheduler.get_orders_by_status(OrderStatus.NOT_STARTED))}")
    print(f"  生产中: {len(scheduler.get_orders_by_status(OrderStatus.IN_PRODUCTION))}")
    print(f"  暂停中: {len(scheduler.get_orders_by_status(OrderStatus.PAUSED))}")
    print(f"  已完成: {len(scheduler.get_orders_by_status(OrderStatus.COMPLETED))}")


def show_delay_risks(scheduler: ProductionScheduler):
    print("\n" + "=" * 80)
    print("                       延误风险分析报告")
    print("=" * 80)

    analysis = scheduler.analyze_delay_risks()

    delayed = analysis['delayed_orders']
    at_risk = analysis['at_risk_orders']
    bottlenecks = analysis['bottleneck_machines']
    suggestions = analysis['suggestions']

    print(f"\n📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if not delayed and not at_risk and not bottlenecks:
        print("\n✅ 所有订单状态良好，无延误风险！")
        return

    if delayed:
        print(f"\n⚠️  已确认延期订单 ({len(delayed)} 个):")
        print("-" * 80)
        print(f"{'订单号':<10} {'克重':<6} {'印张':<8} {'交期':<12} {'计划完成':<16} {'延期':<8} {'机器':<8}")
        print("-" * 80)
        for d in delayed:
            order = d['order']
            print(f"{order.order_id:<10} {order.paper_grammage:<5}g {order.sheet_count:<8} "
                  f"{d['delivery_date'].strftime('%Y-%m-%d'):<12} "
                  f"{d['scheduled_end'].strftime('%Y-%m-%d %H:%M'):<16} "
                  f"{d['delay_days']:<8}天 {d['machine']:<8}")

    if at_risk:
        print(f"\n⚠️  存在风险订单 ({len(at_risk)} 个):")
        print("-" * 60)
        for r in at_risk:
            order = r['order']
            risk_icon = "🔴" if r['risk_level'] == 'high' else "🟡"
            print(f"  {risk_icon} {order.order_id}: {r['reason']}")
            print(f"     交期: {order.delivery_date.strftime('%Y-%m-%d')} "
                  f"计划完成: {order.scheduled_end.strftime('%Y-%m-%d %H:%M') if order.scheduled_end else '未排程'} "
                  f"状态: {order.status.value}")

    if bottlenecks:
        print(f"\n⚙️  瓶颈机器分析 ({len(bottlenecks)} 台):")
        print("-" * 60)
        for b in bottlenecks:
            level = "🔴 严重" if b['bottleneck_level'] == 'critical' else "🟡 警告"
            machine = b['machine']
            print(f"  {level} {machine.name} ({machine.machine_id}):")
            print(f"     订单数: {b['order_count']} 个, 总工时: {b['total_hours']:.1f}h, "
                  f"利用率: {b['utilization']:.0%}, 跨度: {b['makespan_days']} 天")

    if suggestions:
        print(f"\n💡 优化建议 ({len(suggestions)} 条):")
        print("-" * 60)
        for i, s in enumerate(suggestions, 1):
            if s['type'] == 'reassign':
                print(f"  {i}. [调整机器] 订单 {s['order_id']}:")
                print(f"     从 {s['from_machine']} 调整到 {s['to_machine']}")
                print(f"     原因: {s['reason']}")
            elif s['type'] == 'priority':
                print(f"  {i}. [提升优先级] 订单 {s['order_id']}:")
                print(f"     {s['reason']}")
            elif s['type'] == 'merge':
                print(f"  {i}. [合并生产] {s['paper_grammage']}g 纸张:")
                print(f"     订单: {', '.join(s['orders'])}")
                print(f"     可节省 {s['saved_setup_minutes']} 分钟换单时间")

    print("\n" + "=" * 80)


def show_material_suggestions(scheduler: ProductionScheduler):
    print("\n--- 物料合并提醒 ---")
    suggestions = scheduler.get_material_merge_suggestions()

    if not suggestions:
        print("暂无合并建议。")
        return

    print(f"发现 {len(suggestions)} 个合并机会:")
    print("-" * 80)
    for i, suggestion in enumerate(suggestions, 1):
        machine = next((m.name for m in scheduler.machines if m.machine_id == suggestion['machine_id']),
                       suggestion['machine_id'])
        print(f"\n建议 #{i}:")
        print(f"  机器: {machine} ({suggestion['machine_id']})")
        print(f"  纸张克重: {suggestion['paper_grammage']}g")
        print(f"  涉及订单: {', '.join(suggestion['orders'])}")
        print(f"  总印张数: {suggestion['total_sheets']}")
        print(f"  可节省换单时间: {suggestion['saved_setup_minutes']} 分钟 "
              f"({suggestion['saved_setup_minutes']/60:.1f} 小时)")

    print("\n提示: 将相同纸张的订单连续安排生产，可减少换单清洗时间。")


def import_orders(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 导入订单 (CSV) ---")
    file_path = input("CSV文件路径: ").strip()

    if not file_path:
        print("错误: 文件路径不能为空！")
        return

    result = import_orders_from_csv(file_path, existing_orders=scheduler.orders)

    print(f"\n{'='*60}")
    print("导入结果统计")
    print(f"{'='*60}")
    print(f"  ✅ 成功新增: {result['success']} 个订单")
    print(f"  ⏭️  重复跳过: {result['duplicate']} 个订单")
    print(f"  ❌ 格式错误: {result['invalid']} 个订单")
    print(f"{'='*60}")

    if result['warnings']:
        print("\n⚠️  警告信息:")
        for warning in result['warnings'][:10]:
            print(f"  - {warning}")
        if len(result['warnings']) > 10:
            print(f"  ... 还有 {len(result['warnings']) - 10} 条警告")

    if result['errors']:
        print("\n❌ 错误信息:")
        for error in result['errors'][:10]:
            print(f"  - {error}")
        if len(result['errors']) > 10:
            print(f"  ... 还有 {len(result['errors']) - 10} 条错误")

    for order in result['orders']:
        scheduler.add_order(order)
        production_log.add_event('order_added', order.order_id, None, f"从CSV导入订单")

    if result['success'] > 0:
        print(f"\n成功导入 {result['success']} 个新订单！建议执行 [4. 执行滚动排程] 更新计划。")


def export_schedule(scheduler: ProductionScheduler):
    print("\n--- 导出排程 (CSV) ---")
    file_path = input("导出文件路径 (默认: schedule.csv): ").strip() or "schedule.csv"

    all_slots = scheduler.get_all_slots()
    if not all_slots:
        print("暂无排程数据，请先执行排程。")
        return

    for slot in all_slots:
        pass

    if export_schedule_to_csv(all_slots, file_path):
        print(f"排程已导出到: {file_path}")
        print(f"共导出 {len(all_slots)} 条排程记录。")


def export_orders(scheduler: ProductionScheduler):
    print("\n--- 导出订单 (CSV) ---")
    file_path = input("导出文件路径 (默认: orders.csv): ").strip() or "orders.csv"

    if not scheduler.orders:
        print("暂无订单数据。")
        return

    if export_orders_to_csv(scheduler.orders, file_path):
        print(f"订单已导出到: {file_path}")
        print(f"共导出 {len(scheduler.orders)} 个订单。")
        print("提示: 导出的文件可以直接通过 [13. 导入订单CSV] 导回系统。")


def manage_shifts(scheduler: ProductionScheduler):
    print("\n--- 班次设置 ---")
    print("  1. 查看当前班次配置")
    print("  2. 设置单班 (白班 8:00-20:00)")
    print("  3. 设置双班 (白班 8:00-20:00, 夜班 20:00-8:00)")
    print("  4. 自定义班次")
    choice = input("请选择 (1-4, 默认1): ").strip() or "1"

    if choice == "1":
        print("\n当前班次配置:")
        print("-" * 60)
        if not scheduler.calendar.shifts:
            print("  (暂无班次配置)")
        else:
            for i, shift in enumerate(scheduler.calendar.shifts, 1):
                print(f"  {i}. {shift.name}")
                print(f"     时间: {shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}")
                print(f"     类型: {shift.shift_type.value}")
                print(f"     时长: {shift.daily_hours():.1f} 小时")
        print("-" * 60)

    elif choice == "2":
        shifts = [
            Shift("白班", time(8, 0), time(20, 0), ShiftType.DAY)
        ]
        scheduler.calendar.set_shifts(shifts)
        print("\n已设置为单班制 (白班 8:00-20:00)")
        print("提示: 下次执行排程时生效。")

    elif choice == "3":
        shifts = [
            Shift("白班", time(8, 0), time(20, 0), ShiftType.DAY),
            Shift("夜班", time(20, 0), time(8, 0), ShiftType.NIGHT)
        ]
        scheduler.calendar.set_shifts(shifts)
        print("\n已设置为双班制:")
        print("  白班: 08:00 - 20:00")
        print("  夜班: 20:00 - 次日 08:00")
        print("提示: 下次执行排程时生效。")

    elif choice == "4":
        try:
            n_str = input("请输入班次数量: ").strip()
            n = int(n_str)
            if n <= 0:
                print("错误: 班次数量必须大于0！")
                return
            shifts = []
            for i in range(n):
                print(f"\n--- 第 {i+1} 个班次:")
                name = input(f"  班次名称: ").strip() or f"班次{i+1}"
                start_str = input("  开始时间 (HH:MM): ").strip()
                end_str = input("  结束时间 (HH:MM): ").strip()
                type_choice = input("  班次类型: 1.白班 2.夜班 3.全天 (默认1): ").strip() or "1"
                type_map = {"1": ShiftType.DAY, "2": ShiftType.NIGHT, "3": ShiftType.FULL}
                shift_type = type_map.get(type_choice, ShiftType.DAY)
                try:
                    start = datetime.strptime(start_str, "%H:%M").time()
                    end = datetime.strptime(end_str, "%H:%M").time()
                    shifts.append(Shift(name, start, end, shift_type))
                except ValueError:
                        print("错误: 时间格式不正确！")
                        return
            scheduler.calendar.set_shifts(shifts)
            print(f"\n已设置 {len(shifts)} 个班次！")
            print("提示: 下次执行排程时生效。")
        except ValueError:
            print("错误: 输入格式不正确！")

    else:
        print("无效选择！")


def manage_holidays(scheduler: ProductionScheduler):
    print("\n--- 节假日管理 ---")
    print("  1. 查看节假日列表")
    print("  2. 添加节假日")
    print("  3. 删除节假日")
    print("  4. 批量添加节假日")
    print("  5. 清空所有节假日")
    choice = input("请选择 (1-5, 默认1): ").strip() or "1"

    if choice == "1":
        print("\n已设置的节假日:")
        print("-" * 40)
        if not scheduler.calendar.holidays:
            print("  (暂无节假日)")
        else:
            for i, d in enumerate(sorted(scheduler.calendar.holidays), 1):
                weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                print(f"  {i}. {d.strftime('%Y-%m-%d')} ({weekday_names[d.weekday()]})")
        print("-" * 40)

    elif choice == "2":
        date_str = input("请输入节假日日期 (YYYY-MM-DD): ").strip()
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            scheduler.calendar.add_holiday(d)
            print(f"\n已添加节假日: {d.strftime('%Y-%m-%d')}")
        except ValueError:
            print("错误: 日期格式不正确！")

    elif choice == "3":
        if not scheduler.calendar.holidays:
            print("\n暂无节假日可删除。")
            return
        print("\n已设置的节假日:")
        for i, d in enumerate(sorted(scheduler.calendar.holidays), 1):
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            print(f"  {i}. {d.strftime('%Y-%m-%d')} ({weekday_names[d.weekday()]})")
        idx_str = input("请输入要删除的序号: ").strip()
        try:
            idx = int(idx_str) - 1
            holidays_list = sorted(scheduler.calendar.holidays)
            if 0 <= idx < len(holidays_list):
                scheduler.calendar.remove_holiday(holidays_list[idx])
                print(f"\n已删除节假日: {holidays_list[idx].strftime('%Y-%m-%d')}")
            else:
                print("无效序号！")
        except ValueError:
            print("错误: 输入格式不正确！")

    elif choice == "4":
        start_str = input("请输入开始日期 (YYYY-MM-DD): ").strip()
        days_str = input("请输入天数: ").strip()
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            days = int(days_str)
            if days <= 0:
                print("错误: 天数必须大于0！")
                return
            added = 0
            for i in range(days):
                d = start_date + timedelta(days=i)
                if d not in scheduler.calendar.holidays:
                    scheduler.calendar.add_holiday(d)
                    added += 1
            print(f"\n批量添加完成，共添加 {added} 个节假日。")
        except ValueError:
            print("错误: 输入格式不正确！")

    elif choice == "5":
        confirm = input("确定要清空所有节假日吗? (y/N): ").strip().lower()
        if confirm in ('y', 'yes', '是'):
            scheduler.calendar.holidays.clear()
            print("\n已清空所有节假日。")
        else:
            print("已取消。")

    else:
        print("无效选择！")


def manage_pause_resume(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 登记暂停/恢复 ---")

    in_production = scheduler.get_orders_by_status(OrderStatus.IN_PRODUCTION)
    paused = scheduler.get_orders_by_status(OrderStatus.PAUSED)
    all_orders = in_production + paused

    if not all_orders:
        print("没有可操作的订单。")
        return

    print("可操作的订单:")
    for i, order in enumerate(all_orders, 1):
        machine = next((m.name for m in scheduler.machines if m.machine_id == order.assigned_machine),
                       order.assigned_machine)
        status_str = "生产中" if order.status == OrderStatus.IN_PRODUCTION else "暂停中"
        print(f"  {i}. {order.order_id} - {status_str} - 纸张:{order.paper_grammage}g "
              f"印张:{order.completed_sheets}/{order.sheet_count} 机器:{machine}")

    try:
        choice = input("\n请输入订单序号或订单号: ").strip()
        target_order = None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_orders):
                target_order = all_orders[idx]
        else:
            for order in all_orders:
                if order.order_id == choice:
                    target_order = order
                    break

        if not target_order:
            print("未找到该订单！")
            return

        if target_order.status == OrderStatus.IN_PRODUCTION:
            print(f"\n当前订单状态: 生产中")
            print("  1. 暂停订单")
            action = input("请选择操作 (1): ").strip() or "1"
            if action == "1":
                reason = input("请输入暂停原因: ").strip()
                if not reason:
                    print("错误: 暂停原因不能为空！")
                    return
                if scheduler.pause_order(target_order.order_id, reason):
                    production_log.add_event('order_paused', target_order.order_id,
                                          target_order.assigned_machine, f"暂停原因: {reason}")
                    print(f"订单 {target_order.order_id} 已暂停。")
                    print(f"已暂停 {target_order.pause_count} 次，累计暂停 {target_order.total_pause_minutes} 分钟")
                    print(f"下次执行滚动排程将重新计算顺延影响")
                else:
                    print("暂停失败！")
            else:
                print("无效选择！")

        elif target_order.status == OrderStatus.PAUSED:
            print(f"\n当前订单状态: 暂停中")
            if target_order.pause_records:
                last_pause = target_order.pause_records[-1]
                print(f"  暂停原因: {last_pause.get('reason', '未知')}")
                print(f"  暂停时间: {last_pause.get('pause_time', '未知')}")
            print("  1. 恢复订单")
            action = input("请选择操作 (1): ").strip() or "1"
            if action == "1":
                if scheduler.resume_order(target_order.order_id):
                    production_log.add_event('order_resumed', target_order.order_id,
                                              target_order.assigned_machine, "订单恢复生产")
                    print(f"订单 {target_order.order_id} 已恢复生产。")
                    print(f"本次暂停已记录，累计 {target_order.total_pause_minutes} 分钟")
                else:
                    print("恢复失败！")
            else:
                print("无效选择！")

    except ValueError:
        print("输入无效！")


def record_downtime_ui(scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 异常停机登记 ---")

    print("机器列表:")
    for i, machine in enumerate(scheduler.machines, 1):
        print(f"  {i}. {machine.name} ({machine.machine_id}): {machine.min_grammage}g-{machine.max_grammage}g")

    try:
        choice = input("\n请选择机器序号或机器ID: ").strip()
        target_machine = None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(scheduler.machines):
                target_machine = scheduler.machines[idx]
        else:
            for m in scheduler.machines:
                if m.machine_id == choice:
                    target_machine = m
                    break

        if not target_machine:
            print("未找到该机器！")
            return

        reason = input("请输入停机原因: ").strip()
        if not reason:
            print("错误: 停机原因不能为空！")
            return

        print("\n停机类型:")
        print("  1. 异常停机 (unplanned)")
        print("  2. 计划停机 (planned)")
        type_choice = input("请选择 (1-2, 默认1): ").strip() or "1"
        downtime_type = 'unplanned' if type_choice == '1' else 'planned'

        start_str = input("开始时间 (YYYY-MM-DD HH:MM, 回车默认当前时间): ").strip()
        end_str = input("结束时间 (YYYY-MM-DD HH:MM, 回车表示未结束): ").strip()

        try:
            if start_str:
                start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
            else:
                start_time = datetime.now()

            end_time = None
            if end_str:
                end_time = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
        except ValueError:
            print("错误: 时间格式不正确！")
            return

        current_order = scheduler.get_machine_current_order(target_machine.machine_id, start_time)
        order_id = None
        if current_order:
            print(f"\n检测到该机器当前正在生产订单: {current_order.order_id}")
            link = input("是否关联此订单? (Y/n): ").strip().lower()
            if not link or link in ('y', 'yes', '是'):
                order_id = current_order.order_id
        else:
            order_choice = input("\n请输入关联订单号 (回车不关联): ").strip()
            if order_choice:
                for o in scheduler.orders:
                    if o.order_id == order_choice:
                        order_id = order_choice
                        break

        record = scheduler.record_downtime(
            machine_id=target_machine.machine_id,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            downtime_type=downtime_type,
            order_id=order_id
        )
        production_log.add_event('downtime_recorded', order_id, target_machine.machine_id,
                              f"停机登记: {reason}, 类型:{downtime_type}")

        print(f"\n停机记录已保存！记录ID: {record.record_id}")
        print(f"  机器: {target_machine.name}")
        print(f"  类型: {'异常停机' if downtime_type == 'unplanned' else '计划停机'}")
        print(f"  原因: {reason}")
        print(f"  开始: {start_time.strftime('%Y-%m-%d %H:%M')}")
        if end_time:
            print(f"  结束: {end_time.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"  结束: 未结束")
        if order_id:
            print(f"  关联订单: {order_id}")
        print("\n提示: 下次执行滚动排程时将考虑此停机时段。")

    except ValueError:
        print("输入无效！")


def save_data_ui(datastore: DataStore, scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 保存数据 ---")
    result = datastore.save_all(
        scheduler.orders,
        scheduler.machines,
        scheduler.calendar.to_dict(),
        production_log,
        scheduler.downtime_records
    )
    if result:
        production_log.add_event('data_saved', None, None, "手动保存数据")
        print("✅ 数据保存成功！")
    else:
        print("❌ 数据保存失败！")


def load_data_ui(datastore: DataStore, scheduler: ProductionScheduler, production_log: ProductionLog):
    print("\n--- 加载数据 ---")
    if not datastore.has_saved_data():
        print("没有找到保存的数据。")
        return

    confirm = input("加载数据将覆盖当前数据，是否继续? (y/N): ").strip().lower()
    if confirm not in ('y', 'yes', '是'):
        print("已取消加载。")
        return

    data = datastore.load_all()
    if not data.get('exists'):
        print("加载失败，没有保存的数据。")
        return

    scheduler.orders = data['orders']
    if data['machines']:
        scheduler.machines = data['machines']
    else:
        scheduler.machines = create_default_machines()
    scheduler.machine_schedules = {m.machine_id: [] for m in scheduler.machines}

    if data['calendar']:
        scheduler.calendar = WorkCalendar.from_dict(data['calendar'])

    if data['production_log']:
        production_log.events = data['production_log'].events
    else:
        production_log.events = ProductionLog().events

    scheduler.downtime_records = []
    for dr in data.get('downtime_records', []):
        from storage import _deserialize_datetime
        scheduler.downtime_records.append(DowntimeRecord(
            record_id=dr.get('record_id'),
            machine_id=dr.get('machine_id'),
            order_id=dr.get('order_id'),
            start_time=_deserialize_datetime(dr.get('start_time')),
            end_time=_deserialize_datetime(dr.get('end_time')),
            reason=dr.get('reason', ''),
            downtime_type=dr.get('downtime_type', 'unplanned')
        ))

    production_log.add_event('data_loaded', None, None, "加载保存的数据")

    print(f"\n✅ 数据加载成功！")
    print(f"  加载订单: {len(scheduler.orders)} 个")
    print(f"  加载机器: {len(scheduler.machines)} 台")
    print(f"  加载停机记录: {len(scheduler.downtime_records)} 条")
    if data.get('saved_at'):
        print(f"  数据保存时间: {data['saved_at']}")


def show_capacity_forecast(scheduler: ProductionScheduler):
    print("\n--- 产能预估视图 ---")
    days_str = input("预估天数(回车默认3): ").strip()
    try:
        days = int(days_str) if days_str else 3
        if days <= 0:
            print("错误: 天数必须大于0！")
            return
    except ValueError:
        print("错误: 输入格式不正确！")
        return

    forecast = scheduler.get_capacity_forecast(days)
    forecast_dates = forecast.get('forecast_dates', [])
    machines = forecast.get('machines', {})
    summary = forecast.get('summary', {})

    start_date = forecast_dates[0].strftime('%Y-%m-%d') if forecast_dates else '-'
    end_date = forecast_dates[-1].strftime('%Y-%m-%d') if forecast_dates else '-'
    today = date.today()

    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RESET = '\033[0m'

    print(f"\n{'='*100}")
    print(f"              未来{days}天产能预估 (日期范围: {start_date} ~ {end_date})")
    print(f"{'='*100}")

    for machine_id, m_data in machines.items():
        machine_name = m_data.get('machine_name', machine_id)
        m_summary = m_data.get('summary', {})
        overall_util = m_summary.get('overall_utilization', 0)
        bottleneck = m_summary.get('bottleneck_level', 'normal')
        total_cap = m_summary.get('total_capacity_hours', 0)
        total_used = m_summary.get('total_used_hours', 0)
        total_remain = m_summary.get('total_remaining_hours', 0)
        full_shifts = m_summary.get('full_shifts', [])

        if bottleneck == 'critical':
            level_str = f"{RED}瓶颈critical{RESET}"
        elif bottleneck == 'warning':
            level_str = f"{YELLOW}警告warning{RESET}"
        else:
            level_str = f"{GREEN}正常normal{RESET}"

        print(f"\n🖨️  机器: {machine_name} ({machine_id})  利用率: {overall_util:.0%}  {level_str}")
        print("-" * 100)

        m_dates = m_data.get('dates', {})
        for d in forecast_dates:
            d_data = m_dates.get(d)
            if not d_data:
                continue
            date_str = d.strftime('%Y-%m-%d')
            today_mark = "  ▶今天" if d == today else ""
            print(f"  📅 {date_str}{today_mark}")

            shifts = d_data.get('shifts', {})
            for shift_name, s_data in shifts.items():
                total = s_data.get('total_hours', 0)
                used = s_data.get('used_hours', 0)
                remain = s_data.get('remaining_hours', 0)
                util = s_data.get('utilization', 0)
                is_full = s_data.get('is_full', False)
                orders = s_data.get('orders', [])

                line = f"    {shift_name}: 总{total:.1f}h / 已用{used:.1f}h / 剩余{remain:.1f}h / 利用率{util:.0%}"
                if is_full:
                    line += f"  {RED}【已塞满】{RESET}"
                print(line)

                if orders:
                    order_display = ','.join(orders[:3])
                    if len(orders) > 3:
                        order_display += '...'
                    print(f"      订单数:{len(orders)} {order_display}")

            daily_total = d_data.get('daily_total_hours', 0)
            daily_used = d_data.get('daily_used_hours', 0)
            daily_remaining = d_data.get('daily_remaining_hours', 0)
            daily_util = d_data.get('daily_utilization', 0)
            print(f"    📊 合计: {daily_total:.1f}/{daily_used:.1f}/{daily_remaining:.1f}h 利用率{daily_util:.0%}")

        print(f"  {'='*90}")
        print(f"  📈 机器汇总: 总容量{total_cap:.1f}h 已用{total_used:.1f}h 剩余{total_remain:.1f}h 利用率{overall_util:.0%}")
        if full_shifts:
            print(f"  {RED}⚠️  已塞满班次: {', '.join(full_shifts)}{RESET}")

    print(f"\n{'='*100}")
    print("🏭 全厂汇总")
    print(f"{'='*100}")

    all_full = summary.get('all_full_shifts', [])
    bottleneck_machines = summary.get('bottleneck_machines', [])
    recommended = summary.get('recommended_action', '')

    if all_full:
        print(f"  {RED}⚠️  已塞满的班次 ({len(all_full)} 个):{RESET}")
        for fs in all_full:
            print(f"      - {fs}")
    else:
        print(f"  {GREEN}✅ 没有已塞满的班次{RESET}")

    if bottleneck_machines:
        print(f"  {RED}🔴 瓶颈机器 ({len(bottleneck_machines)} 台):{RESET}")
        for bm in bottleneck_machines:
            bm_name = machines.get(bm, {}).get('machine_name', bm)
            print(f"      - {bm_name} ({bm})")
    else:
        print(f"  {GREEN}✅ 无瓶颈机器{RESET}")

    print(f"\n  💡 建议: {recommended}")
    print(f"{'='*100}")


def export_daily_report_ui(scheduler: ProductionScheduler):
    print("\n--- 生产日报导出 ---")
    date_str = input("请输入日期 (YYYY-MM-DD, 回车默认今天): ").strip()
    try:
        if date_str:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            report_date = date.today()
    except ValueError:
        print("错误: 日期格式不正确！")
        return

    report = scheduler.generate_daily_report(report_date)

    print(f"\n{'='*90}")
    print(f"                  生产日报 - {report_date.strftime('%Y-%m-%d')}")
    print(f"{'='*90}")

    summary = report.get('summary', {})
    print(f"\n📊 汇总统计:")
    print(f"  完成订单数: {summary.get('total_completed', 0)}")
    print(f"  在制订单数: {summary.get('total_in_production', 0)}")
    print(f"  延期订单数: {summary.get('total_delayed', 0)}")
    print(f"  完成总印张: {summary.get('total_sheets', 0)}")
    factory_pause_min = summary.get('factory_total_pause_minutes', 0)
    factory_pause_cnt = summary.get('factory_total_pause_count', 0)
    if factory_pause_min > 0 or factory_pause_cnt > 0:
        print(f"  全厂暂停累计: {factory_pause_min}分钟/{factory_pause_cnt}次")

    print(f"\n⚙️  各机器详情:")
    print("-" * 90)
    print(f"{'机器':<12} {'完成数':<6} {'完成印张':<8} {'在制订单':<18} {'延期':<12} {'利用率':<6} {'暂停/受影响':<30}")
    print("-" * 90)
    machines = report.get('machines', {})
    for machine_id, machine_data in machines.items():
        utilization = machine_data.get('utilization', 0)
        in_prod = '、'.join(machine_data.get('in_production_orders', [])) or '-'
        delayed = '、'.join(machine_data.get('delayed_orders', [])) or '-'
        pause_min = machine_data.get('total_pause_minutes', 0)
        pause_cnt = machine_data.get('total_pause_count', 0)
        affected = machine_data.get('orders_affected_by_pause', [])
        pause_parts = []
        if pause_min > 0 or pause_cnt > 0:
            pause_parts.append(f"暂停:{pause_min}分钟/{pause_cnt}次")
        if affected:
            pause_parts.append(f"受影响: {','.join(affected)}")
        pause_str = '  '.join(pause_parts) or '-'
        print(f"{machine_data.get('machine_name', machine_id):<12} "
              f"{machine_data.get('completed_count', 0):<6} "
              f"{machine_data.get('completed_sheets', 0):<8} "
              f"{in_prod:<18} "
              f"{delayed:<12} "
              f"{utilization:.0%}   "
              f"{pause_str:<30}")
    print("-" * 90)

    export_confirm = input("\n是否导出CSV? (Y/n): ").strip().lower()
    if not export_confirm or export_confirm in ('y', 'yes', '是'):
        default_path = f"daily_report_{report_date.strftime('%Y%m%d')}.csv"
        file_path = input(f"导出文件路径 (默认: {default_path}): ").strip() or default_path
        if export_daily_report_to_csv(report, file_path):
            print(f"✅ 日报已导出到: {file_path}")
        else:
            print("❌ 导出失败！")


def main():
    datastore = DataStore()
    production_log = ProductionLog()
    machines = create_default_machines()
    scheduler = ProductionScheduler(machines, calendar=WorkCalendar())

    print("\n" + "=" * 65)
    print("           欢迎使用印刷厂生产排程系统 v3.0")
    print("=" * 65)

    if datastore.has_saved_data():
        print("\n检测到已保存的数据。")
        load_choice = input("是否加载保存的数据? (Y/n): ").strip().lower()
        if not load_choice or load_choice in ('y', 'yes', '是'):
            data = datastore.load_all()
            if data.get('exists'):
                scheduler.orders = data['orders']
                if data['machines']:
                    scheduler.machines = data['machines']
                scheduler.machine_schedules = {m.machine_id: [] for m in scheduler.machines}
                if data['calendar']:
                    scheduler.calendar = WorkCalendar.from_dict(data['calendar'])
                if data['production_log']:
                    production_log.events = data['production_log'].events
                scheduler.downtime_records = []
                for dr in data.get('downtime_records', []):
                    from storage import _deserialize_datetime
                    scheduler.downtime_records.append(DowntimeRecord(
                        record_id=dr.get('record_id'),
                        machine_id=dr.get('machine_id'),
                        order_id=dr.get('order_id'),
                        start_time=_deserialize_datetime(dr.get('start_time')),
                        end_time=_deserialize_datetime(dr.get('end_time')),
                        reason=dr.get('reason', ''),
                        downtime_type=dr.get('downtime_type', 'unplanned')
                    ))
                production_log.add_event('data_loaded', None, None, "启动时加载数据")
                print(f"✅ 已加载数据: {len(scheduler.orders)} 个订单, {len(scheduler.machines)} 台机器")
            else:
                print("❌ 加载数据失败，使用默认配置。")

    print(f"\n已配置 {len(scheduler.machines)} 台印刷机:")
    for m in scheduler.machines:
        print(f"  {m.name} ({m.machine_id}): {m.min_grammage}g-{m.max_grammage}g, "
              f"速度 {m.speed_per_hour} 印张/小时")
    print("\n提示: 本系统支持滚动排程、延误风险分析、生产进度跟踪等功能。")
    print("      建议先导入订单 (菜单项13)，然后执行排程 (菜单项4)。")

    while True:
        print_menu()
        choice = input("\n请选择操作 (0-23): ").strip()

        need_autosave = False

        if choice == '0':
            print("\n正在保存数据...")
            datastore.save_all(
                scheduler.orders, scheduler.machines,
                scheduler.calendar.to_dict(),
                production_log, scheduler.downtime_records)
            production_log.add_event('data_saved', None, None, "退出时自动保存")
            print("\n感谢使用，再见！")
            break
        elif choice == '1':
            view_all_orders(scheduler)
        elif choice == '2':
            add_order(scheduler, production_log)
            need_autosave = True
        elif choice == '3':
            modify_order_delivery(scheduler)
        elif choice == '4':
            run_schedule(scheduler, production_log)
            need_autosave = True
        elif choice == '5':
            insert_urgent_order(scheduler, production_log)
            need_autosave = True
        elif choice == '6':
            view_gantt(scheduler)
        elif choice == '7':
            mark_order_started(scheduler, production_log)
            need_autosave = True
        elif choice == '8':
            mark_order_completed_ui(scheduler, production_log)
            need_autosave = True
        elif choice == '9':
            update_order_progress_ui(scheduler)
            need_autosave = True
        elif choice == '10':
            auto_update_status(scheduler, production_log)
            need_autosave = True
        elif choice == '11':
            show_material_suggestions(scheduler)
        elif choice == '12':
            show_delay_risks(scheduler)
        elif choice == '13':
            import_orders(scheduler, production_log)
            need_autosave = True
        elif choice == '14':
            export_schedule(scheduler)
        elif choice == '15':
            export_orders(scheduler)
        elif choice == '16':
            manage_shifts(scheduler)
            need_autosave = True
        elif choice == '17':
            manage_holidays(scheduler)
            need_autosave = True
        elif choice == '18':
            manage_pause_resume(scheduler, production_log)
            need_autosave = True
        elif choice == '19':
            record_downtime_ui(scheduler, production_log)
            need_autosave = True
        elif choice == '20':
            save_data_ui(datastore, scheduler, production_log)
        elif choice == '21':
            load_data_ui(datastore, scheduler, production_log)
            need_autosave = True
        elif choice == '22':
            export_daily_report_ui(scheduler)
        elif choice == '23':
            show_capacity_forecast(scheduler)
        else:
            print("无效选择，请重新输入！")

        if choice != '0' and need_autosave:
            datastore.save_all(
                scheduler.orders, scheduler.machines,
                scheduler.calendar.to_dict(),
                production_log, scheduler.downtime_records)

        if choice != '0':
            input("\n按回车键继续...")


if __name__ == "__main__":
    main()