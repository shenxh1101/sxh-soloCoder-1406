from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Optional, List, Dict


class OrderStatus(Enum):
    PENDING = "待排产"
    NOT_STARTED = "未开工"
    IN_PRODUCTION = "生产中"
    COMPLETED = "已完成"
    PAUSED = "暂停中"


@dataclass
class Order:
    order_id: str
    paper_grammage: int
    sheet_count: int
    delivery_date: date
    status: OrderStatus = OrderStatus.PENDING
    is_urgent: bool = False
    assigned_machine: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    completed_sheets: int = 0
    notes: str = ""
    pause_records: List[Dict] = field(default_factory=list)
    shift: Optional[str] = None
    start_shift: Optional[str] = None
    end_shift: Optional[str] = None
    pause_count: int = 0
    original_scheduled_end: Optional[datetime] = None

    def production_hours(self, speed_per_hour: int) -> float:
        if speed_per_hour <= 0:
            return float('inf')
        return self.sheet_count / speed_per_hour

    @property
    def start_time(self) -> Optional[datetime]:
        return self.actual_start or self.scheduled_start

    @property
    def end_time(self) -> Optional[datetime]:
        return self.actual_end or self.scheduled_end

    @property
    def progress(self) -> float:
        if self.sheet_count <= 0:
            return 0.0
        return min(self.completed_sheets / self.sheet_count, 1.0)

    @property
    def is_delayed(self) -> bool:
        if not self.end_time:
            return False
        end_date = self.end_time.date()
        return end_date > self.delivery_date

    @property
    def delay_days(self) -> int:
        if not self.end_time or not self.is_delayed:
            return 0
        return (self.end_time.date() - self.delivery_date).days

    @property
    def total_pause_minutes(self) -> int:
        total = 0
        for record in self.pause_records:
            pause_time = record.get("pause_time")
            resume_time = record.get("resume_time")
            if pause_time and resume_time:
                delta = resume_time - pause_time
                total += int(delta.total_seconds() // 60)
        return total

    @property
    def pause_delay_minutes(self) -> int:
        if self.original_scheduled_end and self.scheduled_end:
            delta = self.scheduled_end - self.original_scheduled_end
            return int(delta.total_seconds() // 60)
        return self.total_pause_minutes

    @property
    def is_cross_shift(self) -> bool:
        return bool(self.start_shift and self.end_shift and self.start_shift != self.end_shift)


@dataclass
class DowntimeRecord:
    record_id: str
    machine_id: str
    order_id: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    reason: str
    downtime_type: str

    @property
    def duration_minutes(self) -> int:
        if not self.end_time:
            return 0
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() // 60)

    @property
    def is_resolved(self) -> bool:
        return self.end_time is not None


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
