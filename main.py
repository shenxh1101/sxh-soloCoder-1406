import sys
from datetime import date, datetime, timedelta
from models import Order, PrintingMachine, OrderStatus
from scheduler import ProductionScheduler
from gantt import generate_gantt_chart, generate_daily_gantt
from csv_io import import_orders_from_csv, export_orders_to_csv, export_schedule_to_csv


def create_default_machines():
    return [
        PrintingMachine("M1", "印刷机1号", 60, 157, 5000),
        PrintingMachine("M2", "印刷机2号", 128, 250, 4000),
        PrintingMachine("M3", "印刷机3号", 200, 300, 3000),
    ]


def print_menu():
    print("\n" + "=" * 65)
    print("       印刷厂生产排程系统 v2.0")
    print("=" * 65)
    print("  ┌───────────── 订单管理 ─────────────┐  ┌───────────── 生产执行 ─────────────┐")
    print("  │  1. 查看所有订单      2. 添加订单   │  │  7. 登记开工        8. 登记完工     │")
    print("  │  3. 修改订单交期    12. 延误风险   │  │  9. 更新进度       10. 自动更新状态  │")
    print("  └─────────────────────────────────────┘  └────────────────────────────────────┘")
    print("  ┌───────────── 排程计划 ─────────────┐  ┌───────────── 数据交换 ─────────────┐")
    print("  │  4. 执行滚动排程     5. 紧急插单   │  │ 13. 导入订单CSV   14. 导出排程CSV   │")
    print("  │  6. 查看甘特图     11. 物料提醒    │  │ 15. 导出订单CSV                     │")
    print("  └─────────────────────────────────────┘  └────────────────────────────────────┘")
    print("  0. 退出系统")
    print("=" * 65)


def view_all_orders(scheduler: ProductionScheduler):
    if not scheduler.orders:
        print("\n暂无订单。")
        return

    scheduler.update_order_status_by_time()

    print("\n" + "=" * 120)
    print("所有订单列表")
    print("-" * 120)
    print(f"{'订单号':<12} {'克重':<6} {'印张':<10} {'交货日期':<12} {'状态':<10} {'紧急':<6} "
          f"{'机器':<8} {'计划开始':<16} {'计划结束':<16} {'进度':<8} {'延期':<6}")
    print("-" * 120)

    for order in sorted(scheduler.orders, key=lambda o: (o.delivery_date, -o.is_urgent)):
        urgent = "是" if order.is_urgent else "否"
        machine = order.assigned_machine or "-"
        s_start = order.scheduled_start.strftime("%m-%d %H:%M") if order.scheduled_start else "-"
        s_end = order.scheduled_end.strftime("%m-%d %H:%M") if order.scheduled_end else "-"
        progress = f"{order.progress:.0%}" if order.status == OrderStatus.IN_PRODUCTION else "-"
        delay = f"{order.delay_days}天" if order.is_delayed and order.status != OrderStatus.COMPLETED else "-"

        line = f"{order.order_id:<12} {order.paper_grammage:<5}g {order.sheet_count:<10} " \
               f"{order.delivery_date.strftime('%Y-%m-%d'):<12} {order.status.value:<10} {urgent:<6} " \
               f"{machine:<8} {s_start:<16} {s_end:<16} {progress:<8} {delay:<6}"

        if order.is_delayed and order.status != OrderStatus.COMPLETED:
            line = "⚠️  " + line
        elif order.is_urgent and order.status != OrderStatus.COMPLETED:
            line = "⚡ " + line

        print(line)

    print("-" * 120)
    print(f"总计: {len(scheduler.orders)} 个订单 | "
          f"待排产:{len(scheduler.get_orders_by_status(OrderStatus.PENDING))} "
          f"未开工:{len(scheduler.get_orders_by_status(OrderStatus.NOT_STARTED))} "
          f"生产中:{len(scheduler.get_orders_by_status(OrderStatus.IN_PRODUCTION))} "
          f"已完成:{len(scheduler.get_orders_by_status(OrderStatus.COMPLETED))}")
    print("=" * 120)


def add_order(scheduler: ProductionScheduler):
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


def run_schedule(scheduler: ProductionScheduler):
    print("\n--- 执行滚动排程 ---")

    total_orders = len(scheduler.orders)
    locked_count = len([o for o in scheduler.orders
                      if o.status in (OrderStatus.IN_PRODUCTION, OrderStatus.COMPLETED)])
    pending_count = len([o for o in scheduler.orders
                        if o.status in (OrderStatus.PENDING, OrderStatus.NOT_STARTED)])

    print(f"当前总订单数: {total_orders}")
    print(f"  - 锁定订单 (生产中/已完成): {locked_count}")
    print(f"  - 待排程订单: {pending_count}")

    if pending_count == 0 and locked_count == 0:
        print("\n没有订单可以排程，请先添加订单。")
        return

    confirm = input(f"\n是否重新排程所有 {pending_count} 个未完成订单? (Y/n): ").strip().lower()
    if confirm and confirm not in ('y', 'yes', '是'):
        print("已取消排程。")
        return

    result = scheduler.schedule_all(reschedule_all=True)

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
            available_hours = total_days * 12
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
                end_date
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
                target_date
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


def insert_urgent_order(scheduler: ProductionScheduler):
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
    print("  4. 已完成")
    choice = input("请选择 (1-4): ").strip()

    status_map = {
        '1': OrderStatus.PENDING,
        '2': OrderStatus.NOT_STARTED,
        '3': OrderStatus.IN_PRODUCTION,
        '4': OrderStatus.COMPLETED,
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
    print("-" * 90)
    print(f"{'订单号':<12} {'克重':<6} {'印张':<10} {'交货日期':<12} {'机器':<8} {'计划结束':<16} {'进度':<8}")
    print("-" * 90)
    for order in sorted(orders, key=lambda o: o.delivery_date):
        machine = order.assigned_machine or "-"
        s_end = order.scheduled_end.strftime("%m-%d %H:%M") if order.scheduled_end else "-"
        progress = f"{order.progress:.0%}" if order.status == OrderStatus.IN_PRODUCTION else "-"
        print(f"{order.order_id:<12} {order.paper_grammage:<5}g {order.sheet_count:<10} "
              f"{order.delivery_date.strftime('%Y-%m-%d'):<12} {machine:<8} {s_end:<16} {progress:<8}")


def mark_order_started(scheduler: ProductionScheduler):
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
                print(f"订单 {target_order.order_id} 已登记开工，开工时间: {actual_time.strftime('%Y-%m-%d %H:%M')}")
            else:
                print("标记失败！")
        else:
            print("未找到该订单！")
    except ValueError:
        print("输入无效！")


def mark_order_completed_ui(scheduler: ProductionScheduler):
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


def auto_update_status(scheduler: ProductionScheduler):
    print("\n--- 自动更新订单状态 ---")
    now = datetime.now()
    result = scheduler.update_order_status_by_time(now)

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


def import_orders(scheduler: ProductionScheduler):
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


def main():
    machines = create_default_machines()
    scheduler = ProductionScheduler(machines)

    print("\n" + "=" * 65)
    print("           欢迎使用印刷厂生产排程系统 v2.0")
    print("=" * 65)
    print(f"已配置 {len(machines)} 台印刷机:")
    for m in machines:
        print(f"  {m.name} ({m.machine_id}): {m.min_grammage}g-{m.max_grammage}g, "
              f"速度 {m.speed_per_hour} 印张/小时")
    print("\n提示: 本系统支持滚动排程、延误风险分析、生产进度跟踪等功能。")
    print("      建议先导入订单 (菜单项13)，然后执行排程 (菜单项4)。")

    while True:
        print_menu()
        choice = input("\n请选择操作 (0-15): ").strip()

        if choice == '0':
            print("\n感谢使用，再见！")
            break
        elif choice == '1':
            view_all_orders(scheduler)
        elif choice == '2':
            add_order(scheduler)
        elif choice == '3':
            modify_order_delivery(scheduler)
        elif choice == '4':
            run_schedule(scheduler)
        elif choice == '5':
            insert_urgent_order(scheduler)
        elif choice == '6':
            view_gantt(scheduler)
        elif choice == '7':
            mark_order_started(scheduler)
        elif choice == '8':
            mark_order_completed_ui(scheduler)
        elif choice == '9':
            update_order_progress_ui(scheduler)
        elif choice == '10':
            auto_update_status(scheduler)
        elif choice == '11':
            show_material_suggestions(scheduler)
        elif choice == '12':
            show_delay_risks(scheduler)
        elif choice == '13':
            import_orders(scheduler)
        elif choice == '14':
            export_schedule(scheduler)
        elif choice == '15':
            export_orders(scheduler)
        else:
            print("无效选择，请重新输入！")

        if choice != '0':
            input("\n按回车键继续...")


if __name__ == "__main__":
    main()


