/**
 * ITAM Seed Script (TypeScript + Prisma)
 * =======================================
 * Converted 1:1 from the original Python (psycopg2) seed script.
 *
 * Usage:
 *   npx prisma generate
 *   npx prisma db push          # or: npx prisma migrate dev
 *   DATABASE_URL="postgresql://user:password@localhost:5432/itam_db" npm run seed
 *
 * Behaviour (matches the original):
 *   - Idempotent: running twice is safe (truncates all tables first).
 *   - Deterministic: uses a seeded PRNG (seed 42) so re-runs are reproducible.
 *     NOTE: because JavaScript has no equivalent of Python's `random` module,
 *     the *exact* values generated will differ from the Python version, but
 *     the run-to-run determinism property is preserved.
 *   - Covers every workflow, status, and relationship in schema_v3.dbml.
 */

import "dotenv/config";
import { randomUUID } from "crypto";
import { PrismaPg } from "@prisma/adapter-pg";
import { Pool } from "pg";
import {
  PrismaClient,
  Prisma,
  UserRole,
  OwnerType,
  DeviceStatus,
  RequestStatus,
  RequestPriority,
  MgrApprovalStatus,
  RejectedBy,
  ExtensionStatus,
  SupportType,
  SupportStatus,
  SupportResolution,
  HandoverStatus,
  ActorRole,
  DeviceLogEvent,
  User,
  Item,
  ItemCategory,
  Request,
  ExtensionRequest,
  SupportRequest,
  HandoverRequest,
} from "@prisma/client";

const connectionString = process.env["DATABASE_URL"];

if (!connectionString) {
  throw new Error("DATABASE_URL is not set");
}

const databaseUrl = new URL(connectionString);
const isLocalDatabase = ["localhost", "127.0.0.1", "::1"].includes(databaseUrl.hostname);
const pool = new Pool({
  connectionString,
  ssl: isLocalDatabase ? false : { rejectUnauthorized: false },
});
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

// ═══════════════════════════════════════════════════════════════════════════
// Reproducibility — seeded PRNG (mulberry32), seeded with 42
// ═══════════════════════════════════════════════════════════════════════════
function mulberry32(seed: number) {
  let a = seed;
  return function random(): number {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(42);

function randomFloat(): number {
  return rand();
}

/** Inclusive on both ends, like Python's random.randint(a, b). */
function randomInt(min: number, max: number): number {
  return Math.floor(rand() * (max - min + 1)) + min;
}

function requireValue<T>(value: T | undefined, label: string): T {
  if (value === undefined) {
    throw new Error(`Missing required seed value: ${label}`);
  }
  return value;
}

function at<T>(list: readonly T[], index: number, label = "item"): T {
  return requireValue(list[index], `${label}[${index}]`);
}

function pick<T>(list: readonly T[]): T {
  return at(list, Math.floor(rand() * list.length), "pick");
}

/** Sample n unique items without replacement, like Python's random.sample. */
function sample<T>(list: readonly T[], n: number): T[] {
  const pool = [...list];
  const count = Math.min(n, pool.length);
  const result: T[] = [];
  for (let i = 0; i < count; i++) {
    const idx = Math.floor(rand() * pool.length);
    result.push(requireValue(pool.splice(idx, 1)[0], "sampled item"));
  }
  return result;
}

// ═══════════════════════════════════════════════════════════════════════════
// Helpers — ids, dates
// ═══════════════════════════════════════════════════════════════════════════
function uid(): string {
  return randomUUID();
}

function now(): Date {
  return new Date();
}

function addDays(date: Date, n: number): Date {
  return new Date(date.getTime() + n * 24 * 60 * 60 * 1000);
}

function addHours(date: Date, n: number): Date {
  return new Date(date.getTime() + n * 60 * 60 * 1000);
}

/** Return a UTC datetime relative to today. */
function ts(offsetDays = 0, offsetHours = 0): Date {
  return addHours(addDays(now(), offsetDays), offsetHours);
}

function past(d = 0, h = 0): Date {
  return ts(-d, -h);
}

function future(d = 0, h = 0): Date {
  return ts(d, h);
}

function subHours(date: Date, n: number): Date {
  return addHours(date, -n);
}

function dateOnly(date: Date): Date {
  return new Date(date.toISOString().slice(0, 10));
}

// ═══════════════════════════════════════════════════════════════════════════
// Realistic static data
// ═══════════════════════════════════════════════════════════════════════════
const FIRST_NAMES = [
  "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", "Henry",
  "Isabella", "Jack", "Karen", "Leo", "Mia", "Noah", "Olivia", "Paul",
  "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xander",
  "Yasmine", "Zach", "Amber", "Brian", "Chloe", "Derek", "Elena", "Felix",
  "Gina", "Hank", "Iris", "James", "Kira", "Luke", "Maya", "Nate",
  "Opal", "Pete", "Rosa", "Steve", "Tracy", "Ursula", "Vince", "Wanda",
];
const LAST_NAMES = [
  "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
  "Davis", "Wilson", "Anderson", "Taylor", "Thomas", "Moore", "Martin",
  "Jackson", "Lee", "Perez", "Thompson", "White", "Harris", "Clark",
  "Lewis", "Robinson", "Walker", "Hall", "Young", "Allen", "King",
  "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
];

// Unused by the original script's logic, kept for data-fidelity parity.
const DEVICE_ADJECTIVES = ["Pro", "Air", "Ultra", "Max", "Plus", "Elite", "Slim", "Go"];

const LAPTOP_MODELS = [
  'MacBook Pro 14"', 'MacBook Pro 16"', "MacBook Air M2", "MacBook Air M3",
  "Dell XPS 13", "Dell XPS 15", "Dell Latitude 5540", "Dell Latitude 7440",
  "HP EliteBook 840", "HP EliteBook 860", "HP ZBook Studio G10",
  "Lenovo ThinkPad X1 Carbon", "Lenovo ThinkPad T14s", "Lenovo IdeaPad 5 Pro",
  "ASUS ZenBook 14", "ASUS ProArt Studiobook", "Microsoft Surface Laptop 5",
];
const PHONE_MODELS = [
  "iPhone 15 Pro", "iPhone 15 Pro Max", "iPhone 14 Pro",
  "Samsung Galaxy S24 Ultra", "Samsung Galaxy S24+",
  "Google Pixel 8 Pro", "Google Pixel 8",
  "OnePlus 12", "Xiaomi 14 Pro",
];
const MONITOR_MODELS = [
  'Dell UltraSharp 27" 4K', 'Dell UltraSharp 32" 4K',
  'LG UltraFine 27"', 'LG 34" UltraWide',
  'Samsung 32" Curved QHD', 'BenQ PD2725U 27"',
  "Apple Pro Display XDR", "ASUS ProArt PA329CV",
];
const KEYBOARD_MODELS = [
  "Apple Magic Keyboard", "Logitech MX Keys", "Keychron K3 Pro",
  "Keychron Q1 Pro", "Das Keyboard 4 Professional", "Razer BlackWidow V4",
];
const MOUSE_MODELS = [
  "Apple Magic Mouse", "Logitech MX Master 3S", "Logitech MX Anywhere 3",
  "Razer DeathAdder V3", "Microsoft Arc Mouse", "Logitech G Pro X Superlight",
];
const HEADSET_MODELS = [
  "Sony WH-1000XM5", "Bose QuietComfort 45", "Apple AirPods Pro (2nd Gen)",
  "Jabra Evolve2 85", "Sennheiser HD 450BT", "Poly Voyager Focus 2",
];
const CHARGER_MODELS = [
  "Apple 140W USB-C Power Adapter", "Apple 67W MagSafe Adapter",
  "Anker 65W GaN Charger", "Dell 130W USB-C Slim Power Adapter",
  "Belkin 108W GaN 3-Port Charger",
];
const TABLET_MODELS = [
  'iPad Pro 12.9" M2', "iPad Air M1", "iPad mini 6th Gen",
  "Samsung Galaxy Tab S9 Ultra", "Microsoft Surface Pro 9",
];
const DOCK_MODELS = [
  "CalDigit TS4 Thunderbolt 4 Dock", "Dell Thunderbolt Dock WD22TB4",
  "Anker 13-in-1 USB-C Hub", "Belkin Thunderbolt 3 Dock Pro",
];

const CLIENT_NAMES = ["Acme Corp", "TechVentures Ltd", "GlobalFinance Inc", "StartupXYZ"];

const SUPPORT_DESCRIPTIONS_UPDATE = [
  "macOS needs updating to the latest version",
  "Chrome and Slack are out of date, please update",
  "Security patch required for firmware",
  "Battery calibration update needed",
  "Remote Desktop software needs fresh install",
];
const SUPPORT_DESCRIPTIONS_DAMAGE = [
  "Screen cracked after dropping the device",
  "Keyboard keys are sticky and some are not registering",
  "Charging port is loose and device won't charge properly",
  "Fan making loud grinding noise",
  "Trackpad is unresponsive after liquid spill",
  "Hinge is broken on laptop lid",
];
const SUPPORT_DESCRIPTIONS_LOST = [
  "Device left in taxi after client meeting — cannot locate",
  "Stolen from desk in shared office space",
  "Left at airport, reported missing to lost property",
  "Cannot locate device after office relocation",
];

const REQUEST_NOTES: (string | null)[] = [
  "Need for upcoming client presentation",
  "Replacement for my device which is in repair",
  "Required for remote work setup",
  "New hire onboarding — day one start",
  "Short-term project requirement ends next quarter",
  "Travelling for 3 weeks, need portable option",
  "Current device is too slow for development work",
  "Designer needs better display for creative work",
  null, null, null, // some requests have no note
];

const HANDOVER_NOTES: (string | null)[] = [
  "Borrowing for afternoon presentation",
  "Mine is with IT for repair",
  "Need to demo to client in meeting room",
  "Quick loan while mine is being charged",
  null,
];

// ═══════════════════════════════════════════════════════════════════════════
// Name generator
// ═══════════════════════════════════════════════════════════════════════════
const usedNames = new Set<string>();
function makeName(): string {
  for (let i = 0; i < 200; i++) {
    const n = `${pick(FIRST_NAMES)} ${pick(LAST_NAMES)}`;
    if (!usedNames.has(n)) {
      usedNames.add(n);
      return n;
    }
  }
  return `User ${uid().slice(0, 8)}`;
}

function makeEmail(name: string): string {
  const parts = name.toLowerCase().split(" ");
  return `${requireValue(parts[0], "email first name")}.${requireValue(parts[1], "email last name")}@techcorp.internal`;
}

function makeSerial(prefix = "SN"): string {
  return `${prefix}-${randomInt(100000, 999999)}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Types used by internal helpers
// ═══════════════════════════════════════════════════════════════════════════
type ItDecidedByArg = User | "none" | null | undefined;

const PENDING_LIKE_STATUSES: RequestStatus[] = [
  RequestStatus.requested,
  RequestStatus.pending_mgr_approval,
  RequestStatus.pending_it_approval,
  RequestStatus.rejected,
  RequestStatus.cancelled,
];

function computeItDecidedById(
  itDecidedBy: ItDecidedByArg,
  status: RequestStatus,
  itAdminId: string
): string | null {
  const isFinalStatus = !PENDING_LIKE_STATUSES.includes(status);
  const isRealUser = itDecidedBy != null && itDecidedBy !== "none";
  if (itDecidedBy !== "none" && isFinalStatus) {
    return isRealUser ? (itDecidedBy as User).id : itAdminId;
  }
  return isRealUser ? (itDecidedBy as User).id : null;
}

// ═══════════════════════════════════════════════════════════════════════════
// SEED FUNCTION
// ═══════════════════════════════════════════════════════════════════════════
async function runSeed(tx: Prisma.TransactionClient) {
  // ── 0. Truncate everything ──────────────────────────────────────────────
  console.log("Truncating all tables…");
  await tx.$executeRawUnsafe(`
    TRUNCATE TABLE
      device_log,
      support_request,
      handover_request,
      extension_request,
      request,
      item,
      item_category,
      "user"
    RESTART IDENTITY CASCADE;
  `);

  // ═══════════════════════════════════════════════════════════════════════
  // 1. USERS
  // ═══════════════════════════════════════════════════════════════════════
  // Creation order matters for FK validity:
  //   1. Managers first   — no FK dependencies (managerId = null)
  //   2. IT Admins second — no FK dependencies (managerId = null)
  //   3. Employees last   — each has managerId → user.id (a manager),
  //                         so the referenced manager row MUST already exist.
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding users…");

  const managers: User[] = [];
  const itAdmins: User[] = [];
  const employees: User[] = [];

  // ── 1a. 5 Managers (created FIRST — employees reference them via FK) ──
  for (let i = 0; i < 5; i++) {
    const name = makeName();
    const u = await tx.user.create({
      data: {
        id: uid(),
        name,
        email: makeEmail(name),
        role: UserRole.manager,
        managerId: null,
        isActive: true,
        createdAt: past(180),
        updatedAt: past(10),
      },
    });
    managers.push(u);
  }

  // ── 1b. 3 IT Admins ───────────────────────────────────────────────────
  for (let i = 0; i < 3; i++) {
    const name = makeName();
    const u = await tx.user.create({
      data: {
        id: uid(),
        name,
        email: makeEmail(name),
        role: UserRole.it_admin,
        managerId: null,
        isActive: true,
        createdAt: past(180),
        updatedAt: past(10),
      },
    });
    itAdmins.push(u);
  }

  // ── 1c. 30 Employees — each assigned to an already-created manager ────
  for (let i = 0; i < 30; i++) {
    const name = makeName();
    const mgr = pick(managers);
    const u = await tx.user.create({
      data: {
        id: uid(),
        name,
        email: makeEmail(name),
        role: UserRole.employee,
        managerId: mgr.id,
        isActive: i < 28,
        createdAt: past(randomInt(30, 180)),
        updatedAt: past(randomInt(1, 15)),
      },
    });
    employees.push(u);
  }

  const allUsers = [...managers, ...itAdmins, ...employees];
  const activeEmployees = employees.filter((e) => e.isActive);
  const itAdmin = at(itAdmins, 0, "itAdmins"); // primary IT admin for most actions

  let empIdx = 0;
  function nextActiveEmployee(): User {
    const emp = at(activeEmployees, empIdx % activeEmployees.length, "activeEmployees");
    empIdx += 1;
    return emp;
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 2. ITEM CATEGORIES
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding item categories…");

  const catDefs: Array<[string, string, boolean, boolean]> = [
    ["Laptop", "Portable computers for daily work", true, true],
    ["Mobile Phone", "Company smartphones for employees", true, true],
    ["Monitor", "External display monitors", false, true],
    ["Keyboard", "Mechanical and membrane keyboards", false, true],
    ["Mouse", "Wireless and wired mice", false, true],
    ["Headset", "Noise-cancelling headsets and earphones", false, true],
    ["Charger", "Power adapters and charging cables", false, true],
    ["Tablet", "Tablets for presentations and fieldwork", true, true],
    ["Dock", "Docking stations and USB-C hubs", false, true],
    ["Legacy", "Retired category for old device types", false, false],
  ];
  const categories: Record<string, ItemCategory> = {};
  for (const [name, desc, reqMgr, isActive] of catDefs) {
    const c = await tx.itemCategory.create({
      data: {
        id: uid(),
        name,
        description: desc,
        requiresMgrApproval: reqMgr,
        isActive,
        createdAt: past(200),
        updatedAt: past(5),
      },
    });
    categories[name] = c;
  }

  function getCategory(name: string): ItemCategory {
    return requireValue(categories[name], `category ${name}`);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 3. ITEMS (DEVICES)
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding items (devices)…");

  const items: Item[] = [];

  interface MakeItemOpts {
    status?: DeviceStatus;
    ownerType?: OwnerType;
    clientName?: string | null;
    currentOwnerId?: string | null;
    purchaseDaysAgo?: number;
  }

  async function makeItem(
    name: string,
    categoryName: string,
    opts: MakeItemOpts = {}
  ): Promise<Item> {
    const purchaseDaysAgo = opts.purchaseDaysAgo ?? randomInt(30, 730);
    const pd = past(purchaseDaysAgo);
    const i = await tx.item.create({
      data: {
        id: uid(),
        name,
        serialNo: makeSerial(),
        categoryId: getCategory(categoryName).id,
        ownerType: opts.ownerType ?? OwnerType.company,
        clientName: opts.clientName ?? null,
        status: opts.status ?? DeviceStatus.available,
        currentOwnerId: opts.currentOwnerId ?? null,
        purchaseDate: dateOnly(past(purchaseDaysAgo)),
        qrCodeToken: uid(),
        createdAt: pd,
        updatedAt: now(),
      },
    });
    items.push(i);
    return i;
  }

  // Laptops — 12 units created (mirrors original sample size)
  const laptops: Item[] = [];
  for (const model of sample(LAPTOP_MODELS, 12)) {
    laptops.push(await makeItem(model, "Laptop"));
  }
  const laptopsForAssign = laptops.slice(0, 8);

  // Phones — 8 units
  const phones: Item[] = [];
  for (const model of sample(PHONE_MODELS, 8)) {
    phones.push(await makeItem(model, "Mobile Phone"));
  }
  const phonesForAssign = phones.slice(0, 5);

  // Monitors — 10 units
  const monitors: Item[] = [];
  for (const model of sample(MONITOR_MODELS, 10)) {
    monitors.push(await makeItem(model, "Monitor"));
  }

  // Keyboards — 8 units
  const keyboards: Item[] = [];
  for (const model of sample(KEYBOARD_MODELS, 8)) {
    keyboards.push(await makeItem(model, "Keyboard"));
  }

  // Mice — 6 units
  const mice: Item[] = [];
  for (const model of sample(MOUSE_MODELS, 6)) {
    mice.push(await makeItem(model, "Mouse"));
  }

  // Headsets — 6 units
  const headsets: Item[] = [];
  for (const model of sample(HEADSET_MODELS, 6)) {
    headsets.push(await makeItem(model, "Headset"));
  }

  // Chargers — 5 units
  const chargers: Item[] = [];
  for (const model of sample(CHARGER_MODELS, 5)) {
    chargers.push(await makeItem(model, "Charger"));
  }

  // Tablets — 5 units
  const tablets: Item[] = [];
  for (const model of sample(TABLET_MODELS, 5)) {
    tablets.push(await makeItem(model, "Tablet"));
  }

  // Docks — 4 units
  const docks: Item[] = [];
  for (const model of sample(DOCK_MODELS, 4)) {
    docks.push(await makeItem(model, "Dock"));
  }

  // Client-owned devices — direct assign, skip request lifecycle
  const clientDevices: Item[] = [];
  for (let i = 0; i < CLIENT_NAMES.length; i++) {
    const cn = at(CLIENT_NAMES, i, "CLIENT_NAMES");
    const model = pick(LAPTOP_MODELS);
    const cd = await makeItem(`${cn} — ${model}`, "Laptop", {
      ownerType: OwnerType.client,
      clientName: cn,
      status: DeviceStatus.assigned,
      currentOwnerId: at(activeEmployees, i, "activeEmployees").id,
    });
    clientDevices.push(cd);
  }

  // Some devices in special states
  const underRepairItem = await makeItem(pick(LAPTOP_MODELS), "Laptop", {
    status: DeviceStatus.under_repair,
  });
  const maintenanceItem = await makeItem(pick(MONITOR_MODELS), "Monitor", {
    status: DeviceStatus.maintenance,
  });
  const lostItem = await makeItem(pick(PHONE_MODELS), "Mobile Phone", {
    status: DeviceStatus.lost,
  });
  const retiredItem = await makeItem(pick(LAPTOP_MODELS), "Laptop", {
    status: DeviceStatus.retired,
    purchaseDaysAgo: 1460,
  });

  // ═══════════════════════════════════════════════════════════════════════
  // Device log helper
  // ═══════════════════════════════════════════════════════════════════════
  interface LogEventOpts {
    itemId: string;
    eventType: DeviceLogEvent;
    actorRole: ActorRole;
    actorId?: string | null;
    requestId?: string | null;
    supportRequestId?: string | null;
    extensionRequestId?: string | null;
    handoverRequestId?: string | null;
    fromValue?: string | null;
    toValue?: string | null;
    note?: string | null;
    metadata?: Record<string, unknown> | null;
    isMilestone?: boolean;
    occurredAt?: Date | null;
  }

  async function logEvent(opts: LogEventOpts) {
    const occurredAt = opts.occurredAt ?? now();
    await tx.deviceLog.create({
      data: {
        id: uid(),
        itemId: opts.itemId,
        eventType: opts.eventType,
        actorId: opts.actorId ?? null,
        actorRole: opts.actorRole,
        requestId: opts.requestId ?? null,
        supportRequestId: opts.supportRequestId ?? null,
        extensionRequestId: opts.extensionRequestId ?? null,
        handoverRequestId: opts.handoverRequestId ?? null,
        fromValue: opts.fromValue ?? null,
        toValue: opts.toValue ?? null,
        note: opts.note ?? null,
        metadata: (opts.metadata ?? {}) as Prisma.InputJsonValue,
        isMilestone: opts.isMilestone ?? false,
        occurredAt,
        createdAt: occurredAt,
        updatedAt: occurredAt,
      },
    });
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 4. DEVICE LOG — device_created for every item
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding device_created log entries…");
  for (const item of items) {
    await logEvent({
      itemId: item.id,
      eventType: "device_created",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      toValue: "available",
      note: `Device added to inventory: ${item.name}`,
      isMilestone: false,
      occurredAt: item.createdAt,
    });
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 5. REQUESTS — FULL SPECTRUM OF STATUSES
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding requests…");
  const requests: Request[] = [];

  interface MakeRequestOpts {
    status: RequestStatus;
    priority?: RequestPriority;
    reqFrom: Date;
    reqTo: Date;
    assignedItem?: Item | null;
    assignedFrom?: Date | null;
    assignedTo?: Date | null;
    requiresMgr?: boolean | null;
    mgrStatus?: MgrApprovalStatus;
    managerId?: string | null;
    mgrNote?: string | null;
    mgrDecidedAt?: Date | null;
    itDecidedBy?: ItDecidedByArg;
    itNote?: string | null;
    itDecidedAt?: Date | null;
    rejectedBy?: RejectedBy | null;
    rejectedReason?: string | null;
    cancelledBy?: User | null;
    cancelledAt?: Date | null;
    isWfh?: boolean;
    shipTracking?: string | null;
    shipInit?: Date | null;
    shipDone?: Date | null;
    retTracking?: string | null;
    retInit?: Date | null;
    completedAt?: Date | null;
    completedBy?: User | null;
    completedNext?: DeviceStatus | null;
    isClientDirect?: boolean;
    note?: string | null;
    createdAt?: Date | null;
  }

  async function makeRequest(
    requester: User,
    categoryName: string,
    opts: MakeRequestOpts
  ): Promise<Request> {
    const cat = getCategory(categoryName);
    const requiresMgr = opts.requiresMgr ?? cat.requiresMgrApproval;
    const createdAt = opts.createdAt ?? addDays(opts.reqFrom, -3);
    const r = await tx.request.create({
      data: {
        id: uid(),
        requesterId: requester.id,
        categoryId: cat.id,
        assignedItemId: opts.assignedItem ? opts.assignedItem.id : null,
        requestedFrom: opts.reqFrom,
        requestedTo: opts.reqTo,
        assignedFrom: opts.assignedFrom ?? null,
        assignedTo: opts.assignedTo ?? null,
        status: opts.status,
        priority: opts.priority ?? RequestPriority.medium,
        note: opts.note ?? pick(REQUEST_NOTES),
        requiresMgrApproval: requiresMgr,
        mgrApprovalStatus: opts.mgrStatus ?? MgrApprovalStatus.not_required,
        managerId: opts.managerId ?? requester.managerId ?? null,
        managerDecisionNote: opts.mgrNote ?? null,
        managerDecidedAt: opts.mgrDecidedAt ?? null,
        itDecidedById: computeItDecidedById(opts.itDecidedBy, opts.status, itAdmin.id),
        itDecisionNote: opts.itNote ?? null,
        itDecidedAt: opts.itDecidedAt ?? null,
        rejectedBy: opts.rejectedBy ?? null,
        rejectedReason: opts.rejectedReason ?? null,
        cancelledById: opts.cancelledBy ? opts.cancelledBy.id : null,
        cancelledAt: opts.cancelledAt ?? null,
        isWfh: opts.isWfh ?? false,
        shipTrackingUrl: opts.shipTracking ?? null,
        shipInitiatedAt: opts.shipInit ?? null,
        shipCompletedAt: opts.shipDone ?? null,
        returnTrackingUrl: opts.retTracking ?? null,
        returnInitiatedAt: opts.retInit ?? null,
        completedAt: opts.completedAt ?? null,
        completedById: opts.completedBy ? opts.completedBy.id : null,
        completedNextStatus: opts.completedNext ?? null,
        isClientDirect: opts.isClientDirect ?? false,
        createdAt,
        updatedAt: now(),
      },
    });
    requests.push(r);
    return r;
  }

  // ── 5a. Completed requests (historical) ────────────────────────────────
  const completedPairs: Array<[Request, Item]> = [];

  for (const item of laptopsForAssign.slice(0, 5)) {
    const emp = nextActiveEmployee();
    const start = past(randomInt(60, 120));
    const end = past(randomInt(10, 55));
    const r = await makeRequest(emp, "Laptop", {
      status: RequestStatus.completed,
      priority: pick([RequestPriority.low, RequestPriority.medium, RequestPriority.high]),
      reqFrom: start,
      reqTo: addDays(end, 5),
      assignedItem: item,
      assignedFrom: start,
      assignedTo: end,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.approved,
      managerId: emp.managerId,
      mgrDecidedAt: addHours(start, 4),
      itDecidedAt: addHours(start, 8),
      completedAt: end,
      completedBy: itAdmin,
      completedNext: DeviceStatus.available,
      createdAt: addDays(start, -5),
    });
    completedPairs.push([r, item]);
    // Reset item to available after completion
    await tx.item.update({
      where: { id: item.id },
      data: { status: DeviceStatus.available, currentOwnerId: null },
    });
    item.status = DeviceStatus.available;
    item.currentOwnerId = null;
  }

  for (const item of phonesForAssign.slice(0, 3)) {
    const emp = nextActiveEmployee();
    const start = past(randomInt(40, 90));
    const end = past(randomInt(5, 35));
    const r = await makeRequest(emp, "Mobile Phone", {
      status: RequestStatus.completed,
      priority: RequestPriority.medium,
      reqFrom: start,
      reqTo: addDays(end, 3),
      assignedItem: item,
      assignedFrom: start,
      assignedTo: end,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.approved,
      managerId: emp.managerId,
      mgrDecidedAt: addHours(start, 6),
      itDecidedAt: addHours(start, 10),
      completedAt: end,
      completedBy: itAdmin,
      completedNext: DeviceStatus.available,
      createdAt: addDays(start, -4),
    });
    completedPairs.push([r, item]);
    await tx.item.update({
      where: { id: item.id },
      data: { status: DeviceStatus.available, currentOwnerId: null },
    });
    item.status = DeviceStatus.available;
    item.currentOwnerId = null;
  }

  // Completed WFH request
  const wfhItem = at(laptopsForAssign, 5, "laptopsForAssign");
  {
    const emp = nextActiveEmployee();
    const wfhStart = past(50);
    const wfhEnd = past(5);
    const rWfhDone = await makeRequest(emp, "Laptop", {
      status: RequestStatus.completed,
      priority: RequestPriority.high,
      reqFrom: wfhStart,
      reqTo: addDays(wfhEnd, 2),
      assignedItem: wfhItem,
      assignedFrom: addDays(wfhStart, 2),
      assignedTo: wfhEnd,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.approved,
      managerId: emp.managerId,
      mgrDecidedAt: addHours(wfhStart, 3),
      itDecidedAt: addHours(wfhStart, 6),
      isWfh: true,
      shipTracking: "https://tracking.dhl.com/ABC123456",
      shipInit: addHours(wfhStart, 8),
      shipDone: addDays(wfhStart, 2),
      retTracking: "https://tracking.ups.com/XYZ789012",
      retInit: addDays(wfhEnd, -2),
      completedAt: wfhEnd,
      completedBy: itAdmin,
      completedNext: DeviceStatus.available,
      createdAt: addDays(wfhStart, -4),
    });
    completedPairs.push([rWfhDone, wfhItem]);
    await tx.item.update({
      where: { id: wfhItem.id },
      data: { status: DeviceStatus.available, currentOwnerId: null },
    });
    wfhItem.status = DeviceStatus.available;
    wfhItem.currentOwnerId = null;
  }

  // ── 5b. Active assigned requests ───────────────────────────────────────
  const assignedPairs: Array<[Request, Item, User]> = [];

  const activeLaptopItems = laptops.filter((i) => i.status === DeviceStatus.available).slice(0, 6);
  for (const item of activeLaptopItems) {
    const emp = nextActiveEmployee();
    const start = past(randomInt(5, 30));
    const end = future(randomInt(10, 60));
    const r = await makeRequest(emp, "Laptop", {
      status: RequestStatus.assigned,
      priority: pick([RequestPriority.medium, RequestPriority.high]),
      reqFrom: start,
      reqTo: end,
      assignedItem: item,
      assignedFrom: start,
      assignedTo: end,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.approved,
      managerId: emp.managerId,
      mgrDecidedAt: addHours(addDays(start, -2), 4),
      itDecidedAt: addDays(start, -1),
      createdAt: addDays(start, -5),
    });
    await tx.item.update({
      where: { id: item.id },
      data: { status: DeviceStatus.assigned, currentOwnerId: emp.id },
    });
    item.status = DeviceStatus.assigned;
    item.currentOwnerId = emp.id;
    assignedPairs.push([r, item, emp]);
  }

  const activePhoneItems = phones.filter((i) => i.status === DeviceStatus.available).slice(0, 3);
  for (const item of activePhoneItems) {
    const emp = nextActiveEmployee();
    const start = past(randomInt(3, 20));
    const end = future(randomInt(10, 45));
    const r = await makeRequest(emp, "Mobile Phone", {
      status: RequestStatus.assigned,
      priority: RequestPriority.medium,
      reqFrom: start,
      reqTo: end,
      assignedItem: item,
      assignedFrom: start,
      assignedTo: end,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.approved,
      managerId: emp.managerId,
      mgrDecidedAt: addHours(addDays(start, -1), 3),
      itDecidedAt: start,
      createdAt: addDays(start, -3),
    });
    await tx.item.update({
      where: { id: item.id },
      data: { status: DeviceStatus.assigned, currentOwnerId: emp.id },
    });
    item.status = DeviceStatus.assigned;
    item.currentOwnerId = emp.id;
    assignedPairs.push([r, item, emp]);
  }

  // Active monitor assignment (no manager approval)
  for (const item of monitors.filter((i) => i.status === DeviceStatus.available).slice(0, 3)) {
    const emp = nextActiveEmployee();
    const start = past(randomInt(2, 15));
    const end = future(randomInt(20, 90));
    const r = await makeRequest(emp, "Monitor", {
      status: RequestStatus.assigned,
      priority: RequestPriority.low,
      reqFrom: start,
      reqTo: end,
      assignedItem: item,
      assignedFrom: start,
      assignedTo: end,
      requiresMgr: false,
      mgrStatus: MgrApprovalStatus.not_required,
      itDecidedAt: start,
      createdAt: addDays(start, -2),
    });
    await tx.item.update({
      where: { id: item.id },
      data: { status: DeviceStatus.assigned, currentOwnerId: emp.id },
    });
    item.status = DeviceStatus.assigned;
    item.currentOwnerId = emp.id;
    assignedPairs.push([r, item, emp]);
  }

  // WFH active — outbound shipping in progress
  const wfhShipItem = at(laptops.filter((i) => i.status === DeviceStatus.available), 0, "available laptops");
  {
    const empWfh = nextActiveEmployee();
    const wfhS2Start = past(1);
    const wfhS2End = future(30);
    const rWfhShip = await makeRequest(empWfh, "Laptop", {
      status: RequestStatus.assigned,
      priority: RequestPriority.high,
      reqFrom: wfhS2Start,
      reqTo: wfhS2End,
      assignedItem: wfhShipItem,
      assignedFrom: addDays(wfhS2Start, 3),
      assignedTo: wfhS2End,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.approved,
      managerId: empWfh.managerId,
      mgrDecidedAt: addHours(past(3), 4),
      itDecidedAt: past(2),
      isWfh: true,
      shipTracking: "https://tracking.fedex.com/DEF456789",
      shipInit: past(1),
      createdAt: past(5),
    });
    await tx.item.update({
      where: { id: wfhShipItem.id },
      data: { status: DeviceStatus.shipping_pending, currentOwnerId: empWfh.id },
    });
    wfhShipItem.status = DeviceStatus.shipping_pending;
    wfhShipItem.currentOwnerId = empWfh.id;
    assignedPairs.push([rWfhShip, wfhShipItem, empWfh]);
  }

  // WFH active — return shipping in progress
  const availableLaptopsNow = laptops.filter((i) => i.status === DeviceStatus.available);
  const wfhRetItem = availableLaptopsNow.length > 0 ? at(availableLaptopsNow, 0, "availableLaptopsNow") : at(laptops, laptops.length - 1, "laptops");
  {
    const empWfh2 = nextActiveEmployee();
    const wfhRStart = past(25);
    const wfhREnd = future(2);
    const rWfhRet = await makeRequest(empWfh2, "Laptop", {
      status: RequestStatus.assigned,
      priority: RequestPriority.medium,
      reqFrom: wfhRStart,
      reqTo: wfhREnd,
      assignedItem: wfhRetItem,
      assignedFrom: addDays(wfhRStart, 2),
      assignedTo: wfhREnd,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.approved,
      managerId: empWfh2.managerId,
      mgrDecidedAt: addDays(wfhRStart, -1),
      itDecidedAt: wfhRStart,
      isWfh: true,
      shipTracking: "https://tracking.dhl.com/GHI012345",
      shipInit: addHours(wfhRStart, 6),
      shipDone: addDays(wfhRStart, 2),
      retTracking: "https://tracking.ups.com/JKL678901",
      retInit: past(2),
      createdAt: addDays(wfhRStart, -3),
    });
    await tx.item.update({
      where: { id: wfhRetItem.id },
      data: { status: DeviceStatus.return_shipping_pending, currentOwnerId: empWfh2.id },
    });
    wfhRetItem.status = DeviceStatus.return_shipping_pending;
    wfhRetItem.currentOwnerId = empWfh2.id;
    assignedPairs.push([rWfhRet, wfhRetItem, empWfh2]);
  }

  // ── 5c. Pending IT approval ─────────────────────────────────────────────
  const pendingItReqs: Request[] = [];
  for (let i = 0; i < 6; i++) {
    const emp = nextActiveEmployee();
    const catName = pick(["Laptop", "Monitor", "Keyboard", "Headset"]);
    const cat = getCategory(catName);
    const start = future(randomInt(1, 14));
    const end = future(randomInt(20, 60));
    const needsMgr = cat.requiresMgrApproval;
    const r = await makeRequest(emp, catName, {
      status: RequestStatus.pending_it_approval,
      priority: pick([RequestPriority.low, RequestPriority.medium, RequestPriority.high]),
      reqFrom: start,
      reqTo: end,
      requiresMgr: needsMgr,
      mgrStatus: needsMgr ? MgrApprovalStatus.approved : MgrApprovalStatus.not_required,
      managerId: needsMgr ? emp.managerId : null,
      mgrDecidedAt: needsMgr ? subHours(now(), randomInt(1, 48)) : null,
      itDecidedBy: "none",
      createdAt: past(randomInt(1, 5)),
    });
    pendingItReqs.push(r);
  }

  // ── 5d. Pending manager approval ────────────────────────────────────────
  const pendingMgrReqs: Request[] = [];
  for (let i = 0; i < 4; i++) {
    const emp = nextActiveEmployee();
    const catName = pick(["Laptop", "Mobile Phone", "Tablet"]);
    const start = future(randomInt(5, 20));
    const end = future(randomInt(25, 70));
    const r = await makeRequest(emp, catName, {
      status: RequestStatus.pending_mgr_approval,
      priority: pick([RequestPriority.medium, RequestPriority.high]),
      reqFrom: start,
      reqTo: end,
      requiresMgr: true,
      mgrStatus: MgrApprovalStatus.pending,
      managerId: emp.managerId,
      itDecidedBy: "none",
      createdAt: past(randomInt(0, 3)),
    });
    pendingMgrReqs.push(r);
  }

  // ── 5e. Just submitted (requested) ──────────────────────────────────────
  const plainRequested: Request[] = [];
  for (let i = 0; i < 3; i++) {
    const emp = nextActiveEmployee();
    const catName = pick(["Mouse", "Charger", "Keyboard", "Monitor"]);
    const cat = getCategory(catName);
    const start = future(randomInt(1, 10));
    const end = future(randomInt(15, 45));
    const r = await makeRequest(emp, catName, {
      status: RequestStatus.requested,
      priority: pick([RequestPriority.low, RequestPriority.medium]),
      reqFrom: start,
      reqTo: end,
      requiresMgr: cat.requiresMgrApproval,
      mgrStatus: MgrApprovalStatus.not_required,
      itDecidedBy: "none",
      createdAt: past(randomInt(0, 1)),
    });
    plainRequested.push(r);
  }

  // ── 5f. Rejected requests ───────────────────────────────────────────────
  for (let i = 0; i < 4; i++) {
    const emp = nextActiveEmployee();
    const catName = pick(["Laptop", "Mobile Phone", "Tablet"]);
    const start = past(randomInt(20, 60));
    const end = past(randomInt(5, 18));
    const byMgr = randomFloat() < 0.5;
    await makeRequest(emp, catName, {
      status: RequestStatus.rejected,
      priority: pick([RequestPriority.low, RequestPriority.medium, RequestPriority.high]),
      reqFrom: start,
      reqTo: end,
      requiresMgr: true,
      mgrStatus: byMgr ? MgrApprovalStatus.rejected : MgrApprovalStatus.approved,
      managerId: emp.managerId,
      mgrDecidedAt: byMgr ? addHours(start, 8) : addHours(start, 4),
      itDecidedBy: byMgr ? "none" : undefined,
      itDecidedAt: byMgr ? null : addHours(start, 12),
      rejectedBy: byMgr ? RejectedBy.manager : RejectedBy.it_admin,
      rejectedReason: pick([
        "Device not available for requested period",
        "Business justification insufficient",
        "Employee already has active assignment in this category",
        "Request period conflicts with planned maintenance",
        "Priority level does not meet threshold for this device type",
      ]),
      createdAt: addDays(start, -3),
    });
  }

  // ── 5g. Cancelled requests ──────────────────────────────────────────────
  for (let i = 0; i < 3; i++) {
    const emp = nextActiveEmployee();
    const catName = pick(["Monitor", "Keyboard", "Dock"]);
    const start = past(randomInt(15, 45));
    const cancelAt = addHours(start, randomInt(2, 24));
    await makeRequest(emp, catName, {
      status: RequestStatus.cancelled,
      priority: RequestPriority.low,
      reqFrom: addDays(start, 5),
      reqTo: addDays(start, 25),
      requiresMgr: false,
      mgrStatus: MgrApprovalStatus.not_required,
      itDecidedBy: "none",
      cancelledBy: emp,
      cancelledAt: cancelAt,
      createdAt: start,
    });
  }

  // ── 5h. Client direct-assign requests (for audit symmetry) ──────────────
  for (let i = 0; i < Math.min(clientDevices.length, activeEmployees.length, 4); i++) {
    const cd = at(clientDevices, i, "clientDevices");
    const empI = at(activeEmployees, i, "activeEmployees");
    const start = past(randomInt(10, 60));
    const r = await makeRequest(empI, "Laptop", {
      status: RequestStatus.assigned,
      priority: RequestPriority.high,
      reqFrom: start,
      reqTo: future(60),
      assignedItem: cd,
      assignedFrom: start,
      assignedTo: future(60),
      requiresMgr: false,
      mgrStatus: MgrApprovalStatus.not_required,
      itDecidedAt: start,
      isClientDirect: true,
      note: "Client-provided device — direct assign",
      createdAt: start,
    });
    assignedPairs.push([r, cd, empI]);
  }

  // ── 5i. Under-repair request (for audit) ────────────────────────────────
  const empRepair = nextActiveEmployee();
  const repairStart = past(20);
  const rRepair = await makeRequest(empRepair, "Laptop", {
    status: RequestStatus.assigned,
    priority: RequestPriority.high,
    reqFrom: repairStart,
    reqTo: future(30),
    assignedItem: underRepairItem,
    assignedFrom: repairStart,
    assignedTo: future(30),
    requiresMgr: true,
    mgrStatus: MgrApprovalStatus.approved,
    managerId: empRepair.managerId,
    mgrDecidedAt: addDays(repairStart, -1),
    itDecidedAt: repairStart,
    createdAt: addDays(repairStart, -4),
  });
  await tx.item.update({
    where: { id: underRepairItem.id },
    data: { currentOwnerId: empRepair.id },
  });
  underRepairItem.currentOwnerId = empRepair.id;
  assignedPairs.push([rRepair, underRepairItem, empRepair]);

  // ── 5j. Future / waitlisted ──────────────────────────────────────────────
  const empWait = nextActiveEmployee();
  await makeRequest(empWait, "Laptop", {
    status: RequestStatus.pending_it_approval,
    priority: RequestPriority.high,
    reqFrom: future(15),
    reqTo: future(45),
    requiresMgr: true,
    mgrStatus: MgrApprovalStatus.approved,
    managerId: empWait.managerId,
    mgrDecidedAt: past(1),
    itDecidedBy: "none",
    createdAt: past(2),
    note: "Urgent: needed for project kick-off in 2 weeks",
  });

  // ═══════════════════════════════════════════════════════════════════════
  // 6. DEVICE LOG — assigned / completed events
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding assignment log events…");

  for (const [r, item] of completedPairs) {
    await logEvent({
      itemId: item.id,
      eventType: "assigned",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: r.id,
      fromValue: "available",
      toValue: "assigned",
      note: `Assigned to employee for period ending ${r.assignedTo ? r.assignedTo.toISOString().slice(0, 10) : "N/A"}`,
      isMilestone: true,
      occurredAt: r.assignedFrom ?? r.createdAt,
    });
    await logEvent({
      itemId: item.id,
      eventType: "assignment_completed",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: r.id,
      fromValue: "assigned",
      toValue: r.completedNextStatus ?? null,
      note: "Return processed, device status updated",
      isMilestone: true,
      occurredAt: r.completedAt ?? now(),
    });
  }

  for (const [r, item, emp] of assignedPairs) {
    const ev = r.isClientDirect ? "client_assigned" : "assigned";
    await logEvent({
      itemId: item.id,
      eventType: ev,
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: r.id,
      fromValue: "available",
      toValue: "assigned",
      note: `Assigned to ${emp.name}`,
      isMilestone: true,
      occurredAt: r.assignedFrom ?? r.createdAt,
    });
    if (r.isWfh && r.shipInitiatedAt) {
      await logEvent({
        itemId: item.id,
        eventType: "ship_outbound_initiated",
        actorId: itAdmin.id,
        actorRole: ActorRole.it_admin,
        requestId: r.id,
        note: "Outbound shipping initiated",
        metadata: { tracking_url: r.shipTrackingUrl },
        isMilestone: false,
        occurredAt: r.shipInitiatedAt,
      });
    }
    if (r.isWfh && r.shipCompletedAt) {
      await logEvent({
        itemId: item.id,
        eventType: "ship_outbound_completed",
        actorId: itAdmin.id,
        actorRole: ActorRole.it_admin,
        requestId: r.id,
        note: "Outbound delivery confirmed",
        isMilestone: true,
        occurredAt: r.shipCompletedAt,
      });
    }
    // NOTE: the original Python script guarded the "return ship initiated" log
    // on `r.get("return_init")` — a key that was never actually set on the
    // request dict (only "return_initiated_at" was). That means this event
    // never fired in the original script. Preserved for parity; if you want
    // this event to fire, guard on `r.returnInitiatedAt` instead.
  }

  // Special: under_repair log entry
  await logEvent({
    itemId: underRepairItem.id,
    eventType: "status_changed",
    actorId: itAdmin.id,
    actorRole: ActorRole.it_admin,
    requestId: rRepair.id,
    fromValue: "assigned",
    toValue: "under_repair",
    note: "Device sent to repair centre — keyboard failure",
    isMilestone: true,
    occurredAt: past(5),
  });

  // Lost device log
  await logEvent({
    itemId: lostItem.id,
    eventType: "marked_lost",
    actorId: itAdmin.id,
    actorRole: ActorRole.it_admin,
    fromValue: "assigned",
    toValue: "lost",
    note: "Employee confirmed device cannot be located after office move",
    isMilestone: true,
    occurredAt: past(12),
  });

  // Retired device log
  await logEvent({
    itemId: retiredItem.id,
    eventType: "retired",
    actorId: itAdmin.id,
    actorRole: ActorRole.it_admin,
    fromValue: "available",
    toValue: "retired",
    note: "Device exceeded 4-year lifecycle policy — retired from inventory",
    isMilestone: true,
    occurredAt: past(30),
  });

  // ═══════════════════════════════════════════════════════════════════════
  // 7. EXTENSION REQUESTS
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding extension requests…");
  const extensions: ExtensionRequest[] = [];

  // Approved extension (moves assigned_to forward)
  if (assignedPairs.length >= 1) {
    const [rExtBase, itemExt, empExt] = at(assignedPairs, 0, "assignedPairs");
    const extOldTo = rExtBase.assignedTo;
    const extNewTo = extOldTo ? addDays(extOldTo, 14) : future(30);
    const extDecided = past(3);
    const ext1 = await tx.extensionRequest.create({
      data: {
        id: uid(),
        originalRequestId: rExtBase.id,
        requesterId: empExt.id,
        currentAssignedTo: extOldTo ?? future(20),
        extendedTo: extNewTo,
        status: ExtensionStatus.approved,
        requiresMgrApproval: true,
        managerId: empExt.managerId,
        mgrApprovalStatus: MgrApprovalStatus.approved,
        managerNote: "Approved — project extended",
        managerDecidedAt: subHours(extDecided, 6),
        itDecidedById: itAdmin.id,
        itNote: "No conflicts found for extended range",
        itDecidedAt: extDecided,
        createdAt: addDays(extDecided, -2),
        updatedAt: extDecided,
      },
    });
    extensions.push(ext1);
    // Update the parent request's assigned_to
    await tx.request.update({ where: { id: rExtBase.id }, data: { assignedTo: extNewTo } });
    rExtBase.assignedTo = extNewTo;
    await logEvent({
      itemId: itemExt.id,
      eventType: "extension_requested",
      actorId: empExt.id,
      actorRole: ActorRole.employee,
      requestId: rExtBase.id,
      extensionRequestId: ext1.id,
      note: `Extension requested to ${extNewTo.toISOString().slice(0, 10)}`,
      isMilestone: false,
      occurredAt: ext1.createdAt,
    });
    await logEvent({
      itemId: itemExt.id,
      eventType: "extension_approved",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: rExtBase.id,
      extensionRequestId: ext1.id,
      fromValue: extOldTo ? extOldTo.toISOString().slice(0, 10) : "",
      toValue: extNewTo.toISOString().slice(0, 10),
      note: "Extension approved — assigned_to updated",
      metadata: { extended_by_days: 14 },
      isMilestone: true,
      occurredAt: extDecided,
    });
  }

  // Pending extension
  if (assignedPairs.length > 1) {
    const [rExt2Base, itemExt2, empExt2] = at(assignedPairs, 1, "assignedPairs");
    const ext2CurrentAssignedTo = rExt2Base.assignedTo ?? future(25);
    const ext2 = await tx.extensionRequest.create({
      data: {
        id: uid(),
        originalRequestId: rExt2Base.id,
        requesterId: empExt2.id,
        currentAssignedTo: ext2CurrentAssignedTo,
        extendedTo: addDays(ext2CurrentAssignedTo, 21),
        status: ExtensionStatus.pending,
        requiresMgrApproval: false,
        managerId: null,
        mgrApprovalStatus: MgrApprovalStatus.not_required,
        managerNote: null,
        managerDecidedAt: null,
        itDecidedById: null,
        itNote: null,
        itDecidedAt: null,
        createdAt: past(1),
        updatedAt: past(1),
      },
    });
    extensions.push(ext2);
    await logEvent({
      itemId: itemExt2.id,
      eventType: "extension_requested",
      actorId: empExt2.id,
      actorRole: ActorRole.employee,
      requestId: rExt2Base.id,
      extensionRequestId: ext2.id,
      note: "Extension requested — awaiting IT review",
      isMilestone: false,
      occurredAt: ext2.createdAt,
    });
  }

  // Rejected extension
  if (assignedPairs.length > 2) {
    const [rExt3Base, itemExt3, empExt3] = at(assignedPairs, 2, "assignedPairs");
    const ext3Decided = past(5);
    const ext3CurrentAssignedTo = rExt3Base.assignedTo ?? future(15);
    const ext3 = await tx.extensionRequest.create({
      data: {
        id: uid(),
        originalRequestId: rExt3Base.id,
        requesterId: empExt3.id,
        currentAssignedTo: ext3CurrentAssignedTo,
        extendedTo: addDays(ext3CurrentAssignedTo, 30),
        status: ExtensionStatus.rejected,
        requiresMgrApproval: true,
        managerId: empExt3.managerId,
        mgrApprovalStatus: MgrApprovalStatus.approved,
        managerNote: "Approved by manager",
        managerDecidedAt: subHours(ext3Decided, 10),
        itDecidedById: itAdmin.id,
        itNote: "Conflict detected: another request scheduled for this device",
        itDecidedAt: ext3Decided,
        createdAt: addDays(ext3Decided, -3),
        updatedAt: ext3Decided,
      },
    });
    extensions.push(ext3);
    await logEvent({
      itemId: itemExt3.id,
      eventType: "extension_rejected",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: rExt3Base.id,
      extensionRequestId: ext3.id,
      note: "Extension rejected — date conflict with another booking",
      isMilestone: false,
      occurredAt: ext3Decided,
    });
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 8. SUPPORT REQUESTS
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding support requests…");
  const supportRequests: SupportRequest[] = [];

  interface MakeSupportOpts {
    type: SupportType;
    description: string;
    status: SupportStatus;
    resolution?: SupportResolution | null;
    itNote?: string | null;
    swappedTo?: Item | null;
    filedDaysAgo?: number;
    resolvedDaysAgo?: number | null;
    autoClosed?: boolean;
  }

  async function makeSupport(
    item: Item,
    requester: User,
    request: Request | null,
    opts: MakeSupportOpts
  ): Promise<SupportRequest> {
    const filedDaysAgo = opts.filedDaysAgo ?? 5;
    const filed = past(filedDaysAgo);
    const resolvedAt = opts.resolvedDaysAgo != null ? past(opts.resolvedDaysAgo) : null;
    const s = await tx.supportRequest.create({
      data: {
        id: uid(),
        itemId: item.id,
        requesterId: requester.id,
        requestId: request ? request.id : null,
        type: opts.type,
        description: opts.description,
        status: opts.status,
        resolution: opts.resolution ?? null,
        itNote: opts.itNote ?? null,
        swappedToItemId: opts.swappedTo ? opts.swappedTo.id : null,
        filedAt: filed,
        resolvedById: resolvedAt ? itAdmin.id : null,
        resolvedAt,
        autoClosed: opts.autoClosed ?? false,
        createdAt: filed,
        updatedAt: resolvedAt ?? filed,
      },
    });
    supportRequests.push(s);
    return s;
  }

  // Open support tickets
  if (assignedPairs.length > 0) {
    const [r1, item1, emp1] = at(assignedPairs, 0, "assignedPairs");
    const sOpenDamage = await makeSupport(item1, emp1, r1, {
      type: SupportType.damage,
      description: pick(SUPPORT_DESCRIPTIONS_DAMAGE),
      status: SupportStatus.open,
      filedDaysAgo: 2,
    });
    await logEvent({
      itemId: item1.id,
      eventType: "support_opened",
      actorId: emp1.id,
      actorRole: ActorRole.employee,
      requestId: r1.id,
      supportRequestId: sOpenDamage.id,
      note: sOpenDamage.description,
      isMilestone: true,
      occurredAt: sOpenDamage.filedAt,
    });
  }

  if (assignedPairs.length > 1) {
    const [r2, item2, emp2] = at(assignedPairs, 1, "assignedPairs");
    const sOpenUpdate = await makeSupport(item2, emp2, r2, {
      type: SupportType.update,
      description: pick(SUPPORT_DESCRIPTIONS_UPDATE),
      status: SupportStatus.in_progress,
      filedDaysAgo: 4,
    });
    await logEvent({
      itemId: item2.id,
      eventType: "support_opened",
      actorId: emp2.id,
      actorRole: ActorRole.employee,
      requestId: r2.id,
      supportRequestId: sOpenUpdate.id,
      note: sOpenUpdate.description,
      isMilestone: true,
      occurredAt: sOpenUpdate.filedAt,
    });
  }

  // Resolved support tickets
  if (assignedPairs.length > 2) {
    const [r3, item3, emp3] = at(assignedPairs, 2, "assignedPairs");
    const sResolvedUpdate = await makeSupport(item3, emp3, r3, {
      type: SupportType.update,
      description: pick(SUPPORT_DESCRIPTIONS_UPDATE),
      status: SupportStatus.resolved,
      resolution: SupportResolution.remote_resolved,
      itNote: "Remote session completed, all software updated successfully",
      filedDaysAgo: 15,
      resolvedDaysAgo: 12,
    });
    await logEvent({
      itemId: item3.id,
      eventType: "support_opened",
      actorId: emp3.id,
      actorRole: ActorRole.employee,
      requestId: r3.id,
      supportRequestId: sResolvedUpdate.id,
      note: sResolvedUpdate.description,
      isMilestone: true,
      occurredAt: sResolvedUpdate.filedAt,
    });
    await logEvent({
      itemId: item3.id,
      eventType: "support_resolved",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: r3.id,
      supportRequestId: sResolvedUpdate.id,
      note: "Software update completed via remote session",
      isMilestone: true,
      occurredAt: sResolvedUpdate.resolvedAt,
    });
  }

  if (assignedPairs.length > 3) {
    const [r4, item4, emp4] = at(assignedPairs, 3, "assignedPairs");
    const sResolvedRepair = await makeSupport(item4, emp4, r4, {
      type: SupportType.damage,
      description: pick(SUPPORT_DESCRIPTIONS_DAMAGE),
      status: SupportStatus.resolved,
      resolution: SupportResolution.repaired_in_place,
      itNote: "Keyboard replacement completed in-house. Device returned to user.",
      filedDaysAgo: 20,
      resolvedDaysAgo: 10,
    });
    await logEvent({
      itemId: item4.id,
      eventType: "support_opened",
      actorId: emp4.id,
      actorRole: ActorRole.employee,
      requestId: r4.id,
      supportRequestId: sResolvedRepair.id,
      note: sResolvedRepair.description,
      isMilestone: true,
      occurredAt: sResolvedRepair.filedAt,
    });
    await logEvent({
      itemId: item4.id,
      eventType: "status_changed",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: r4.id,
      supportRequestId: sResolvedRepair.id,
      fromValue: "assigned",
      toValue: "under_repair",
      note: "Device collected for in-place repair",
      isMilestone: true,
      occurredAt: past(18),
    });
    await logEvent({
      itemId: item4.id,
      eventType: "status_changed",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: r4.id,
      supportRequestId: sResolvedRepair.id,
      fromValue: "under_repair",
      toValue: "assigned",
      note: "Repair completed — returned to employee",
      isMilestone: true,
      occurredAt: past(10),
    });
    await logEvent({
      itemId: item4.id,
      eventType: "support_resolved",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      requestId: r4.id,
      supportRequestId: sResolvedRepair.id,
      note: "Keyboard replaced successfully",
      isMilestone: true,
      occurredAt: sResolvedRepair.resolvedAt,
    });
  }

  // Support on under_repair device
  const sUnderRepair = await makeSupport(underRepairItem, empRepair, rRepair, {
    type: SupportType.damage,
    description: "Keyboard intermittently fails — keys 5, 6, Y, U not registering",
    status: SupportStatus.in_progress,
    filedDaysAgo: 5,
  });
  await logEvent({
    itemId: underRepairItem.id,
    eventType: "support_opened",
    actorId: empRepair.id,
    actorRole: ActorRole.employee,
    requestId: rRepair.id,
    supportRequestId: sUnderRepair.id,
    note: sUnderRepair.description,
    isMilestone: true,
    occurredAt: sUnderRepair.filedAt,
  });

  // Support on lost device
  const sLost = await makeSupport(lostItem, at(activeEmployees, 0, "activeEmployees"), null, {
    type: SupportType.lost,
    description: pick(SUPPORT_DESCRIPTIONS_LOST),
    status: SupportStatus.resolved,
    resolution: SupportResolution.marked_lost,
    itNote: "Loss confirmed. Device flagged as lost. IT to decide next status.",
    filedDaysAgo: 14,
    resolvedDaysAgo: 12,
  });
  await logEvent({
    itemId: lostItem.id,
    eventType: "support_opened",
    actorId: at(activeEmployees, 0, "activeEmployees").id,
    actorRole: ActorRole.employee,
    supportRequestId: sLost.id,
    note: sLost.description,
    isMilestone: true,
    occurredAt: sLost.filedAt,
  });
  await logEvent({
    itemId: lostItem.id,
    eventType: "support_resolved",
    actorId: itAdmin.id,
    actorRole: ActorRole.it_admin,
    supportRequestId: sLost.id,
    note: "Loss confirmed by IT",
    isMilestone: true,
    occurredAt: sLost.resolvedAt,
  });

  // Auto-closed support tickets (from completed requests)
  if (completedPairs.length > 0) {
    const [rComp, itemComp] = at(completedPairs, 0, "completedPairs");
    const sAuto = await makeSupport(itemComp, at(activeEmployees, 0, "activeEmployees"), rComp, {
      type: SupportType.update,
      description: "Pending OS update — 3 weeks overdue",
      status: SupportStatus.resolved,
      resolution: SupportResolution.remote_resolved,
      itNote: null,
      autoClosed: true,
      filedDaysAgo: 90,
      resolvedDaysAgo: 80,
    });
    await logEvent({
      itemId: itemComp.id,
      eventType: "support_auto_closed",
      actorId: null,
      actorRole: ActorRole.system,
      requestId: rComp.id,
      supportRequestId: sAuto.id,
      note: "Auto-closed: parent request completed",
      isMilestone: false,
      occurredAt: sAuto.resolvedAt,
    });
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 9. HANDOVER REQUESTS
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding handover requests…");
  const handovers: HandoverRequest[] = [];

  interface MakeHandoverOpts {
    status: HandoverStatus;
    durationHours?: number;
    note?: string | null;
    requestedAt?: Date | null;
    decidedAt?: Date | null;
    completedAt?: Date | null;
  }

  async function makeHandover(
    item: Item,
    owner: User,
    borrower: User,
    opts: MakeHandoverOpts
  ): Promise<HandoverRequest> {
    const ra = opts.requestedAt ?? past(randomInt(1, 10));
    const h = await tx.handoverRequest.create({
      data: {
        id: uid(),
        itemId: item.id,
        ownerId: owner.id,
        borrowerId: borrower.id,
        requestedDurationHours: opts.durationHours ?? randomInt(1, 8),
        status: opts.status,
        requestedAt: ra,
        decidedAt: opts.decidedAt ?? null,
        completedAt: opts.completedAt ?? null,
        note: opts.note ?? pick(HANDOVER_NOTES),
        createdAt: ra,
        updatedAt: opts.completedAt ?? opts.decidedAt ?? ra,
      },
    });
    handovers.push(h);
    return h;
  }

  // Active (accepted) handover
  if (assignedPairs.length >= 5) {
    const [, itemH1, empH1] = at(assignedPairs, 4, "assignedPairs");
    const borrowerH1 = nextActiveEmployee();
    const h1Req = past(3);
    const h1Dec = addHours(past(3), 1);
    const h1 = await makeHandover(itemH1, empH1, borrowerH1, {
      status: HandoverStatus.accepted,
      durationHours: 4,
      note: "Borrowing for client demo this afternoon",
      requestedAt: h1Req,
      decidedAt: h1Dec,
    });
    await logEvent({
      itemId: itemH1.id,
      eventType: "handover_requested",
      actorId: borrowerH1.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h1.id,
      note: `${borrowerH1.name} requested handover`,
      isMilestone: false,
      occurredAt: h1Req,
    });
    await logEvent({
      itemId: itemH1.id,
      eventType: "handover_accepted",
      actorId: empH1.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h1.id,
      note: `Handover accepted for ${h1.requestedDurationHours} hours`,
      isMilestone: true,
      occurredAt: h1Dec,
    });
  }

  // Completed handover
  if (assignedPairs.length >= 6) {
    const [, itemH2, empH2] = at(assignedPairs, 5, "assignedPairs");
    const borrowerH2 = nextActiveEmployee();
    const h2Req = past(8);
    const h2Dec = addHours(past(8), 0.5);
    const h2Comp = addHours(past(7), 4);
    const h2 = await makeHandover(itemH2, empH2, borrowerH2, {
      status: HandoverStatus.completed,
      durationHours: 3,
      note: "Needed for afternoon workshop",
      requestedAt: h2Req,
      decidedAt: h2Dec,
      completedAt: h2Comp,
    });
    await logEvent({
      itemId: itemH2.id,
      eventType: "handover_requested",
      actorId: borrowerH2.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h2.id,
      note: `${borrowerH2.name} requested handover`,
      isMilestone: false,
      occurredAt: h2Req,
    });
    await logEvent({
      itemId: itemH2.id,
      eventType: "handover_accepted",
      actorId: empH2.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h2.id,
      note: "Handover accepted",
      isMilestone: true,
      occurredAt: h2Dec,
    });
    await logEvent({
      itemId: itemH2.id,
      eventType: "handover_completed",
      actorId: empH2.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h2.id,
      note: "Device returned to owner",
      isMilestone: true,
      occurredAt: h2Comp,
    });
  }

  // Rejected handover
  if (assignedPairs.length >= 7) {
    const [, itemH3, empH3] = at(assignedPairs, 6, "assignedPairs");
    const borrowerH3 = nextActiveEmployee();
    const h3Req = past(4);
    const h3Dec = addHours(past(4), 2);
    const h3 = await makeHandover(itemH3, empH3, borrowerH3, {
      status: HandoverStatus.rejected,
      durationHours: 2,
      note: null,
      requestedAt: h3Req,
      decidedAt: h3Dec,
    });
    await logEvent({
      itemId: itemH3.id,
      eventType: "handover_requested",
      actorId: borrowerH3.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h3.id,
      note: `${borrowerH3.name} requested handover`,
      isMilestone: false,
      occurredAt: h3Req,
    });
    await logEvent({
      itemId: itemH3.id,
      eventType: "handover_rejected",
      actorId: empH3.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h3.id,
      note: "Owner declined — device needed for own work",
      isMilestone: false,
      occurredAt: h3Dec,
    });
  }

  // Cancelled handover (borrower withdrew)
  if (assignedPairs.length >= 8) {
    const [, itemH4, empH4] = at(assignedPairs, 7, "assignedPairs");
    const borrowerH4 = nextActiveEmployee();
    const h4Req = past(2);
    const h4 = await makeHandover(itemH4, empH4, borrowerH4, {
      status: HandoverStatus.cancelled,
      durationHours: 1,
      note: "No longer needed",
      requestedAt: h4Req,
    });
    await logEvent({
      itemId: itemH4.id,
      eventType: "handover_requested",
      actorId: borrowerH4.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h4.id,
      note: `${borrowerH4.name} requested handover`,
      isMilestone: false,
      occurredAt: h4Req,
    });
    await logEvent({
      itemId: itemH4.id,
      eventType: "handover_cancelled",
      actorId: borrowerH4.id,
      actorRole: ActorRole.employee,
      handoverRequestId: h4.id,
      note: "Borrower cancelled the request",
      isMilestone: false,
      occurredAt: addHours(h4Req, 1),
    });
  }

  // Multiple pending handovers on same device (first-accept-wins scenario)
  if (assignedPairs.length >= 9) {
    const [, itemH5, empH5] = at(assignedPairs, 8, "assignedPairs");
    for (let i = 0; i < 2; i++) {
      const b = at(activeEmployees, (empIdx + i) % activeEmployees.length, "activeEmployees");
      // NOTE: original Python computed `hours(i+1).seconds // 3600`, which for
      // i in {0,1} simplifies to exactly `i+1` — replicated directly as past(i+1).
      const hPending = await makeHandover(itemH5, empH5, b, {
        status: HandoverStatus.requested,
        durationHours: randomInt(1, 3),
        note: pick(HANDOVER_NOTES),
        requestedAt: past(i + 1),
      });
      await logEvent({
        itemId: itemH5.id,
        eventType: "handover_requested",
        actorId: b.id,
        actorRole: ActorRole.employee,
        handoverRequestId: hPending.id,
        note: `${b.name} requested handover (simultaneous)`,
        isMilestone: false,
        occurredAt: hPending.requestedAt,
      });
    }
    empIdx += 2;
  }

  // ═══════════════════════════════════════════════════════════════════════
  // 10. EXTRA DEVICE LOG — maintenance, edits, status changes
  // ═══════════════════════════════════════════════════════════════════════
  console.log("Seeding extra device log events…");

  // Maintenance device
  await logEvent({
    itemId: maintenanceItem.id,
    eventType: "status_changed",
    actorId: itAdmin.id,
    actorRole: ActorRole.it_admin,
    fromValue: "available",
    toValue: "maintenance",
    note: "Scheduled maintenance: firmware update batch — estimated 3 days",
    isMilestone: false,
    occurredAt: past(1),
  });

  // Device edit
  const firstLaptop = at(laptops, 0, "laptops");
  await logEvent({
    itemId: firstLaptop.id,
    eventType: "device_edited",
    actorId: itAdmin.id,
    actorRole: ActorRole.it_admin,
    note: "Serial number corrected after physical audit",
    metadata: { field: "serial_no", old: "SN-OLD-001", new: firstLaptop.serialNo },
    isMilestone: false,
    occurredAt: past(7),
  });

  // Client device assigned log
  for (const cd of clientDevices) {
    await logEvent({
      itemId: cd.id,
      eventType: "client_assigned",
      actorId: itAdmin.id,
      actorRole: ActorRole.it_admin,
      fromValue: "available",
      toValue: "assigned",
      note: `Client device from ${cd.clientName} directly assigned`,
      isMilestone: true,
      occurredAt: past(randomInt(10, 60)),
    });
  }

  // ═══════════════════════════════════════════════════════════════════════
  // SUMMARY
  // ═══════════════════════════════════════════════════════════════════════
  console.log("\n✓ Seed complete. Summary:");
  console.log(
    `  Users:             ${String(allUsers.length).padStart(4)}  (${itAdmins.length} IT admins, ${managers.length} managers, ${employees.length} employees)`
  );
  console.log(`  Item categories:   ${String(Object.keys(categories).length).padStart(4)}`);
  console.log(`  Devices (items):   ${String(items.length).padStart(4)}  (incl. ${clientDevices.length} client-owned)`);
  console.log(`  Requests:          ${String(requests.length).padStart(4)}`);
  console.log(`  Extension reqs:    ${String(extensions.length).padStart(4)}`);
  console.log(`  Support reqs:      ${String(supportRequests.length).padStart(4)}`);
  console.log(`  Handover reqs:     ${String(handovers.length).padStart(4)}`);
  console.log(`  Device log rows:   see DB — one per event`);

  // Referenced for parity with the original script's imports/definitions but
  // not otherwise used in the seeding logic itself.
  void DEVICE_ADJECTIVES;
  void keyboards;
  void mice;
  void headsets;
  void chargers;
  void tablets;
  void docks;
  void pendingItReqs;
  void pendingMgrReqs;
  void plainRequested;
}

// ═══════════════════════════════════════════════════════════════════════════
// Entry point
// ═══════════════════════════════════════════════════════════════════════════
async function main() {
  console.log("Connecting to database…");
  await prisma.$transaction(
    async (tx) => {
      await runSeed(tx);
    },
    { maxWait: 30_000, timeout: 600_000 }
  );
}

main()
  .then(async () => {
    await prisma.$disconnect();
  })
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    process.exit(1);
  });
