import json
import os
from datetime import datetime, date
from typing import Dict, List, Any, Optional
from models import Order, OrderStatus, PrintingMachine, ScheduleSlot


def _serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _deserialize_datetime(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _serialize_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _deserialize_date(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def order_to_dict(order: Order) -> Dict:
    return {
        "order_id": order.order_id,
        "paper_grammage": order.paper_grammage,
        "sheet_count": order.sheet_count,
        "delivery_date": _serialize_date(order.delivery_date),
        "status": order.status.value,
        "is_urgent": order.is_urgent,
        "assigned_machine": order.assigned_machine,
        "scheduled_start": _serialize_datetime(order.scheduled_start),
        "scheduled_end": _serialize_datetime(order.scheduled_end),
        "actual_start": _serialize_datetime(order.actual_start),
        "actual_end": _serialize_datetime(order.actual_end),
        "completed_sheets": order.completed_sheets,
        "notes": order.notes,
    }


def dict_to_order(data: Dict) -> Order:
    status_map = {s.value: s for s in OrderStatus}
    order = Order(
        order_id=data["order_id"],
        paper_grammage=data["paper_grammage"],
        sheet_count=data["sheet_count"],
        delivery_date=_deserialize_date(data.get("delivery_date")),
        status=status_map.get(data.get("status", "待排产"), OrderStatus.PENDING),
        is_urgent=data.get("is_urgent", False),
        assigned_machine=data.get("assigned_machine"),
        completed_sheets=data.get("completed_sheets", 0),
        notes=data.get("notes", ""),
    )
    order.scheduled_start = _deserialize_datetime(data.get("scheduled_start"))
    order.scheduled_end = _deserialize_datetime(data.get("scheduled_end"))
    order.actual_start = _deserialize_datetime(data.get("actual_start"))
    order.actual_end = _deserialize_datetime(data.get("actual_end"))
    return order


def machine_to_dict(m: PrintingMachine) -> Dict:
    return {
        "machine_id": m.machine_id,
        "name": m.name,
        "min_grammage": m.min_grammage,
        "max_grammage": m.max_grammage,
        "speed_per_hour": m.speed_per_hour,
    }


def dict_to_machine(data: Dict) -> PrintingMachine:
    return PrintingMachine(
        machine_id=data["machine_id"],
        name=data["name"],
        min_grammage=data["min_grammage"],
        max_grammage=data["max_grammage"],
        speed_per_hour=data["speed_per_hour"],
    )


class ProductionLog:
    def __init__(self):
        self.events: List[Dict] = []

    VALID_EVENT_TYPES = {
        'order_added', 'order_started', 'order_completed', 'order_paused', 'order_resumed',
        'schedule_run', 'downtime_recorded', 'data_saved', 'data_loaded', 'status_auto_updated'
    }

    def add_event(self, event_type: str, order_id: Optional[str], machine_id: Optional[str],
                  details: str = "", timestamp: Optional[datetime] = None):
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}. Must be one of {self.VALID_EVENT_TYPES}")
        self.events.append({
            "timestamp": _serialize_datetime(timestamp or datetime.now()),
            "event_type": event_type,
            "order_id": order_id,
            "machine_id": machine_id,
            "details": details,
        })

    def get_events_by_date(self, d: date) -> List[Dict]:
        result = []
        for e in self.events:
            if e["timestamp"] and e["timestamp"][:10] == d.isoformat():
                result.append(e)
        return result

    def to_dict(self) -> Dict:
        return {"events": self.events}

    @classmethod
    def from_dict(cls, data: Dict) -> "ProductionLog":
        log = cls()
        log.events = data.get("events", [])
        return log


class DataStore:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def save_all(self, orders: List[Order], machines: List[PrintingMachine],
                 calendar_data: Optional[Dict] = None,
                 production_log: Optional[ProductionLog] = None,
                 downtime_records: Optional[List] = None) -> bool:
        try:
            data = {
                "version": "3.0",
                "saved_at": _serialize_datetime(datetime.now()),
                "orders": [order_to_dict(o) for o in orders],
                "machines": [machine_to_dict(m) for m in machines],
            }
            if calendar_data:
                data["calendar"] = calendar_data
            if production_log:
                data["production_log"] = production_log.to_dict()
            if downtime_records:
                data["downtime_records"] = [
                    {
                        'record_id': r.record_id,
                        'machine_id': r.machine_id,
                        'order_id': r.order_id,
                        'start_time': _serialize_datetime(r.start_time),
                        'end_time': _serialize_datetime(r.end_time),
                        'reason': r.reason,
                        'downtime_type': r.downtime_type,
                    }
                    for r in downtime_records
                ]

            path = os.path.join(self.data_dir, "factory_data.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存数据失败: {e}")
            return False

    def load_all(self) -> Dict:
        path = os.path.join(self.data_dir, "factory_data.json")
        if not os.path.exists(path):
            return {"orders": [], "machines": [], "calendar": None, "production_log": None, "downtime_records": [], "exists": False}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            orders = [dict_to_order(d) for d in data.get("orders", [])]
            machines = [dict_to_machine(d) for d in data.get("machines", [])]
            calendar_data = data.get("calendar")
            production_log = ProductionLog.from_dict(data["production_log"]) if data.get("production_log") else ProductionLog()
            downtime_records = data.get("downtime_records", [])
            return {
                "orders": orders,
                "machines": machines,
                "calendar": calendar_data,
                "production_log": production_log,
                "downtime_records": downtime_records,
                "exists": True,
                "saved_at": data.get("saved_at"),
            }
        except Exception as e:
            print(f"加载数据失败: {e}")
            return {"orders": [], "machines": [], "calendar": None, "production_log": None, "downtime_records": [], "exists": False}

    def has_saved_data(self) -> bool:
        return os.path.exists(os.path.join(self.data_dir, "factory_data.json"))

    def backup(self) -> Optional[str]:
        path = os.path.join(self.data_dir, "factory_data.json")
        if not os.path.exists(path):
            return None
        backup_path = os.path.join(
            self.data_dir,
            f"factory_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        try:
            with open(path, "r", encoding="utf-8") as src:
                with open(backup_path, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            return backup_path
        except Exception:
            return None
