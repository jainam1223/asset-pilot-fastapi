"""Deterministic demo-data seed script for the ITAM database.

Re-implements the *intent* of `_docs/db_seed.ts` (a TS/Prisma script that
used a seeded PRNG, mulberry32(42)) in async Python/SQLAlchemy, using
`random.Random(42)` for determinism instead. It is NOT a line-by-line
port: counts/shapes/status-coverage match, exact sampled values do not
need to.

Behaviour:
  - Idempotent: truncates every domain table (FK-safe order, via raw
    `TRUNCATE ... RESTART IDENTITY CASCADE` so it also bypasses the
    append-only RULES on `device_log`) before reseeding, so re-running is
    always safe.
  - Deterministic: `random.Random(42)` drives every random choice.
  - Covers every enum value / workflow the M3 spec calls for: 38 users,
    10 item categories, ~72 items, requests spanning all 7 `request_status`
    values, 3 extension requests, ~8 support requests (incl. one
    `auto_closed` with a system actor and one `swapped` resolution with
    matching `swapped_out`/`swapped_in` device_log rows), 6 handover
    requests, and a device_log audit trail with milestone flags mirroring
    `db_seed.ts`'s de facto event -> milestone map.

Usage:
    make seed
    # or directly:
    python -m scripts.seed
"""

import asyncio
import itertools
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.device_log import DeviceLog
from app.models.enums import (
    ActorRole,
    DeviceLogEvent,
    DeviceStatus,
    ExtensionStatus,
    HandoverStatus,
    MgrApprovalStatus,
    OwnerType,
    RejectedByEnum,
    RequestPriority,
    RequestStatus,
    SupportResolution,
    SupportStatus,
    SupportType,
    UserRole,
)
from app.models.extension_request import ExtensionRequest
from app.models.handover_request import HandoverRequest
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.request import Request
from app.models.support_request import SupportRequest
from app.models.user import User

DEV_PASSWORD = "Password123!"

TRUNCATE_SQL = """
    TRUNCATE TABLE
        device_log,
        support_request,
        handover_request,
        extension_request,
        request,
        item,
        item_category,
        "user"
    RESTART IDENTITY CASCADE
"""

# ═══════════════════════════════════════════════════════════════════════════
# Static realistic data pools
# ═══════════════════════════════════════════════════════════════════════════
FIRST_NAMES = [
    "Alice",
    "Bob",
    "Carol",
    "David",
    "Emma",
    "Frank",
    "Grace",
    "Henry",
    "Isabella",
    "Jack",
    "Karen",
    "Leo",
    "Mia",
    "Noah",
    "Olivia",
    "Paul",
    "Quinn",
    "Rachel",
    "Sam",
    "Tina",
    "Uma",
    "Victor",
    "Wendy",
    "Xander",
    "Yasmine",
    "Zach",
    "Amber",
    "Brian",
    "Chloe",
    "Derek",
    "Elena",
    "Felix",
    "Gina",
    "Hank",
    "Iris",
    "James",
    "Kira",
    "Luke",
    "Maya",
    "Nate",
    "Opal",
    "Pete",
    "Rosa",
    "Steve",
    "Tracy",
    "Ursula",
    "Vince",
    "Wanda",
]
LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Wilson",
    "Anderson",
    "Taylor",
    "Thomas",
    "Moore",
    "Martin",
    "Jackson",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Clark",
    "Lewis",
    "Robinson",
    "Walker",
    "Hall",
    "Young",
    "Allen",
    "King",
    "Wright",
    "Scott",
    "Torres",
    "Nguyen",
    "Hill",
    "Flores",
    "Green",
]

LAPTOP_MODELS = [
    'MacBook Pro 14"',
    'MacBook Pro 16"',
    "MacBook Air M2",
    "MacBook Air M3",
    "Dell XPS 13",
    "Dell XPS 15",
    "Dell Latitude 5540",
    "Dell Latitude 7440",
    "HP EliteBook 840",
    "HP EliteBook 860",
    "HP ZBook Studio G10",
    "Lenovo ThinkPad X1 Carbon",
]
PHONE_MODELS = [
    "iPhone 15 Pro",
    "iPhone 15 Pro Max",
    "iPhone 14 Pro",
    "Samsung Galaxy S24 Ultra",
    "Samsung Galaxy S24+",
    "Google Pixel 8 Pro",
    "Google Pixel 8",
    "OnePlus 12",
]
MONITOR_MODELS = [
    'Dell UltraSharp 27" 4K',
    'Dell UltraSharp 32" 4K',
    'LG UltraFine 27"',
    'LG 34" UltraWide',
    'Samsung 32" Curved QHD',
    'BenQ PD2725U 27"',
    "Apple Pro Display XDR",
    "ASUS ProArt PA329CV",
    'ViewSonic VP2768a 27"',
    'AOC Q27P2 27" QHD',
]
KEYBOARD_MODELS = [
    "Apple Magic Keyboard",
    "Logitech MX Keys",
    "Keychron K3 Pro",
    "Keychron Q1 Pro",
    "Das Keyboard 4 Professional",
    "Razer BlackWidow V4",
    "Logitech G915 TKL",
    "Corsair K100 RGB",
]
MOUSE_MODELS = [
    "Apple Magic Mouse",
    "Logitech MX Master 3S",
    "Logitech MX Anywhere 3",
    "Razer DeathAdder V3",
    "Microsoft Arc Mouse",
    "Logitech G Pro X Superlight",
]
HEADSET_MODELS = [
    "Sony WH-1000XM5",
    "Bose QuietComfort 45",
    "Apple AirPods Pro (2nd Gen)",
    "Jabra Evolve2 85",
    "Sennheiser HD 450BT",
    "Poly Voyager Focus 2",
]
CHARGER_MODELS = [
    "Apple 140W USB-C Power Adapter",
    "Apple 67W MagSafe Adapter",
    "Anker 65W GaN Charger",
    "Dell 130W USB-C Slim Power Adapter",
    "Belkin 108W GaN 3-Port Charger",
]
TABLET_MODELS = [
    'iPad Pro 12.9" M2',
    "iPad Air M1",
    "iPad mini 6th Gen",
    "Samsung Galaxy Tab S9 Ultra",
    "Microsoft Surface Pro 9",
]
DOCK_MODELS = [
    "CalDigit TS4 Thunderbolt 4 Dock",
    "Dell Thunderbolt Dock WD22TB4",
    "Anker 13-in-1 USB-C Hub",
    "Belkin Thunderbolt 3 Dock Pro",
]

CLIENT_NAMES = ["Acme Corp", "TechVentures Ltd", "GlobalFinance Inc", "StartupXYZ"]

SUPPORT_DESCRIPTIONS_UPDATE = [
    "macOS needs updating to the latest version",
    "Chrome and Slack are out of date, please update",
    "Security patch required for firmware",
    "Battery calibration update needed",
    "Remote Desktop software needs fresh install",
]
SUPPORT_DESCRIPTIONS_DAMAGE = [
    "Screen cracked after dropping the device",
    "Keyboard keys are sticky and some are not registering",
    "Charging port is loose and device won't charge properly",
    "Fan making loud grinding noise",
    "Trackpad is unresponsive after liquid spill",
    "Hinge is broken on laptop lid",
]
SUPPORT_DESCRIPTIONS_LOST = [
    "Device left in taxi after client meeting — cannot locate",
    "Stolen from desk in shared office space",
    "Left at airport, reported missing to lost property",
    "Cannot locate device after office relocation",
]

REQUEST_NOTES: list[str | None] = [
    "Need for upcoming client presentation",
    "Replacement for my device which is in repair",
    "Required for remote work setup",
    "New hire onboarding — day one start",
    "Short-term project requirement ends next quarter",
    "Travelling for 3 weeks, need portable option",
    "Current device is too slow for development work",
    "Designer needs better display for creative work",
    None,
    None,
    None,
]

HANDOVER_NOTES: list[str | None] = [
    "Borrowing for afternoon presentation",
    "Mine is with IT for repair",
    "Need to demo to client in meeting room",
    "Quick loan while mine is being charged",
    None,
]

REJECT_REASONS = [
    "Device not available for requested period",
    "Business justification insufficient",
    "Employee already has active assignment in this category",
    "Request period conflicts with planned maintenance",
    "Priority level does not meet threshold for this device type",
]

CATEGORY_DEFS: list[tuple[str, str, bool, bool]] = [
    ("Laptop", "Portable computers for daily work", True, True),
    ("Mobile Phone", "Company smartphones for employees", True, True),
    ("Monitor", "External display monitors", False, True),
    ("Keyboard", "Mechanical and membrane keyboards", False, True),
    ("Mouse", "Wireless and wired mice", False, True),
    ("Headset", "Noise-cancelling headsets and earphones", False, True),
    ("Charger", "Power adapters and charging cables", False, True),
    ("Tablet", "Tablets for presentations and fieldwork", True, True),
    ("Dock", "Docking stations and USB-C hubs", False, True),
    ("Legacy", "Retired category for old device types", False, False),
]


# ═══════════════════════════════════════════════════════════════════════════
# Small deterministic helpers
# ═══════════════════════════════════════════════════════════════════════════
def now() -> datetime:
    return datetime.now(UTC)


def past(days: int = 0, hours: float = 0) -> datetime:
    return now() - timedelta(days=days, hours=hours)


def future(days: int = 0, hours: float = 0) -> datetime:
    return now() + timedelta(days=days, hours=hours)


def add_days(dt: datetime, n: int) -> datetime:
    return dt + timedelta(days=n)


def add_hours(dt: datetime, n: float) -> datetime:
    return dt + timedelta(hours=n)


def sample_list[T](rng: random.Random, seq: list[T], n: int) -> list[T]:
    return rng.sample(seq, min(n, len(seq)))


def make_name(rng: random.Random, used: set[str]) -> str:
    for _ in range(500):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if name not in used:
            used.add(name)
            return name
    fallback = f"User {uuid.uuid4().hex[:8]}"
    used.add(fallback)
    return fallback


def make_email(name: str) -> str:
    first, last = name.lower().split(" ", 1)
    return f"{first}.{last.replace(' ', '')}@techcorp.internal"


def make_serial(rng: random.Random) -> str:
    return f"SN-{rng.randint(100000, 999999)}"


# ═══════════════════════════════════════════════════════════════════════════
# Seed routine
# ═══════════════════════════════════════════════════════════════════════════
async def seed(session: AsyncSession) -> tuple[dict[str, int], str]:
    rng = random.Random(42)
    used_names: set[str] = set()
    password_hash = hash_password(DEV_PASSWORD)

    users: list[User] = []
    categories: dict[str, ItemCategory] = {}
    items: list[Item] = []
    item_created_at: dict[uuid.UUID, datetime] = {}
    requests: list[Request] = []
    extensions: list[ExtensionRequest] = []
    support_requests: list[SupportRequest] = []
    handovers: list[HandoverRequest] = []
    device_logs: list[DeviceLog] = []

    # ── 1. USERS ────────────────────────────────────────────────────────
    managers: list[User] = []
    it_admins: list[User] = []
    employees: list[User] = []

    for _ in range(5):
        name = make_name(rng, used_names)
        u = User(
            id=uuid.uuid4(),
            name=name,
            email=make_email(name),
            password_hash=password_hash,
            role=UserRole.MANAGER,
            manager_id=None,
            is_active=True,
        )
        session.add(u)
        managers.append(u)
        users.append(u)

    for _ in range(3):
        name = make_name(rng, used_names)
        u = User(
            id=uuid.uuid4(),
            name=name,
            email=make_email(name),
            password_hash=password_hash,
            role=UserRole.IT_ADMIN,
            manager_id=None,
            is_active=True,
        )
        session.add(u)
        it_admins.append(u)
        users.append(u)

    for i in range(30):
        name = make_name(rng, used_names)
        mgr = rng.choice(managers)
        u = User(
            id=uuid.uuid4(),
            name=name,
            email=make_email(name),
            password_hash=password_hash,
            role=UserRole.EMPLOYEE,
            manager_id=mgr.id,
            is_active=i < 28,
        )
        session.add(u)
        employees.append(u)
        users.append(u)

    it_admin = it_admins[0]
    active_employees = [e for e in employees if e.is_active]
    emp_cycle = itertools.cycle(active_employees)

    def next_active_employee() -> User:
        return next(emp_cycle)

    # SQLAlchemy has no ORM `relationship()`s wired between these models
    # (only raw FK columns), so the unit-of-work flush process does not
    # automatically topologically sort INSERTs across tables. Flushing at
    # each dependency boundary (below) guarantees parent rows exist in
    # Postgres before dependent rows are inserted.
    await session.flush()

    # ── 2. ITEM CATEGORIES ──────────────────────────────────────────────
    for cat_name, desc, req_mgr, is_active in CATEGORY_DEFS:
        c = ItemCategory(
            id=uuid.uuid4(),
            name=cat_name,
            description=desc,
            requires_mgr_approval=req_mgr,
            is_active=is_active,
        )
        session.add(c)
        categories[cat_name] = c

    await session.flush()

    # ── 3. ITEMS ────────────────────────────────────────────────────────
    def make_item(
        name: str,
        category_name: str,
        *,
        status: DeviceStatus = DeviceStatus.AVAILABLE,
        owner_type: OwnerType = OwnerType.COMPANY,
        client_name: str | None = None,
        current_owner_id: uuid.UUID | None = None,
        purchase_days_ago: int | None = None,
    ) -> Item:
        days_ago = purchase_days_ago if purchase_days_ago is not None else rng.randint(30, 730)
        created_dt = past(days_ago)
        item = Item(
            id=uuid.uuid4(),
            name=name,
            serial_no=make_serial(rng),
            category_id=categories[category_name].id,
            owner_type=owner_type,
            client_name=client_name,
            status=status,
            current_owner_id=current_owner_id,
            purchase_date=created_dt.date(),
            qr_code_token=uuid.uuid4(),
        )
        session.add(item)
        items.append(item)
        item_created_at[item.id] = created_dt
        return item

    laptops = [make_item(m, "Laptop") for m in sample_list(rng, LAPTOP_MODELS, 12)]
    phones = [make_item(m, "Mobile Phone") for m in sample_list(rng, PHONE_MODELS, 8)]
    monitors = [make_item(m, "Monitor") for m in sample_list(rng, MONITOR_MODELS, 10)]
    for m in sample_list(rng, KEYBOARD_MODELS, 8):
        make_item(m, "Keyboard")
    for m in sample_list(rng, MOUSE_MODELS, 6):
        make_item(m, "Mouse")
    for m in sample_list(rng, HEADSET_MODELS, 6):
        make_item(m, "Headset")
    for m in sample_list(rng, CHARGER_MODELS, 5):
        make_item(m, "Charger")
    for m in sample_list(rng, TABLET_MODELS, 5):
        make_item(m, "Tablet")
    for m in sample_list(rng, DOCK_MODELS, 4):
        make_item(m, "Dock")

    client_devices: list[Item] = []
    for i, cn in enumerate(CLIENT_NAMES):
        model = rng.choice(LAPTOP_MODELS)
        owner = active_employees[i]
        cd = make_item(
            f"{cn} — {model}",
            "Laptop",
            owner_type=OwnerType.CLIENT,
            client_name=cn,
            status=DeviceStatus.ASSIGNED,
            current_owner_id=owner.id,
        )
        client_devices.append(cd)

    under_repair_item = make_item(rng.choice(LAPTOP_MODELS), "Laptop", status=DeviceStatus.UNDER_REPAIR)
    maintenance_item = make_item(rng.choice(MONITOR_MODELS), "Monitor", status=DeviceStatus.MAINTENANCE)
    lost_item = make_item(rng.choice(PHONE_MODELS), "Mobile Phone", status=DeviceStatus.LOST)
    retired_item = make_item(
        rng.choice(LAPTOP_MODELS), "Laptop", status=DeviceStatus.RETIRED, purchase_days_ago=1460
    )

    await session.flush()

    # ── device_log helper ───────────────────────────────────────────────
    def log_event(
        *,
        item_id: uuid.UUID,
        event_type: DeviceLogEvent,
        actor_role: ActorRole,
        actor_id: uuid.UUID | None = None,
        request_id: uuid.UUID | None = None,
        support_request_id: uuid.UUID | None = None,
        extension_request_id: uuid.UUID | None = None,
        handover_request_id: uuid.UUID | None = None,
        from_value: str | None = None,
        to_value: str | None = None,
        note: str | None = None,
        metadata: dict[str, object] | None = None,
        is_milestone: bool = False,
        occurred_at: datetime | None = None,
    ) -> DeviceLog:
        occ = occurred_at if occurred_at is not None else now()
        dl = DeviceLog(
            id=uuid.uuid4(),
            item_id=item_id,
            event_type=event_type,
            actor_id=actor_id,
            actor_role=actor_role,
            request_id=request_id,
            support_request_id=support_request_id,
            extension_request_id=extension_request_id,
            handover_request_id=handover_request_id,
            from_value=from_value,
            to_value=to_value,
            note=note,
            log_metadata=metadata or {},
            is_milestone=is_milestone,
            occurred_at=occ,
        )
        session.add(dl)
        device_logs.append(dl)
        return dl

    # ── 4. device_created for every item ────────────────────────────────
    for item in items:
        log_event(
            item_id=item.id,
            event_type=DeviceLogEvent.DEVICE_CREATED,
            actor_id=it_admin.id,
            actor_role=ActorRole.IT_ADMIN,
            to_value="available",
            note=f"Device added to inventory: {item.name}",
            is_milestone=False,
            occurred_at=item_created_at[item.id],
        )

    # ── 5. REQUESTS ─────────────────────────────────────────────────────
    def make_request(
        requester: User,
        category_name: str,
        *,
        status: RequestStatus,
        requested_from: datetime,
        requested_to: datetime,
        priority: RequestPriority = RequestPriority.MEDIUM,
        note: str | None = None,
        assigned_item: Item | None = None,
        assigned_from: datetime | None = None,
        assigned_to: datetime | None = None,
        requires_mgr_approval: bool | None = None,
        mgr_approval_status: MgrApprovalStatus = MgrApprovalStatus.NOT_REQUIRED,
        manager_id: uuid.UUID | None = None,
        manager_decision_note: str | None = None,
        manager_decided_at: datetime | None = None,
        it_decided_by: uuid.UUID | None = None,
        it_decision_note: str | None = None,
        it_decided_at: datetime | None = None,
        rejected_by: RejectedByEnum | None = None,
        rejected_reason: str | None = None,
        cancelled_by: uuid.UUID | None = None,
        cancelled_at: datetime | None = None,
        is_wfh: bool = False,
        ship_tracking_url: str | None = None,
        ship_initiated_at: datetime | None = None,
        ship_completed_at: datetime | None = None,
        return_tracking_url: str | None = None,
        return_initiated_at: datetime | None = None,
        completed_at: datetime | None = None,
        completed_by: uuid.UUID | None = None,
        completed_next_status: DeviceStatus | None = None,
        is_client_direct: bool = False,
    ) -> Request:
        cat = categories[category_name]
        requires_mgr = (
            requires_mgr_approval if requires_mgr_approval is not None else cat.requires_mgr_approval
        )
        r = Request(
            id=uuid.uuid4(),
            requester_id=requester.id,
            category_id=cat.id,
            assigned_item_id=assigned_item.id if assigned_item else None,
            requested_from=requested_from,
            requested_to=requested_to,
            assigned_from=assigned_from,
            assigned_to=assigned_to,
            status=status,
            priority=priority,
            note=note if note is not None else rng.choice(REQUEST_NOTES),
            requires_mgr_approval=requires_mgr,
            mgr_approval_status=mgr_approval_status,
            manager_id=manager_id if manager_id is not None else requester.manager_id,
            manager_decision_note=manager_decision_note,
            manager_decided_at=manager_decided_at,
            it_decided_by=it_decided_by,
            it_decision_note=it_decision_note,
            it_decided_at=it_decided_at,
            rejected_by=rejected_by,
            rejected_reason=rejected_reason,
            cancelled_by=cancelled_by,
            cancelled_at=cancelled_at,
            is_wfh=is_wfh,
            ship_tracking_url=ship_tracking_url,
            ship_initiated_at=ship_initiated_at,
            ship_completed_at=ship_completed_at,
            return_tracking_url=return_tracking_url,
            return_initiated_at=return_initiated_at,
            completed_at=completed_at,
            completed_by=completed_by,
            completed_next_status=completed_next_status,
            is_client_direct=is_client_direct,
        )
        session.add(r)
        requests.append(r)
        return r

    completed_pairs: list[tuple[Request, Item]] = []
    assigned_pairs: list[tuple[Request, Item, User]] = []

    # 5a. Completed requests
    for item in laptops[:5]:
        emp = next_active_employee()
        start = past(rng.randint(60, 120))
        end = past(rng.randint(10, 55))
        r = make_request(
            emp,
            "Laptop",
            status=RequestStatus.COMPLETED,
            priority=rng.choice([RequestPriority.LOW, RequestPriority.MEDIUM, RequestPriority.HIGH]),
            requested_from=start,
            requested_to=add_days(end, 5),
            assigned_item=item,
            assigned_from=start,
            assigned_to=end,
            requires_mgr_approval=True,
            mgr_approval_status=MgrApprovalStatus.APPROVED,
            manager_id=emp.manager_id,
            manager_decided_at=add_hours(start, 4),
            it_decided_by=it_admin.id,
            it_decided_at=add_hours(start, 8),
            completed_at=end,
            completed_by=it_admin.id,
            completed_next_status=DeviceStatus.AVAILABLE,
        )
        completed_pairs.append((r, item))
        item.status = DeviceStatus.AVAILABLE
        item.current_owner_id = None

    for item in phones[:3]:
        emp = next_active_employee()
        start = past(rng.randint(40, 90))
        end = past(rng.randint(5, 35))
        r = make_request(
            emp,
            "Mobile Phone",
            status=RequestStatus.COMPLETED,
            requested_from=start,
            requested_to=add_days(end, 3),
            assigned_item=item,
            assigned_from=start,
            assigned_to=end,
            requires_mgr_approval=True,
            mgr_approval_status=MgrApprovalStatus.APPROVED,
            manager_id=emp.manager_id,
            manager_decided_at=add_hours(start, 6),
            it_decided_by=it_admin.id,
            it_decided_at=add_hours(start, 10),
            completed_at=end,
            completed_by=it_admin.id,
            completed_next_status=DeviceStatus.AVAILABLE,
        )
        completed_pairs.append((r, item))
        item.status = DeviceStatus.AVAILABLE
        item.current_owner_id = None

    # Completed WFH request (full ship + return cycle)
    wfh_item = laptops[5]
    emp_wfh_done = next_active_employee()
    wfh_start = past(50)
    wfh_end = past(5)
    r_wfh_done = make_request(
        emp_wfh_done,
        "Laptop",
        status=RequestStatus.COMPLETED,
        priority=RequestPriority.HIGH,
        requested_from=wfh_start,
        requested_to=add_days(wfh_end, 2),
        assigned_item=wfh_item,
        assigned_from=add_days(wfh_start, 2),
        assigned_to=wfh_end,
        requires_mgr_approval=True,
        mgr_approval_status=MgrApprovalStatus.APPROVED,
        manager_id=emp_wfh_done.manager_id,
        manager_decided_at=add_hours(wfh_start, 3),
        it_decided_by=it_admin.id,
        it_decided_at=add_hours(wfh_start, 6),
        is_wfh=True,
        ship_tracking_url="https://tracking.dhl.com/ABC123456",
        ship_initiated_at=add_hours(wfh_start, 8),
        ship_completed_at=add_days(wfh_start, 2),
        return_tracking_url="https://tracking.ups.com/XYZ789012",
        return_initiated_at=add_days(wfh_end, -2),
        completed_at=wfh_end,
        completed_by=it_admin.id,
        completed_next_status=DeviceStatus.AVAILABLE,
    )
    completed_pairs.append((r_wfh_done, wfh_item))
    wfh_item.status = DeviceStatus.AVAILABLE
    wfh_item.current_owner_id = None

    # 5b. Active assigned requests
    for item in laptops[:6]:
        emp = next_active_employee()
        start = past(rng.randint(5, 30))
        end = future(rng.randint(10, 60))
        r = make_request(
            emp,
            "Laptop",
            status=RequestStatus.ASSIGNED,
            priority=rng.choice([RequestPriority.MEDIUM, RequestPriority.HIGH]),
            requested_from=start,
            requested_to=end,
            assigned_item=item,
            assigned_from=start,
            assigned_to=end,
            requires_mgr_approval=True,
            mgr_approval_status=MgrApprovalStatus.APPROVED,
            manager_id=emp.manager_id,
            manager_decided_at=add_hours(add_days(start, -2), 4),
            it_decided_by=it_admin.id,
            it_decided_at=add_days(start, -1),
        )
        item.status = DeviceStatus.ASSIGNED
        item.current_owner_id = emp.id
        assigned_pairs.append((r, item, emp))

    for item in phones[:3]:
        emp = next_active_employee()
        start = past(rng.randint(3, 20))
        end = future(rng.randint(10, 45))
        r = make_request(
            emp,
            "Mobile Phone",
            status=RequestStatus.ASSIGNED,
            requested_from=start,
            requested_to=end,
            assigned_item=item,
            assigned_from=start,
            assigned_to=end,
            requires_mgr_approval=True,
            mgr_approval_status=MgrApprovalStatus.APPROVED,
            manager_id=emp.manager_id,
            manager_decided_at=add_hours(add_days(start, -1), 3),
            it_decided_by=it_admin.id,
            it_decided_at=start,
        )
        item.status = DeviceStatus.ASSIGNED
        item.current_owner_id = emp.id
        assigned_pairs.append((r, item, emp))

    for item in monitors[:3]:
        emp = next_active_employee()
        start = past(rng.randint(2, 15))
        end = future(rng.randint(20, 90))
        r = make_request(
            emp,
            "Monitor",
            status=RequestStatus.ASSIGNED,
            priority=RequestPriority.LOW,
            requested_from=start,
            requested_to=end,
            assigned_item=item,
            assigned_from=start,
            assigned_to=end,
            requires_mgr_approval=False,
            mgr_approval_status=MgrApprovalStatus.NOT_REQUIRED,
            it_decided_by=it_admin.id,
            it_decided_at=start,
        )
        item.status = DeviceStatus.ASSIGNED
        item.current_owner_id = emp.id
        assigned_pairs.append((r, item, emp))

    # WFH — outbound shipping in progress
    wfh_ship_item = laptops[6]
    emp_wfh_ship = next_active_employee()
    wfh_ship_start = past(1)
    wfh_ship_end = future(30)
    r_wfh_ship = make_request(
        emp_wfh_ship,
        "Laptop",
        status=RequestStatus.ASSIGNED,
        priority=RequestPriority.HIGH,
        requested_from=wfh_ship_start,
        requested_to=wfh_ship_end,
        assigned_item=wfh_ship_item,
        assigned_from=add_days(wfh_ship_start, 3),
        assigned_to=wfh_ship_end,
        requires_mgr_approval=True,
        mgr_approval_status=MgrApprovalStatus.APPROVED,
        manager_id=emp_wfh_ship.manager_id,
        manager_decided_at=add_hours(past(3), 4),
        it_decided_by=it_admin.id,
        it_decided_at=past(2),
        is_wfh=True,
        ship_tracking_url="https://tracking.fedex.com/DEF456789",
        ship_initiated_at=past(1),
    )
    wfh_ship_item.status = DeviceStatus.SHIPPING_PENDING
    wfh_ship_item.current_owner_id = emp_wfh_ship.id
    assigned_pairs.append((r_wfh_ship, wfh_ship_item, emp_wfh_ship))

    # WFH — return shipping in progress
    wfh_ret_item = laptops[7]
    emp_wfh_ret = next_active_employee()
    wfh_ret_start = past(25)
    wfh_ret_end = future(2)
    r_wfh_ret = make_request(
        emp_wfh_ret,
        "Laptop",
        status=RequestStatus.ASSIGNED,
        requested_from=wfh_ret_start,
        requested_to=wfh_ret_end,
        assigned_item=wfh_ret_item,
        assigned_from=add_days(wfh_ret_start, 2),
        assigned_to=wfh_ret_end,
        requires_mgr_approval=True,
        mgr_approval_status=MgrApprovalStatus.APPROVED,
        manager_id=emp_wfh_ret.manager_id,
        manager_decided_at=add_days(wfh_ret_start, -1),
        it_decided_by=it_admin.id,
        it_decided_at=wfh_ret_start,
        is_wfh=True,
        ship_tracking_url="https://tracking.dhl.com/GHI012345",
        ship_initiated_at=add_hours(wfh_ret_start, 6),
        ship_completed_at=add_days(wfh_ret_start, 2),
        return_tracking_url="https://tracking.ups.com/JKL678901",
        return_initiated_at=past(2),
    )
    wfh_ret_item.status = DeviceStatus.RETURN_SHIPPING_PENDING
    wfh_ret_item.current_owner_id = emp_wfh_ret.id
    assigned_pairs.append((r_wfh_ret, wfh_ret_item, emp_wfh_ret))

    # 5c. Pending IT approval (6)
    for _ in range(6):
        emp = next_active_employee()
        cat_name = rng.choice(["Laptop", "Monitor", "Keyboard", "Headset"])
        needs_mgr = categories[cat_name].requires_mgr_approval
        start = future(rng.randint(1, 14))
        end = future(rng.randint(20, 60))
        make_request(
            emp,
            cat_name,
            status=RequestStatus.PENDING_IT_APPROVAL,
            priority=rng.choice([RequestPriority.LOW, RequestPriority.MEDIUM, RequestPriority.HIGH]),
            requested_from=start,
            requested_to=end,
            requires_mgr_approval=needs_mgr,
            mgr_approval_status=MgrApprovalStatus.APPROVED if needs_mgr else MgrApprovalStatus.NOT_REQUIRED,
            manager_id=emp.manager_id if needs_mgr else None,
            manager_decided_at=past(hours=rng.randint(1, 48)) if needs_mgr else None,
        )

    # One extra "waitlisted" pending_it_approval request, for realism
    emp_wait = next_active_employee()
    make_request(
        emp_wait,
        "Laptop",
        status=RequestStatus.PENDING_IT_APPROVAL,
        priority=RequestPriority.HIGH,
        requested_from=future(15),
        requested_to=future(45),
        requires_mgr_approval=True,
        mgr_approval_status=MgrApprovalStatus.APPROVED,
        manager_id=emp_wait.manager_id,
        manager_decided_at=past(1),
        note="Urgent: needed for project kick-off in 2 weeks",
    )

    # 5d. Pending manager approval (4)
    for _ in range(4):
        emp = next_active_employee()
        cat_name = rng.choice(["Laptop", "Mobile Phone", "Tablet"])
        start = future(rng.randint(5, 20))
        end = future(rng.randint(25, 70))
        make_request(
            emp,
            cat_name,
            status=RequestStatus.PENDING_MGR_APPROVAL,
            priority=rng.choice([RequestPriority.MEDIUM, RequestPriority.HIGH]),
            requested_from=start,
            requested_to=end,
            requires_mgr_approval=True,
            mgr_approval_status=MgrApprovalStatus.PENDING,
            manager_id=emp.manager_id,
        )

    # 5e. Just submitted / requested (3)
    for _ in range(3):
        emp = next_active_employee()
        cat_name = rng.choice(["Mouse", "Charger", "Keyboard", "Monitor"])
        start = future(rng.randint(1, 10))
        end = future(rng.randint(15, 45))
        make_request(
            emp,
            cat_name,
            status=RequestStatus.REQUESTED,
            priority=rng.choice([RequestPriority.LOW, RequestPriority.MEDIUM]),
            requested_from=start,
            requested_to=end,
            requires_mgr_approval=categories[cat_name].requires_mgr_approval,
            mgr_approval_status=MgrApprovalStatus.NOT_REQUIRED,
        )

    # 5f. Rejected (4)
    for _ in range(4):
        emp = next_active_employee()
        cat_name = rng.choice(["Laptop", "Mobile Phone", "Tablet"])
        start = past(rng.randint(20, 60))
        end = past(rng.randint(5, 18))
        by_mgr = rng.random() < 0.5
        make_request(
            emp,
            cat_name,
            status=RequestStatus.REJECTED,
            priority=rng.choice([RequestPriority.LOW, RequestPriority.MEDIUM, RequestPriority.HIGH]),
            requested_from=start,
            requested_to=end,
            requires_mgr_approval=True,
            mgr_approval_status=MgrApprovalStatus.REJECTED if by_mgr else MgrApprovalStatus.APPROVED,
            manager_id=emp.manager_id,
            manager_decided_at=add_hours(start, 8) if by_mgr else add_hours(start, 4),
            it_decided_by=None if by_mgr else it_admin.id,
            it_decided_at=None if by_mgr else add_hours(start, 12),
            rejected_by=RejectedByEnum.MANAGER if by_mgr else RejectedByEnum.IT_ADMIN,
            rejected_reason=rng.choice(REJECT_REASONS),
        )

    # 5g. Cancelled (3)
    for _ in range(3):
        emp = next_active_employee()
        cat_name = rng.choice(["Monitor", "Keyboard", "Dock"])
        start = past(rng.randint(15, 45))
        cancel_at = add_hours(start, rng.randint(2, 24))
        make_request(
            emp,
            cat_name,
            status=RequestStatus.CANCELLED,
            priority=RequestPriority.LOW,
            requested_from=add_days(start, 5),
            requested_to=add_days(start, 25),
            requires_mgr_approval=False,
            mgr_approval_status=MgrApprovalStatus.NOT_REQUIRED,
            cancelled_by=emp.id,
            cancelled_at=cancel_at,
        )

    # 5h. Client direct-assign requests (audit symmetry)
    for i, cd in enumerate(client_devices[: min(len(client_devices), len(active_employees), 4)]):
        emp_i = active_employees[i]
        start = past(rng.randint(10, 60))
        r = make_request(
            emp_i,
            "Laptop",
            status=RequestStatus.ASSIGNED,
            priority=RequestPriority.HIGH,
            requested_from=start,
            requested_to=future(60),
            assigned_item=cd,
            assigned_from=start,
            assigned_to=future(60),
            requires_mgr_approval=False,
            mgr_approval_status=MgrApprovalStatus.NOT_REQUIRED,
            it_decided_by=it_admin.id,
            it_decided_at=start,
            is_client_direct=True,
            note="Client-provided device — direct assign",
        )
        assigned_pairs.append((r, cd, emp_i))

    # 5i. Under-repair request (device already under repair)
    emp_repair = next_active_employee()
    repair_start = past(20)
    r_repair = make_request(
        emp_repair,
        "Laptop",
        status=RequestStatus.ASSIGNED,
        priority=RequestPriority.HIGH,
        requested_from=repair_start,
        requested_to=future(30),
        assigned_item=under_repair_item,
        assigned_from=repair_start,
        assigned_to=future(30),
        requires_mgr_approval=True,
        mgr_approval_status=MgrApprovalStatus.APPROVED,
        manager_id=emp_repair.manager_id,
        manager_decided_at=add_days(repair_start, -1),
        it_decided_by=it_admin.id,
        it_decided_at=repair_start,
    )
    under_repair_item.current_owner_id = emp_repair.id
    assigned_pairs.append((r_repair, under_repair_item, emp_repair))

    await session.flush()

    # ── 6. device_log — assigned / completed / shipping events ─────────
    for r, item in completed_pairs:
        log_event(
            item_id=item.id,
            event_type=DeviceLogEvent.ASSIGNED,
            actor_id=it_admin.id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=r.id,
            from_value="available",
            to_value="assigned",
            note="Assigned to employee",
            is_milestone=True,
            occurred_at=r.assigned_from or r.requested_from,
        )
        if r.is_wfh and r.ship_initiated_at:
            log_event(
                item_id=item.id,
                event_type=DeviceLogEvent.SHIP_OUTBOUND_INITIATED,
                actor_id=it_admin.id,
                actor_role=ActorRole.IT_ADMIN,
                request_id=r.id,
                note="Outbound shipping initiated",
                metadata={"tracking_url": r.ship_tracking_url},
                is_milestone=False,
                occurred_at=r.ship_initiated_at,
            )
        if r.is_wfh and r.ship_completed_at:
            log_event(
                item_id=item.id,
                event_type=DeviceLogEvent.SHIP_OUTBOUND_COMPLETED,
                actor_id=it_admin.id,
                actor_role=ActorRole.IT_ADMIN,
                request_id=r.id,
                note="Outbound delivery confirmed",
                is_milestone=True,
                occurred_at=r.ship_completed_at,
            )
        if r.is_wfh and r.return_initiated_at:
            log_event(
                item_id=item.id,
                event_type=DeviceLogEvent.RETURN_SHIP_INITIATED,
                actor_id=it_admin.id,
                actor_role=ActorRole.IT_ADMIN,
                request_id=r.id,
                note="Return shipping initiated",
                metadata={"tracking_url": r.return_tracking_url},
                is_milestone=False,
                occurred_at=r.return_initiated_at,
            )
            log_event(
                item_id=item.id,
                event_type=DeviceLogEvent.RETURN_RECEIVED,
                actor_id=it_admin.id,
                actor_role=ActorRole.IT_ADMIN,
                request_id=r.id,
                note="Returned device received at IT desk",
                is_milestone=True,
                occurred_at=r.completed_at or now(),
            )
        log_event(
            item_id=item.id,
            event_type=DeviceLogEvent.ASSIGNMENT_COMPLETED,
            actor_id=it_admin.id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=r.id,
            from_value="assigned",
            to_value=r.completed_next_status.value if r.completed_next_status else None,
            note="Return processed, device status updated",
            is_milestone=True,
            occurred_at=r.completed_at or now(),
        )

    for r, item, emp in assigned_pairs:
        event = DeviceLogEvent.CLIENT_ASSIGNED if r.is_client_direct else DeviceLogEvent.ASSIGNED
        log_event(
            item_id=item.id,
            event_type=event,
            actor_id=it_admin.id,
            actor_role=ActorRole.IT_ADMIN,
            request_id=r.id,
            from_value="available",
            to_value="assigned",
            note=f"Assigned to {emp.name}",
            is_milestone=True,
            occurred_at=r.assigned_from or r.requested_from,
        )
        if r.is_wfh and r.ship_initiated_at:
            log_event(
                item_id=item.id,
                event_type=DeviceLogEvent.SHIP_OUTBOUND_INITIATED,
                actor_id=it_admin.id,
                actor_role=ActorRole.IT_ADMIN,
                request_id=r.id,
                note="Outbound shipping initiated",
                metadata={"tracking_url": r.ship_tracking_url},
                is_milestone=False,
                occurred_at=r.ship_initiated_at,
            )
        if r.is_wfh and r.ship_completed_at:
            log_event(
                item_id=item.id,
                event_type=DeviceLogEvent.SHIP_OUTBOUND_COMPLETED,
                actor_id=it_admin.id,
                actor_role=ActorRole.IT_ADMIN,
                request_id=r.id,
                note="Outbound delivery confirmed",
                is_milestone=True,
                occurred_at=r.ship_completed_at,
            )
        if r.is_wfh and r.return_initiated_at and item.status == DeviceStatus.RETURN_SHIPPING_PENDING:
            log_event(
                item_id=item.id,
                event_type=DeviceLogEvent.RETURN_SHIP_INITIATED,
                actor_id=it_admin.id,
                actor_role=ActorRole.IT_ADMIN,
                request_id=r.id,
                note="Return shipping initiated",
                metadata={"tracking_url": r.return_tracking_url},
                is_milestone=False,
                occurred_at=r.return_initiated_at,
            )

    # Special single-item logs
    log_event(
        item_id=under_repair_item.id,
        event_type=DeviceLogEvent.STATUS_CHANGED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r_repair.id,
        from_value="assigned",
        to_value="under_repair",
        note="Device sent to repair centre — keyboard failure",
        is_milestone=True,
        occurred_at=past(5),
    )
    log_event(
        item_id=lost_item.id,
        event_type=DeviceLogEvent.MARKED_LOST,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        from_value="assigned",
        to_value="lost",
        note="Employee confirmed device cannot be located after office move",
        is_milestone=True,
        occurred_at=past(12),
    )
    log_event(
        item_id=retired_item.id,
        event_type=DeviceLogEvent.RETIRED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        from_value="available",
        to_value="retired",
        note="Device exceeded 4-year lifecycle policy — retired from inventory",
        is_milestone=True,
        occurred_at=past(30),
    )

    # ── 7. EXTENSION REQUESTS (3) ────────────────────────────────────────
    r_ext1, item_ext1, emp_ext1 = assigned_pairs[0]
    ext_old_to = r_ext1.assigned_to or future(20)
    ext_new_to = add_days(ext_old_to, 14)
    ext_decided = past(3)
    ext1 = ExtensionRequest(
        id=uuid.uuid4(),
        original_request_id=r_ext1.id,
        requester_id=emp_ext1.id,
        current_assigned_to=ext_old_to,
        extended_to=ext_new_to,
        status=ExtensionStatus.APPROVED,
        requires_mgr_approval=True,
        manager_id=emp_ext1.manager_id,
        mgr_approval_status=MgrApprovalStatus.APPROVED,
        manager_note="Approved — project extended",
        manager_decided_at=add_hours(ext_decided, -6),
        it_decided_by=it_admin.id,
        it_note="No conflicts found for extended range",
        it_decided_at=ext_decided,
    )
    session.add(ext1)
    await session.flush()
    extensions.append(ext1)
    r_ext1.assigned_to = ext_new_to
    log_event(
        item_id=item_ext1.id,
        event_type=DeviceLogEvent.EXTENSION_REQUESTED,
        actor_id=emp_ext1.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r_ext1.id,
        extension_request_id=ext1.id,
        note=f"Extension requested to {ext_new_to.date().isoformat()}",
        is_milestone=False,
        occurred_at=add_days(ext_decided, -2),
    )
    log_event(
        item_id=item_ext1.id,
        event_type=DeviceLogEvent.EXTENSION_APPROVED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r_ext1.id,
        extension_request_id=ext1.id,
        from_value=ext_old_to.date().isoformat(),
        to_value=ext_new_to.date().isoformat(),
        note="Extension approved — assigned_to updated",
        metadata={"extended_by_days": 14},
        is_milestone=True,
        occurred_at=ext_decided,
    )

    r_ext2, item_ext2, emp_ext2 = assigned_pairs[1]
    ext2_current_to = r_ext2.assigned_to or future(25)
    ext2 = ExtensionRequest(
        id=uuid.uuid4(),
        original_request_id=r_ext2.id,
        requester_id=emp_ext2.id,
        current_assigned_to=ext2_current_to,
        extended_to=add_days(ext2_current_to, 21),
        status=ExtensionStatus.PENDING,
        requires_mgr_approval=False,
        manager_id=None,
        mgr_approval_status=MgrApprovalStatus.NOT_REQUIRED,
    )
    session.add(ext2)
    await session.flush()
    extensions.append(ext2)
    log_event(
        item_id=item_ext2.id,
        event_type=DeviceLogEvent.EXTENSION_REQUESTED,
        actor_id=emp_ext2.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r_ext2.id,
        extension_request_id=ext2.id,
        note="Extension requested — awaiting IT review",
        is_milestone=False,
        occurred_at=past(1),
    )

    r_ext3, item_ext3, emp_ext3 = assigned_pairs[2]
    ext3_decided = past(5)
    ext3_current_to = r_ext3.assigned_to or future(15)
    ext3 = ExtensionRequest(
        id=uuid.uuid4(),
        original_request_id=r_ext3.id,
        requester_id=emp_ext3.id,
        current_assigned_to=ext3_current_to,
        extended_to=add_days(ext3_current_to, 30),
        status=ExtensionStatus.REJECTED,
        requires_mgr_approval=True,
        manager_id=emp_ext3.manager_id,
        mgr_approval_status=MgrApprovalStatus.APPROVED,
        manager_note="Approved by manager",
        manager_decided_at=add_hours(ext3_decided, -10),
        it_decided_by=it_admin.id,
        it_note="Conflict detected: another request scheduled for this device",
        it_decided_at=ext3_decided,
    )
    session.add(ext3)
    await session.flush()
    extensions.append(ext3)
    log_event(
        item_id=item_ext3.id,
        event_type=DeviceLogEvent.EXTENSION_REJECTED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r_ext3.id,
        extension_request_id=ext3.id,
        note="Extension rejected — date conflict with another booking",
        is_milestone=False,
        occurred_at=ext3_decided,
    )

    # ── 8. SUPPORT REQUESTS (~8) ────────────────────────────────────────
    async def make_support(
        item: Item,
        requester: User,
        request: Request | None,
        *,
        support_type: SupportType,
        description: str,
        status: SupportStatus,
        resolution: SupportResolution | None = None,
        it_note: str | None = None,
        swapped_to_item: Item | None = None,
        filed_days_ago: int = 5,
        resolved_days_ago: int | None = None,
        auto_closed: bool = False,
    ) -> SupportRequest:
        filed = past(filed_days_ago)
        resolved_at = past(resolved_days_ago) if resolved_days_ago is not None else None
        s = SupportRequest(
            id=uuid.uuid4(),
            item_id=item.id,
            requester_id=requester.id,
            request_id=request.id if request else None,
            type=support_type,
            description=description,
            status=status,
            resolution=resolution,
            it_note=it_note,
            swapped_to_item_id=swapped_to_item.id if swapped_to_item else None,
            filed_at=filed,
            resolved_by=it_admin.id if resolved_at else None,
            resolved_at=resolved_at,
            auto_closed=auto_closed,
        )
        session.add(s)
        await session.flush()
        support_requests.append(s)
        return s

    r1, item1, emp1 = assigned_pairs[0]
    s_open_damage = await make_support(
        item1,
        emp1,
        r1,
        support_type=SupportType.DAMAGE,
        description=rng.choice(SUPPORT_DESCRIPTIONS_DAMAGE),
        status=SupportStatus.OPEN,
        filed_days_ago=2,
    )
    log_event(
        item_id=item1.id,
        event_type=DeviceLogEvent.SUPPORT_OPENED,
        actor_id=emp1.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r1.id,
        support_request_id=s_open_damage.id,
        note=s_open_damage.description,
        is_milestone=True,
        occurred_at=s_open_damage.filed_at,
    )

    r2, item2, emp2 = assigned_pairs[1]
    s_open_update = await make_support(
        item2,
        emp2,
        r2,
        support_type=SupportType.UPDATE,
        description=rng.choice(SUPPORT_DESCRIPTIONS_UPDATE),
        status=SupportStatus.IN_PROGRESS,
        filed_days_ago=4,
    )
    log_event(
        item_id=item2.id,
        event_type=DeviceLogEvent.SUPPORT_OPENED,
        actor_id=emp2.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r2.id,
        support_request_id=s_open_update.id,
        note=s_open_update.description,
        is_milestone=True,
        occurred_at=s_open_update.filed_at,
    )

    r3, item3, emp3 = assigned_pairs[2]
    s_resolved_remote = await make_support(
        item3,
        emp3,
        r3,
        support_type=SupportType.UPDATE,
        description=rng.choice(SUPPORT_DESCRIPTIONS_UPDATE),
        status=SupportStatus.RESOLVED,
        resolution=SupportResolution.REMOTE_RESOLVED,
        it_note="Remote session completed, all software updated successfully",
        filed_days_ago=15,
        resolved_days_ago=12,
    )
    log_event(
        item_id=item3.id,
        event_type=DeviceLogEvent.SUPPORT_OPENED,
        actor_id=emp3.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r3.id,
        support_request_id=s_resolved_remote.id,
        note=s_resolved_remote.description,
        is_milestone=True,
        occurred_at=s_resolved_remote.filed_at,
    )
    log_event(
        item_id=item3.id,
        event_type=DeviceLogEvent.SUPPORT_RESOLVED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r3.id,
        support_request_id=s_resolved_remote.id,
        note="Software update completed via remote session",
        is_milestone=True,
        occurred_at=s_resolved_remote.resolved_at,
    )

    r4, item4, emp4 = assigned_pairs[3]
    s_resolved_repair = await make_support(
        item4,
        emp4,
        r4,
        support_type=SupportType.DAMAGE,
        description=rng.choice(SUPPORT_DESCRIPTIONS_DAMAGE),
        status=SupportStatus.RESOLVED,
        resolution=SupportResolution.REPAIRED_IN_PLACE,
        it_note="Keyboard replacement completed in-house. Device returned to user.",
        filed_days_ago=20,
        resolved_days_ago=10,
    )
    log_event(
        item_id=item4.id,
        event_type=DeviceLogEvent.SUPPORT_OPENED,
        actor_id=emp4.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r4.id,
        support_request_id=s_resolved_repair.id,
        note=s_resolved_repair.description,
        is_milestone=True,
        occurred_at=s_resolved_repair.filed_at,
    )
    log_event(
        item_id=item4.id,
        event_type=DeviceLogEvent.SUPPORT_RESOLVED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r4.id,
        support_request_id=s_resolved_repair.id,
        note="Keyboard replaced successfully",
        is_milestone=True,
        occurred_at=s_resolved_repair.resolved_at,
    )

    # Support on the under-repair device
    s_under_repair = await make_support(
        under_repair_item,
        emp_repair,
        r_repair,
        support_type=SupportType.DAMAGE,
        description="Keyboard intermittently fails — keys 5, 6, Y, U not registering",
        status=SupportStatus.IN_PROGRESS,
        filed_days_ago=5,
    )
    log_event(
        item_id=under_repair_item.id,
        event_type=DeviceLogEvent.SUPPORT_OPENED,
        actor_id=emp_repair.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r_repair.id,
        support_request_id=s_under_repair.id,
        note=s_under_repair.description,
        is_milestone=True,
        occurred_at=s_under_repair.filed_at,
    )

    # Support on the lost device (no linked request)
    lost_reporter = active_employees[0]
    s_lost = await make_support(
        lost_item,
        lost_reporter,
        None,
        support_type=SupportType.LOST,
        description=rng.choice(SUPPORT_DESCRIPTIONS_LOST),
        status=SupportStatus.RESOLVED,
        resolution=SupportResolution.MARKED_LOST,
        it_note="Loss confirmed. Device flagged as lost. IT to decide next status.",
        filed_days_ago=14,
        resolved_days_ago=12,
    )
    log_event(
        item_id=lost_item.id,
        event_type=DeviceLogEvent.SUPPORT_OPENED,
        actor_id=lost_reporter.id,
        actor_role=ActorRole.EMPLOYEE,
        support_request_id=s_lost.id,
        note=s_lost.description,
        is_milestone=True,
        occurred_at=s_lost.filed_at,
    )
    log_event(
        item_id=lost_item.id,
        event_type=DeviceLogEvent.SUPPORT_RESOLVED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        support_request_id=s_lost.id,
        note="Loss confirmed by IT",
        is_milestone=True,
        occurred_at=s_lost.resolved_at,
    )

    # Auto-closed support ticket (system actor), tied to a completed request
    r_comp, item_comp = completed_pairs[0]
    s_auto = await make_support(
        item_comp,
        active_employees[0],
        r_comp,
        support_type=SupportType.UPDATE,
        description="Pending OS update — 3 weeks overdue",
        status=SupportStatus.RESOLVED,
        resolution=SupportResolution.REMOTE_RESOLVED,
        auto_closed=True,
        filed_days_ago=90,
        resolved_days_ago=80,
    )
    log_event(
        item_id=item_comp.id,
        event_type=DeviceLogEvent.SUPPORT_AUTO_CLOSED,
        actor_id=None,
        actor_role=ActorRole.SYSTEM,
        request_id=r_comp.id,
        support_request_id=s_auto.id,
        note="Auto-closed: parent request completed",
        is_milestone=False,
        occurred_at=s_auto.resolved_at,
    )

    # Resolved-via-swap support ticket, with swapped_out/swapped_in device_log
    r_swap, item_swap_from, emp_swap = assigned_pairs[9]
    item_swap_to = monitors[3]
    swap_filed = past(10)
    swap_resolved = past(6)
    s_swap = await make_support(
        item_swap_from,
        emp_swap,
        r_swap,
        support_type=SupportType.DAMAGE,
        description="External display flickering intermittently — panel failure suspected",
        status=SupportStatus.RESOLVED,
        resolution=SupportResolution.SWAPPED,
        it_note="Faulty unit swapped for a spare from inventory",
        swapped_to_item=item_swap_to,
        filed_days_ago=10,
        resolved_days_ago=6,
    )
    log_event(
        item_id=item_swap_from.id,
        event_type=DeviceLogEvent.SUPPORT_OPENED,
        actor_id=emp_swap.id,
        actor_role=ActorRole.EMPLOYEE,
        request_id=r_swap.id,
        support_request_id=s_swap.id,
        note=s_swap.description,
        is_milestone=True,
        occurred_at=swap_filed,
    )
    log_event(
        item_id=item_swap_from.id,
        event_type=DeviceLogEvent.SWAPPED_OUT,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r_swap.id,
        support_request_id=s_swap.id,
        from_value="assigned",
        to_value="under_repair",
        note="Faulty device swapped out and sent for repair",
        is_milestone=True,
        occurred_at=swap_resolved,
    )
    log_event(
        item_id=item_swap_to.id,
        event_type=DeviceLogEvent.SWAPPED_IN,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r_swap.id,
        support_request_id=s_swap.id,
        from_value="available",
        to_value="assigned",
        note="Replacement device swapped in for employee",
        is_milestone=True,
        occurred_at=swap_resolved,
    )
    log_event(
        item_id=item_swap_from.id,
        event_type=DeviceLogEvent.SUPPORT_RESOLVED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        request_id=r_swap.id,
        support_request_id=s_swap.id,
        note="Resolved via device swap",
        is_milestone=True,
        occurred_at=swap_resolved,
    )
    item_swap_from.status = DeviceStatus.UNDER_REPAIR
    item_swap_from.current_owner_id = None
    item_swap_to.status = DeviceStatus.ASSIGNED
    item_swap_to.current_owner_id = emp_swap.id
    r_swap.assigned_item_id = item_swap_to.id

    # ── 9. HANDOVER REQUESTS (6) ─────────────────────────────────────────
    async def make_handover(
        item: Item,
        owner: User,
        borrower: User,
        *,
        status: HandoverStatus,
        duration_hours: int | None = None,
        note: str | None = None,
        requested_at: datetime | None = None,
        decided_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> HandoverRequest:
        ra = requested_at if requested_at is not None else past(rng.randint(1, 10))
        h = HandoverRequest(
            id=uuid.uuid4(),
            item_id=item.id,
            owner_id=owner.id,
            borrower_id=borrower.id,
            requested_duration_hours=duration_hours if duration_hours is not None else rng.randint(1, 8),
            status=status,
            requested_at=ra,
            decided_at=decided_at,
            completed_at=completed_at,
            note=note if note is not None else rng.choice(HANDOVER_NOTES),
        )
        session.add(h)
        await session.flush()
        handovers.append(h)
        return h

    _, item_h1, emp_h1 = assigned_pairs[4]
    borrower_h1 = next_active_employee()
    h1_req = past(3)
    h1_dec = add_hours(past(3), 1)
    h1 = await make_handover(
        item_h1,
        emp_h1,
        borrower_h1,
        status=HandoverStatus.ACCEPTED,
        duration_hours=4,
        note="Borrowing for client demo this afternoon",
        requested_at=h1_req,
        decided_at=h1_dec,
    )
    log_event(
        item_id=item_h1.id,
        event_type=DeviceLogEvent.HANDOVER_REQUESTED,
        actor_id=borrower_h1.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h1.id,
        note=f"{borrower_h1.name} requested handover",
        is_milestone=False,
        occurred_at=h1_req,
    )
    log_event(
        item_id=item_h1.id,
        event_type=DeviceLogEvent.HANDOVER_ACCEPTED,
        actor_id=emp_h1.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h1.id,
        note=f"Handover accepted for {h1.requested_duration_hours} hours",
        is_milestone=True,
        occurred_at=h1_dec,
    )

    _, item_h2, emp_h2 = assigned_pairs[5]
    borrower_h2 = next_active_employee()
    h2_req = past(8)
    h2_dec = add_hours(past(8), 0.5)
    h2_comp = add_hours(past(7), 4)
    h2 = await make_handover(
        item_h2,
        emp_h2,
        borrower_h2,
        status=HandoverStatus.COMPLETED,
        duration_hours=3,
        note="Needed for afternoon workshop",
        requested_at=h2_req,
        decided_at=h2_dec,
        completed_at=h2_comp,
    )
    log_event(
        item_id=item_h2.id,
        event_type=DeviceLogEvent.HANDOVER_REQUESTED,
        actor_id=borrower_h2.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h2.id,
        note=f"{borrower_h2.name} requested handover",
        is_milestone=False,
        occurred_at=h2_req,
    )
    log_event(
        item_id=item_h2.id,
        event_type=DeviceLogEvent.HANDOVER_ACCEPTED,
        actor_id=emp_h2.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h2.id,
        note="Handover accepted",
        is_milestone=True,
        occurred_at=h2_dec,
    )
    log_event(
        item_id=item_h2.id,
        event_type=DeviceLogEvent.HANDOVER_COMPLETED,
        actor_id=emp_h2.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h2.id,
        note="Device returned to owner",
        is_milestone=True,
        occurred_at=h2_comp,
    )

    _, item_h3, emp_h3 = assigned_pairs[6]
    borrower_h3 = next_active_employee()
    h3_req = past(4)
    h3_dec = add_hours(past(4), 2)
    h3 = await make_handover(
        item_h3,
        emp_h3,
        borrower_h3,
        status=HandoverStatus.REJECTED,
        duration_hours=2,
        note=None,
        requested_at=h3_req,
        decided_at=h3_dec,
    )
    log_event(
        item_id=item_h3.id,
        event_type=DeviceLogEvent.HANDOVER_REQUESTED,
        actor_id=borrower_h3.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h3.id,
        note=f"{borrower_h3.name} requested handover",
        is_milestone=False,
        occurred_at=h3_req,
    )
    log_event(
        item_id=item_h3.id,
        event_type=DeviceLogEvent.HANDOVER_REJECTED,
        actor_id=emp_h3.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h3.id,
        note="Owner declined — device needed for own work",
        is_milestone=False,
        occurred_at=h3_dec,
    )

    _, item_h4, emp_h4 = assigned_pairs[7]
    borrower_h4 = next_active_employee()
    h4_req = past(2)
    h4 = await make_handover(
        item_h4,
        emp_h4,
        borrower_h4,
        status=HandoverStatus.CANCELLED,
        duration_hours=1,
        note="No longer needed",
        requested_at=h4_req,
    )
    log_event(
        item_id=item_h4.id,
        event_type=DeviceLogEvent.HANDOVER_REQUESTED,
        actor_id=borrower_h4.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h4.id,
        note=f"{borrower_h4.name} requested handover",
        is_milestone=False,
        occurred_at=h4_req,
    )
    log_event(
        item_id=item_h4.id,
        event_type=DeviceLogEvent.HANDOVER_CANCELLED,
        actor_id=borrower_h4.id,
        actor_role=ActorRole.EMPLOYEE,
        handover_request_id=h4.id,
        note="Borrower cancelled the request",
        is_milestone=False,
        occurred_at=add_hours(h4_req, 1),
    )

    # Two simultaneous "requested" handovers on the same device
    _, item_h5, _emp_h5 = assigned_pairs[8]
    for i in range(2):
        borrower = active_employees[(0 + i) % len(active_employees)]
        h_pending = await make_handover(
            item_h5,
            _emp_h5,
            borrower,
            status=HandoverStatus.REQUESTED,
            duration_hours=rng.randint(1, 3),
            note=rng.choice(HANDOVER_NOTES),
            requested_at=past(i + 1),
        )
        log_event(
            item_id=item_h5.id,
            event_type=DeviceLogEvent.HANDOVER_REQUESTED,
            actor_id=borrower.id,
            actor_role=ActorRole.EMPLOYEE,
            handover_request_id=h_pending.id,
            note=f"{borrower.name} requested handover (simultaneous)",
            is_milestone=False,
            occurred_at=h_pending.requested_at,
        )

    # ── 10. Extra device log — maintenance, edits, client-assigned audit ─
    log_event(
        item_id=maintenance_item.id,
        event_type=DeviceLogEvent.STATUS_CHANGED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        from_value="available",
        to_value="maintenance",
        note="Scheduled maintenance: firmware update batch — estimated 3 days",
        is_milestone=False,
        occurred_at=past(1),
    )

    first_laptop = laptops[0]
    log_event(
        item_id=first_laptop.id,
        event_type=DeviceLogEvent.DEVICE_EDITED,
        actor_id=it_admin.id,
        actor_role=ActorRole.IT_ADMIN,
        note="Serial number corrected after physical audit",
        metadata={"field": "serial_no", "new": first_laptop.serial_no},
        is_milestone=False,
        occurred_at=past(7),
    )

    for cd in client_devices:
        log_event(
            item_id=cd.id,
            event_type=DeviceLogEvent.CLIENT_ASSIGNED,
            actor_id=it_admin.id,
            actor_role=ActorRole.IT_ADMIN,
            from_value="available",
            to_value="assigned",
            note=f"Client device from {cd.client_name} directly assigned",
            is_milestone=True,
            occurred_at=past(rng.randint(10, 60)),
        )

    counts = {
        "users": len(users),
        "item_categories": len(categories),
        "items": len(items),
        "requests": len(requests),
        "extension_requests": len(extensions),
        "support_requests": len(support_requests),
        "handover_requests": len(handovers),
        "device_log": len(device_logs),
    }
    return counts, it_admin.email


async def main() -> None:
    async with AsyncSessionLocal() as session:
        print("Truncating all tables…")
        await session.execute(text(TRUNCATE_SQL))

        print("Seeding demo data…")
        counts, example_email = await seed(session)

        await session.commit()

    print("\nSeed complete. Summary:")
    for table, count in counts.items():
        print(f"  {table:<20} {count}")

    print(f"\nShared dev password for ALL seeded users: {DEV_PASSWORD}")
    print(f"Example login: {example_email} / {DEV_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
