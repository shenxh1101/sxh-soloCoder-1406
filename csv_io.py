import csv
from datetime import date, datetime
from typing import List, Dict, Tuple, Optional
from models import Order, OrderStatus, ScheduleSlot


STATUS_MAP = {
    '待排产': OrderStatus.PENDING,
    '未开工': OrderStatus.NOT_STARTED,
    '生产中': OrderStatus.IN_PRODUCTION,
    '已完成': OrderStatus.COMPLETED,
    '暂停中': OrderStatus.PAUSED,
    'PENDING': OrderStatus.PENDING,
    'NOT_STARTED': OrderStatus.NOT_STARTED,
    'IN_PRODUCTION': OrderStatus.IN_PRODUCTION,
    'COMPLETED': OrderStatus.COMPLETED,
    'PAUSED': OrderStatus.PAUSED,
}


def parse_date(date_str: str) -> Optional[date]:
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%Y%m%d',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.date()
        except ValueError:
            continue
    return None


def parse_datetime(datetime_str: str) -> Optional[datetime]:
    if not datetime_str or not datetime_str.strip():
        return None
    datetime_str = datetime_str.strip()
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(datetime_str, fmt)
        except ValueError:
            continue
    return None


def parse_bool(value: str) -> bool:
    if not value:
        return False
    return str(value).strip().lower() in ('true', '是', '1', 'yes', 'y', '紧急')


def parse_int(value: str, default: int = 0) -> int:
    if not value or not str(value).strip():
        return default
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def get_value(row: Dict, *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return str(row[key])
    return ''


def import_orders_from_csv(file_path: str, existing_orders: List[Order] = None) -> Dict:
    result = {
        'orders': [],
        'success': 0,
        'duplicate': 0,
        'invalid': 0,
        'errors': [],
        'warnings': []
    }

    existing_ids = set()
    if existing_orders:
        existing_ids = set(o.order_id for o in existing_orders)

    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                result['warnings'].append(f"检测到列: {', '.join(reader.fieldnames)}")

            for line_num, row in enumerate(reader, start=2):
                try:
                    order_id = get_value(row, 'order_id', '订单号', '订单编号', 'id').strip()
                    if not order_id:
                        result['invalid'] += 1
                        result['errors'].append(f"第{line_num}行: 缺少订单号")
                        continue

                    if order_id in existing_ids:
                        result['duplicate'] += 1
                        result['warnings'].append(f"第{line_num}行: 订单 {order_id} 已存在，跳过")
                        continue

                    paper_grammage = parse_int(get_value(row, 'paper_grammage', '纸张克重', '克重', '纸张克重(g)'))
                    if paper_grammage < 60 or paper_grammage > 300:
                        result['invalid'] += 1
                        result['errors'].append(f"第{line_num}行: 纸张克重 {paper_grammage}g 超出范围 (60-300g)")
                        continue

                    sheet_count = parse_int(get_value(row, 'sheet_count', '印张数量', '印张', '数量'))
                    if sheet_count <= 0:
                        result['invalid'] += 1
                        result['errors'].append(f"第{line_num}行: 印张数量必须大于0")
                        continue

                    delivery_date_str = get_value(row, 'delivery_date', '交货日期', '交货期', '交期')
                    delivery_date = parse_date(delivery_date_str)
                    if not delivery_date:
                        result['invalid'] += 1
                        result['errors'].append(f"第{line_num}行: 交货日期格式无效 '{delivery_date_str}'")
                        continue

                    status_str = get_value(row, 'status', '状态', '订单状态')
                    status = STATUS_MAP.get(status_str, OrderStatus.PENDING)

                    is_urgent = parse_bool(get_value(row, 'is_urgent', '是否紧急', '紧急', 'urgent'))

                    assigned_machine = get_value(row, 'assigned_machine', '分配机器', '机器', 'machine') or None
                    if not assigned_machine:
                        assigned_machine = None

                    scheduled_start = parse_datetime(get_value(row, 'scheduled_start', '计划开始', '计划开始时间', '开始时间'))
                    scheduled_end = parse_datetime(get_value(row, 'scheduled_end', '计划结束', '计划结束时间', '结束时间'))
                    actual_start = parse_datetime(get_value(row, 'actual_start', '实际开始', '实际开工', '实际开始时间', '开工时间'))
                    actual_end = parse_datetime(get_value(row, 'actual_end', '实际结束', '实际完工', '实际结束时间', '完工时间'))

                    completed_sheets = parse_int(get_value(row, 'completed_sheets', '完成印张', '已完成', '完成数量'))
                    notes = get_value(row, 'notes', '备注', '说明')

                    if status in (OrderStatus.IN_PRODUCTION, OrderStatus.COMPLETED) and not assigned_machine:
                        result['warnings'].append(f"第{line_num}行: 订单 {order_id} 状态为{status.value}但未分配机器，已重置为待排产")
                        status = OrderStatus.PENDING

                    order = Order(
                        order_id=order_id,
                        paper_grammage=paper_grammage,
                        sheet_count=sheet_count,
                        delivery_date=delivery_date,
                        status=status,
                        is_urgent=is_urgent,
                        assigned_machine=assigned_machine,
                        scheduled_start=scheduled_start,
                        scheduled_end=scheduled_end,
                        actual_start=actual_start,
                        actual_end=actual_end,
                        completed_sheets=completed_sheets,
                        notes=notes
                    )

                    result['orders'].append(order)
                    result['success'] += 1
                    existing_ids.add(order_id)

                except (ValueError, KeyError) as e:
                    result['invalid'] += 1
                    result['errors'].append(f"第{line_num}行: 数据格式错误 - {e}")

    except FileNotFoundError:
        result['errors'].append(f"文件不存在 - {file_path}")
    except UnicodeDecodeError:
        result['errors'].append(f"文件编码错误，请使用 UTF-8 编码 - {file_path}")
    except Exception as e:
        result['errors'].append(f"读取文件失败 - {e}")

    return result


def export_orders_to_csv(orders: List[Order], file_path: str) -> bool:
    try:
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                '订单号', '纸张克重(g)', '印张数量', '交货日期',
                '状态', '是否紧急', '分配机器',
                '计划开始', '计划结束',
                '实际开工', '实际完工',
                '完成印张', '备注'
            ])
            for order in orders:
                writer.writerow([
                    order.order_id,
                    order.paper_grammage,
                    order.sheet_count,
                    order.delivery_date.strftime('%Y-%m-%d'),
                    order.status.value,
                    '是' if order.is_urgent else '否',
                    order.assigned_machine or '',
                    order.scheduled_start.strftime('%Y-%m-%d %H:%M') if order.scheduled_start else '',
                    order.scheduled_end.strftime('%Y-%m-%d %H:%M') if order.scheduled_end else '',
                    order.actual_start.strftime('%Y-%m-%d %H:%M') if order.actual_start else '',
                    order.actual_end.strftime('%Y-%m-%d %H:%M') if order.actual_end else '',
                    order.completed_sheets,
                    order.notes
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
                '机器ID', '机器名称', '订单号',
                '纸张克重(g)', '印张数量',
                '开始时间', '结束时间',
                '换单时间(分钟)', '生产时长(小时)',
                '交货日期', '订单状态', '是否紧急'
            ])
            for slot in sorted(slots, key=lambda s: (s.machine_id, s.start_time)):
                order = slot.order
                production_hours = (slot.end_time - slot.start_time).total_seconds() / 3600.0
                writer.writerow([
                    slot.machine_id,
                    '',
                    order.order_id,
                    order.paper_grammage,
                    order.sheet_count,
                    slot.start_time.strftime('%Y-%m-%d %H:%M'),
                    slot.end_time.strftime('%Y-%m-%d %H:%M'),
                    slot.setup_time_minutes,
                    round(production_hours, 2),
                    order.delivery_date.strftime('%Y-%m-%d'),
                    order.status.value,
                    '是' if order.is_urgent else '否'
                ])
        return True
    except Exception as e:
        print(f"错误: 导出排程CSV失败 - {e}")
        return False


def export_daily_report_to_csv(report: Dict, file_path: str) -> bool:
    try:
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            report_date = report.get('report_date')
            summary = report.get('summary', {})
            writer.writerow(['日期', '完成订单数', '在制订单数', '延期订单数', '完成总印张'])
            writer.writerow([
                report_date.strftime('%Y-%m-%d') if report_date else '',
                summary.get('total_completed', 0),
                summary.get('total_in_production', 0),
                summary.get('total_delayed', 0),
                summary.get('total_sheets', 0)
            ])
            writer.writerow([])
            writer.writerow(['机器ID', '完成订单数', '完成印张', '在制订单', '延期订单', '利用率%'])
            machines = report.get('machines', {})
            for machine_id, machine_data in machines.items():
                utilization = machine_data.get('utilization', 0)
                utilization_pct = round(utilization * 100, 2)
                writer.writerow([
                    machine_id,
                    machine_data.get('completed_count', 0),
                    machine_data.get('completed_sheets', 0),
                    '、'.join(machine_data.get('in_production_orders', [])),
                    '、'.join(machine_data.get('delayed_orders', [])),
                    utilization_pct
                ])
        return True
    except Exception as e:
        print(f"错误: 导出生产日报CSV失败 - {e}")
        return False


