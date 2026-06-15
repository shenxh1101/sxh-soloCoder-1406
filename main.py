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
    print("\n" + "=" * 60)
    print("       印刷厂生产排程系统")
    print("=" * 60)
    print("  1. 查看所有订单")
    print("  2. 添加新订单")
    print("  3. 执行排程")
    print("  4. 查看甘特图")
    print("  5. 紧急插单")
    print("  6. 按状态筛选订单")
    print("  7. 标记订单完成")
    print("  8. 物料合并提醒")
    print("  9. 导入订单 (CSV)")
    print(" 10. 导出排程 (CSV)")
    print(" 11. 导出订单 (CSV)")
    print("  0. 退出系统")
    print("=" * 60)


def view_all_orders(scheduler: ProductionScheduler):
    if not scheduler.orders:
        print("\n暂无订单。")
        return

    print("\n" + "=" * 90)
    print("所有订单列表")
    print("-" * 90)
    print(f"{'订单号':<12} {'纸张克重':<10} {'印张数量':<10} {'交货日期':<12} {'状态':<10} {'紧急':<6} {'分配机器':<10}")
    print("-" * 90)

    for order in sorted(scheduler.orders, key=lambda o: o.delivery_date):
        urgent = "是" if order.is_urgent else "否"
        machine = order.assigned_machine or "-"
        print(f"{order.order_id:<12} {order.paper_grammage:<10}g {order.sheet_count:<10} "
              f"{order.delivery_date.strftime('%Y-%m-%d'):<12} {order.status.value:<10} {urgent:<6} {machine:<10}")
    print("=" * 90)


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
        print(f"\n订单 {order_id} 添加成功！")

    except ValueError:
        print("错误: 输入格式不正确！")


def run_schedule(scheduler: ProductionScheduler):
    print("\n--- 执行生产排程 ---")

    pending_count = len([o for o in scheduler.orders if o.status == OrderStatus.PENDING])
    if pending_count == 0:
        print("没有待排产的订单。")
        return

    slots = scheduler.schedule_all()
    print(f"\n排程完成！共排程 {len(slots)} 个订单。")

    print("\n排程结果摘要:")
    for machine in scheduler.machines:
        machine_slots = scheduler.machine_schedules.get(machine.machine_id, [])
        if machine_slots:
            first_start = machine_slots[0].start_time
            last_end = machine_slots[-1].end_time
            total_hours = sum((s.end_time - s.start_time).total_seconds() / 3600.0 for s in machine_slots)
            print(f"  {machine.name}: {len(machine_slots)} 个订单, "
                  f"{first_start.strftime('%m-%d %H:%M')} ~ {last_end.strftime('%m-%d %H:%M')}, "
                  f"总时长 {total_hours:.1f} 小时")

    late_orders = []
    for order in scheduler.orders:
        if order.status == OrderStatus.SCHEDULED and order.end_time:
            if order.end_time.date() > order.delivery_date:
                delay_days = (order.end_time.date() - order.delivery_date).days
                late_orders.append((order, delay_days))

    if late_orders:
        print("\n⚠️  延期订单警告:")
        for order, delay in late_orders:
            print(f"  {order.order_id}: 延期 {delay} 天 (计划完成: {order.end_time.strftime('%Y-%m-%d')}, "
                  f"交货日期: {order.delivery_date.strftime('%Y-%m-%d')})")


def view_gantt(scheduler: ProductionScheduler):
    print("\n--- 查看甘特图 ---")
    print("  1. 多日概览甘特图")
    print("  2. 单日详细甘特图")
    choice = input("请选择 (1-2, 默认1): ").strip() or "1"

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

            chart = generate_gantt_chart(scheduler.machines, scheduler.machine_schedules, start_date, end_date)
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

            chart = generate_daily_gantt(scheduler.machines, scheduler.machine_schedules, target_date)
            print("\n" + chart)
        except ValueError:
            print("错误: 日期格式不正确！")


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

        result = scheduler.insert_urgent_order(urgent_order)

        print(f"\n紧急订单 {order_id} 已插入并排程！")
        print(f"  分配机器: {urgent_order.assigned_machine}")
        print(f"  开始时间: {urgent_order.start_time.strftime('%Y-%m-%d %H:%M') if urgent_order.start_time else '未排程'}")
        print(f"  结束时间: {urgent_order.end_time.strftime('%Y-%m-%d %H:%M') if urgent_order.end_time else '未排程'}")

        affected = result['affected_orders']
        if affected:
            print(f"\n受影响订单 ({len(affected)} 个):")
            print("-" * 70)
            print(f"{'订单号':<12} {'原完成时间':<20} {'新完成时间':<20} {'延期天数':<8}")
            print("-" * 70)
            for item in affected:
                print(f"{item['order_id']:<12} "
                      f"{item['original_end'].strftime('%Y-%m-%d %H:%M'):<20} "
                      f"{item['new_end'].strftime('%Y-%m-%d %H:%M'):<20} "
                      f"{item['delay_days']:<8}天")
        else:
            print("\n其他订单不受影响。")

    except ValueError:
        print("错误: 输入格式不正确！")


def filter_orders_by_status(scheduler: ProductionScheduler):
    print("\n--- 按状态筛选订单 ---")
    print("  1. 待排产")
    print("  2. 已排产")
    print("  3. 生产中")
    print("  4. 已完成")
    choice = input("请选择 (1-4): ").strip()

    status_map = {
        '1': OrderStatus.PENDING,
        '2': OrderStatus.SCHEDULED,
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
    print("-" * 80)
    print(f"{'订单号':<12} {'纸张克重':<10} {'印张数量':<10} {'交货日期':<12} {'机器':<10}")
    print("-" * 80)
    for order in sorted(orders, key=lambda o: o.delivery_date):
        machine = order.assigned_machine or "-"
        print(f"{order.order_id:<12} {order.paper_grammage:<10}g {order.sheet_count:<10} "
              f"{order.delivery_date.strftime('%Y-%m-%d'):<12} {machine:<10}")


def mark_order_completed(scheduler: ProductionScheduler):
    print("\n--- 标记订单完成 ---")
    scheduled_orders = [o for o in scheduler.orders
                        if o.status in (OrderStatus.SCHEDULED, OrderStatus.IN_PRODUCTION)]

    if not scheduled_orders:
        print("没有可标记完成的订单。")
        return

    print("可标记完成的订单:")
    for i, order in enumerate(scheduled_orders, 1):
        print(f"  {i}. {order.order_id} - {order.status.value} - 纸张:{order.paper_grammage}g")

    try:
        choice = input("\n请输入订单序号或订单号: ").strip()
        target_order = None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(scheduled_orders):
                target_order = scheduled_orders[idx]
        else:
            for order in scheduled_orders:
                if order.order_id == choice:
                    target_order = order
                    break

        if target_order:
            if scheduler.mark_order_completed(target_order.order_id):
                print(f"订单 {target_order.order_id} 已标记为已完成。")
            else:
                print("标记失败！")
        else:
            print("未找到该订单！")
    except ValueError:
        print("输入无效！")


def show_material_suggestions(scheduler: ProductionScheduler):
    print("\n--- 物料合并提醒 ---")
    suggestions = scheduler.get_material_merge_suggestions()

    if not suggestions:
        print("暂无合并建议。")
        return

    print(f"发现 {len(suggestions)} 个合并机会:")
    print("-" * 70)
    for i, suggestion in enumerate(suggestions, 1):
        print(f"\n建议 #{i}:")
        print(f"  机器: {suggestion['machine_id']}")
        print(f"  纸张克重: {suggestion['paper_grammage']}g")
        print(f"  涉及订单: {', '.join(suggestion['orders'])}")
        print(f"  总印张数: {suggestion['total_sheets']}")
        print(f"  可节省换单时间: {suggestion['saved_setup_minutes']} 分钟")

    print("\n提示: 将相同纸张的订单连续安排生产，可减少换单清洗时间。")


def import_orders(scheduler: ProductionScheduler):
    print("\n--- 导入订单 (CSV) ---")
    file_path = input("CSV文件路径: ").strip()

    if not file_path:
        print("错误: 文件路径不能为空！")
        return

    orders = import_orders_from_csv(file_path)
    if orders:
        for order in orders:
            exists = any(o.order_id == order.order_id for o in scheduler.orders)
            if not exists:
                scheduler.add_order(order)
            else:
                print(f"  跳过重复订单: {order.order_id}")

        new_count = len([o for o in orders
                        if not any(ext.order_id == o.order_id for ext in scheduler.orders)])
        print(f"\n成功导入 {len(orders)} 个订单！")


def export_schedule(scheduler: ProductionScheduler):
    print("\n--- 导出排程 (CSV) ---")
    file_path = input("导出文件路径 (默认: schedule.csv): ").strip() or "schedule.csv"

    all_slots = scheduler.get_all_slots()
    if not all_slots:
        print("暂无排程数据，请先执行排程。")
        return

    if export_schedule_to_csv(all_slots, file_path):
        print(f"排程已导出到: {file_path}")


def export_orders(scheduler: ProductionScheduler):
    print("\n--- 导出订单 (CSV) ---")
    file_path = input("导出文件路径 (默认: orders.csv): ").strip() or "orders.csv"

    if not scheduler.orders:
        print("暂无订单数据。")
        return

    if export_orders_to_csv(scheduler.orders, file_path):
        print(f"订单已导出到: {file_path}")


def main():
    machines = create_default_machines()
    scheduler = ProductionScheduler(machines)

    print("\n欢迎使用印刷厂生产排程系统！")
    print(f"已配置 {len(machines)} 台印刷机:")
    for m in machines:
        print(f"  {m.name}: {m.min_grammage}g-{m.max_grammage}g, 速度 {m.speed_per_hour} 印张/小时")

    while True:
        print_menu()
        choice = input("\n请选择操作 (0-11): ").strip()

        if choice == '0':
            print("\n感谢使用，再见！")
            break
        elif choice == '1':
            view_all_orders(scheduler)
        elif choice == '2':
            add_order(scheduler)
        elif choice == '3':
            run_schedule(scheduler)
        elif choice == '4':
            view_gantt(scheduler)
        elif choice == '5':
            insert_urgent_order(scheduler)
        elif choice == '6':
            filter_orders_by_status(scheduler)
        elif choice == '7':
            mark_order_completed(scheduler)
        elif choice == '8':
            show_material_suggestions(scheduler)
        elif choice == '9':
            import_orders(scheduler)
        elif choice == '10':
            export_schedule(scheduler)
        elif choice == '11':
            export_orders(scheduler)
        else:
            print("无效选择，请重新输入！")

        input("\n按回车键继续...")


if __name__ == "__main__":
    main()


