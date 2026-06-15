from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum


class ShiftType(Enum):
    DAY = "白班"
    NIGHT = "夜班"
    FULL = "全天"


@dataclass
class Shift:
    name: str
    start_time: time
    end_time: time
    shift_type: ShiftType = ShiftType.DAY

    def __init__(self, name: str, start: time, end: time, shift_type: ShiftType = ShiftType.DAY):
        self.name = name
        self.start_time = start
        self.end_time = end
        self.shift_type = shift_type

    def contains(self, t: time) -> bool:
        if self.start_time <= self.end_time:
            return self.start_time <= t <= self.end_time
        else:
            return t >= self.start_time or t <= self.end_time

    def daily_hours(self) -> float:
        if self.start_time <= self.end_time:
            delta = datetime.combine(date.today(), self.end_time) - datetime.combine(date.today(), self.start_time)
        else:
            delta = datetime.combine(date.today() + timedelta(days=1), self.end_time) - datetime.combine(date.today(), self.start_time)
        return delta.total_seconds() / 3600

    def working_periods(self, d: date) -> List[Tuple[datetime, datetime]]:
        periods: List[Tuple[datetime, datetime]] = []
        start_dt = datetime.combine(d, self.start_time)
        if self.start_time <= self.end_time:
            end_dt = datetime.combine(d, self.end_time)
            periods.append((start_dt, end_dt))
        else:
            end_dt = datetime.combine(d + timedelta(days=1), self.end_time)
            periods.append((start_dt, end_dt))
        return periods


@dataclass
class WorkCalendar:
    shifts: List[Shift] = field(default_factory=list)
    holidays: List[date] = field(default_factory=list)
    work_days: set = field(default_factory=lambda: {0, 1, 2, 3, 4, 5, 6})
    work_on_weekend: bool = True

    def __init__(self):
        self.shifts = [
            Shift("白班", time(8, 0), time(20, 0), ShiftType.DAY),
        ]
        self.holidays = []
        self.work_days = {0, 1, 2, 3, 4, 5, 6}
        self.work_on_weekend = True

    def is_work_day(self, d: date) -> bool:
        if d in self.holidays:
            return False
        if d.weekday() in self.work_days:
            return True
        return self.work_on_weekend

    def add_holiday(self, d: date) -> None:
        if d not in self.holidays:
            self.holidays.append(d)
            self.holidays.sort()

    def remove_holiday(self, d: date) -> None:
        if d in self.holidays:
            self.holidays.remove(d)

    def set_shifts(self, shifts: List[Shift]) -> None:
        self.shifts = shifts

    def get_working_periods(self, start_dt: datetime, end_dt: Optional[datetime] = None) -> List[Tuple[datetime, datetime, Shift]]:
        periods: List[Tuple[datetime, datetime, Shift]] = []
        if end_dt is None:
            end_dt = start_dt + timedelta(days=365)
        current = start_dt.date() - timedelta(days=1)
        end_date = end_dt.date() + timedelta(days=1)
        while current <= end_date:
            if self.is_work_day(current):
                for shift in sorted(self.shifts, key=lambda s: s.start_time):
                    for (s, e) in shift.working_periods(current):
                        if e <= start_dt:
                            continue
                        actual_start = max(s, start_dt)
                        actual_end = min(e, end_dt)
                        if actual_start < actual_end:
                            periods.append((actual_start, actual_end, shift))
            current += timedelta(days=1)
        return periods

    def next_working_start(self, from_dt: datetime) -> datetime:
        for (s, e, shift) in self.get_working_periods(from_dt, from_dt + timedelta(days=1)):
            if s <= from_dt <= e:
                return from_dt
            if s >= from_dt:
                return s
        for offset in range(1, 3650):
            check_date = from_dt.date() + timedelta(days=offset)
            if self.is_work_day(check_date):
                for shift in sorted(self.shifts, key=lambda s: s.start_time):
                    shift_start = datetime.combine(check_date, shift.start_time)
                    return shift_start
        return from_dt

    def add_hours(self, start_dt: datetime, hours: float) -> datetime:
        remaining = hours
        current = start_dt
        for (s, e, shift) in self.get_working_periods(current):
            period_hours = (e - s).total_seconds() / 3600
            if remaining <= period_hours:
                return s + timedelta(hours=remaining)
            remaining -= period_hours
            current = e
        return current

    def total_working_hours_between(self, start_dt: datetime, end_dt: datetime) -> float:
        total = 0.0
        for (s, e, _) in self.get_working_periods(start_dt, end_dt):
            total += (min(e, end_dt) - max(s, start_dt)).total_seconds() / 3600
        return total

    def to_dict(self) -> Dict:
        return {
            "shifts": [
                {
                    "name": s.name,
                    "start_time": s.start_time.strftime("%H:%M"),
                    "end_time": s.end_time.strftime("%H:%M"),
                    "shift_type": s.shift_type.value,
                }
                for s in self.shifts
            ],
            "holidays": [d.isoformat() for d in self.holidays],
            "work_days": sorted(list(self.work_days)),
            "work_on_weekend": self.work_on_weekend,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WorkCalendar":
        cal = cls()
        if "shifts" in data:
            cal.shifts = []
            for s in data["shifts"]:
                start = datetime.strptime(s["start_time"], "%H:%M").time()
                end = datetime.strptime(s["end_time"], "%H:%M").time()
                st = ShiftType(s["shift_type"])
                cal.shifts.append(Shift(s["name"], start, end, st))
        if "holidays" in data:
            cal.holidays = [date.fromisoformat(d) for d in data["holidays"]]
        if "work_days" in data:
            cal.work_days = set(data["work_days"])
        if "work_on_weekend" in data:
            cal.work_on_weekend = data["work_on_weekend"]
        return cal
