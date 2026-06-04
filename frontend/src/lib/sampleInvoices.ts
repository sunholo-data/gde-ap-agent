/**
 * Curated fixture invoices shipped in /public/demo-invoices/. Surfaced by the
 * SampleInvoicePicker on the ap-orchestrator empty-state so judges can run the
 * full pipeline without finding their own file. The three picks are chosen to
 * showcase format range:
 *   - DOCX (clean German invoice)
 *   - ODT  (less common — proves the parser is format-agnostic)
 *   - EML  (email-with-attached-PDF — full intake-flow showcase)
 */
export interface SampleInvoice {
  /** Filename inside /public/demo-invoices/. */
  filename: string;
  /** Vendor display name. */
  vendor: string;
  /** One-line "what makes this interesting" caption. */
  caption: string;
  /** MIME type sent in the synthetic File. */
  mime: string;
  /** Pre-formatted amount string for the card. */
  amount: string;
  /** Country for the vendor flag chip. */
  country: string;
}

export const SAMPLE_INVOICES: readonly SampleInvoice[] = [
  {
    filename: "acme-gmbh-invoice-2026-042.docx",
    vendor: "Acme GmbH",
    caption: "Clean DOCX invoice, German VAT, single line item",
    mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    amount: "€4,250.00",
    country: "DE",
  },
  {
    filename: "apex-consulting-invoice-2026-103.odt",
    vendor: "Apex Consulting",
    caption: "ODT invoice (uncommon format) — proves format-agnostic parsing",
    mime: "application/vnd.oasis.opendocument.text",
    amount: "£8,900.00",
    country: "GB",
  },
  {
    filename: "nordic-parts-invoice-email-2026.eml",
    vendor: "Nordic Parts AB",
    caption: "Email-with-attachment intake (.eml) — full receive-to-post flow",
    mime: "message/rfc822",
    amount: "kr 32,100",
    country: "SE",
  },
] as const;
