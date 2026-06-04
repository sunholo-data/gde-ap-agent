/**
 * Vendor master + PO + prior-invoice data — single frontend source of truth.
 *
 * Lifted from the canonical backend fixture at
 * `infrastructure/demo-vendor-master/vendor-master.jsonl`. The backend
 * imports that JSONL into the discovery engine the validator queries;
 * the frontend mirrors a curated subset here so the Vendor Knowledge
 * Graph MCP App, the AP Analytics dashboard, and any UI surface that
 * needs to "know about" the vendor master can pre-populate with real
 * relationships — not an empty graph waiting on the agent.
 *
 * Keep this short enough to hand-maintain (≈10 vendors, ~6 POs, ~8
 * prior invoices). If we ever need the full master, fetch the backend
 * MCP server (`backend/protocols/mcp_servers/vendor_master.py`) instead.
 */

export interface Vendor {
  id: string;
  name: string;
  country: string;
  currency: string;
  category: string;
  /** EUR-equivalent spend cap per invoice. 0 = blocked. */
  spendLimitEur: number;
  status: "active" | "blocked";
  /** Used by KG node ring colour. */
  approved: boolean;
}

export interface PurchaseOrder {
  poNumber: string;
  vendorId: string;
  currency: string;
  totalAmount: number;
  status: "open" | "closed";
}

export interface PriorInvoice {
  invoiceNumber: string;
  vendorId: string;
  currency: string;
  totalAmount: number;
  postedDate: string;
  status: "posted";
}

export const VENDORS: readonly Vendor[] = [
  {
    id: "V-1042",
    name: "Acme GmbH",
    country: "DE",
    currency: "EUR",
    category: "Cloud Services",
    spendLimitEur: 50000,
    status: "active",
    approved: true,
  },
  {
    id: "V-2014",
    name: "TechCorp Ltd",
    country: "GB",
    currency: "GBP",
    category: "Software Licences",
    spendLimitEur: 25000,
    status: "active",
    approved: true,
  },
  {
    id: "V-3077",
    name: "Nordic Parts AB",
    country: "SE",
    currency: "EUR",
    category: "Manufacturing Parts",
    spendLimitEur: 15000,
    status: "active",
    approved: true,
  },
  {
    id: "V-4090",
    name: "Apex Consulting",
    country: "FR",
    currency: "EUR",
    category: "Professional Services",
    spendLimitEur: 75000,
    status: "active",
    approved: true,
  },
  {
    id: "V-9001",
    name: "BlockedCo S.A.",
    country: "ES",
    currency: "EUR",
    category: "Unknown",
    spendLimitEur: 0,
    status: "blocked",
    approved: false,
  },
] as const;

export const PURCHASE_ORDERS: readonly PurchaseOrder[] = [
  { poNumber: "PO-2026-0189", vendorId: "V-1042", currency: "EUR", totalAmount: 9000, status: "open" },
  { poNumber: "PO-2026-0204", vendorId: "V-2014", currency: "GBP", totalAmount: 18500, status: "open" },
  { poNumber: "PO-2026-0311", vendorId: "V-4090", currency: "EUR", totalAmount: 45000, status: "open" },
] as const;

export const PRIOR_INVOICES: readonly PriorInvoice[] = [
  { invoiceNumber: "INV-2025-119", vendorId: "V-1042", currency: "EUR", totalAmount: 8500, postedDate: "2025-11-15", status: "posted" },
  { invoiceNumber: "INV-2025-187", vendorId: "V-1042", currency: "EUR", totalAmount: 9000, postedDate: "2026-02-20", status: "posted" },
  { invoiceNumber: "INV-2026-018", vendorId: "V-2014", currency: "GBP", totalAmount: 6150, postedDate: "2026-03-10", status: "posted" },
] as const;

export function vendorByName(name: string | null | undefined): Vendor | null {
  if (!name) return null;
  const lc = name.toLowerCase().trim();
  return VENDORS.find((v) => v.name.toLowerCase() === lc) ?? null;
}

export function totalSpendForVendor(vendorId: string): number {
  return PRIOR_INVOICES.filter((i) => i.vendorId === vendorId).reduce(
    (sum, i) => sum + i.totalAmount,
    0,
  );
}
