import csv
from datetime import date, datetime
from typing import List, Dict
from models import Order, OrderStatus, ScheduleSlot


def import_orders_from_csv(file_path: str) -> List[Order]:
    orders = []
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    order_id = row.get('order_id', row.get('订单号', ''))
                    paper_grammage = int(row.get('paper_grammage', row.get('纸张克重', 0)))
                    sheet_count = int(row.get('sheet_count', row.get('印张数量', 0)))
                    delivery_date_str = row.get('delivery_date', row.get('交货日期', ''))

                    is_urgent_str = row.get('is_urgent', row.get('是否紧急', 'false')).lower()
                    is_urgent = is_urgent_str in ('true', '是', '1', 'yes')

                    status_str = row.get('status', row.get('状态', '待排产'))
                    status_map = {
                        '待排产': OrderStatus.PENDING,
                        '已排产': OrderStatus.SCHEDULED,
                        '生产中': OrderStatus.IN_PRODUCTION,
                        '已完成': OrderStatus.COMPLETED,
                        'PENDING': OrderStatus.PENDING,
                        'SCHEDULED': OrderStatus.SCHEDULED,
                        'IN_PRODUCTION': OrderStatus.IN_PRODUCTION,
                        'COMPLETED': OrderStatus.COMPLETED
                    }
                    status = status_map.get(status_str, OrderStatus.PENDING)

                    try:
                        delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        try:
                            delivery_date = datetime.strptime(delivery_date_str, '%Y/%m/%d').date()
                        except ValueError:
                            delivery_date = date.today()

                    if order_id and paper_grammage > 0 and sheet_count > 0:
                        order = Order(
                            order_id=order_id,
                            paper_grammage=paper_grammage,
                            sheet_count=sheet_count,
                            delivery_date=delivery_date,
                            status=status,
                            is_urgent=is_urgent
                        )
                        orders.append(order)
                except (ValueError, KeyError) as e:
                    print(f"警告: 跳过无效行 {row}: {e}")
    except FileNotFoundError:
        print(f"错误: 文件不存在 - {file_path}")
    except Exception as e:
        print(f"错误: 读取CSV文件失败 - {e}")

    return orders


def export_orders_to_csv(orders: List[Order], file_path: str) -> bool:
    try:
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                '订单号', '纸张克重(g)', '印张数量', '交货日期',
                '状态', '是否紧急', '分配机器', '开始时间', '结束时间'
            ])
            for order in orders:
                start_time_str = order.start_time.strftime('%Y-%m-%d %H:%M') if order.start_time else ''
                end_time_str = order.end_time.strftime('%Y-%m-%d %H:%M') if order.end_time else ''
                writer.writerow([
                    order.order_id,
                    order.paper_grammage,
                    order.sheet_count,
                    order.delivery_date.strftime('%Y-%m-%d'),
                    order.status.value,
                    '是' if order.is_urgent else '否',
                    order.assigned_machine or '',
                    start_time_str,
                    end_time_str
                ])
        return True
    except Exception as e:
        print(f"错误: 导出订单CSV失败 - {e}")
        return False


def export_schedule_to_csv(slots: List[ScheduleSlot], file_path: str) -> bool:
    try:
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                '机器ID', '订单号', '纸张克重(g)', '印张数量',
                '开始时间', '结束时间', '换单时间(分钟)', '交货日期'
            ])
            for slot in sorted(slots, key=lambda s: (s.machine_id, s.start_time)):
                writer.writerow([
                    slot.machine_id,
                    slot.order.order_id,
                    slot.order.paper_grammage,
                    slot.order.sheet_count,
                    slot.start_time.strftime('%Y-%m-%d %H:%M'),
                    slot.end_time.strftime('%Y-%m-%d %H:%M'),
                    slot.setup_time_minutes,
                    slot.order.delivery_date.strftime('%Y-%m-%d')
                ])
        return True
    except Exception as e:
        print(f"错误: 导出排程CSV失败 - {e}")
        return False


