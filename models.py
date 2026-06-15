from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Optional


class OrderStatus(Enum):
    PENDING = "待排产"
    SCHEDULED = "已排产"
    IN_PRODUCTION = "生产中"
    COMPLETED = "已完成"


@dataclass
class Order:
    order_id: str
    paper_grammage: int
    sheet_count: int
    delivery_date: date
    status: OrderStatus = OrderStatus.PENDING
    is_urgent: bool = False
    assigned_machine: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def production_hours(self, speed_per_hour: int) -> float:
        if speed_per_hour <= 0:
            return float('inf')
        return self.sheet_count / speed_per_hour


@dataclass
class PrintingMachine:
    machine_id: str
    name: str
    min_grammage: int
    max_grammage: int
    speed_per_hour: int

    def can_print(self, grammage: int) -> bool:
        return self.min_grammage <= grammage <= self.max_grammage


@dataclass
class ScheduleSlot:
    machine_id: str
    order: Order
    start_time: datetime
    end_time: datetime
    setup_time_minutes: int = 30
