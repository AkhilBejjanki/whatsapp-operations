export type Me = {
  id: number;
  email: string;
  name: string;
  role: string;
  organization: { id: number; name: string };
  mock_mode: boolean;
};

export type WhatsAppAccount = {
  id: number;
  waba_id: string;
  phone_number_id: string;
  display_phone_number: string | null;
  verified_name: string | null;
  quality_rating: string | null;
  messaging_limit: string | null;
  webhook_subscribed: boolean;
  updated_at: string;
};

export type AccountResponse = {
  account: WhatsAppAccount | null;
  webhook_path: string;
  verify_token_configured: boolean;
  app_secret_configured: boolean;
  mock_mode: boolean;
};

export type TemplateComponent = {
  type: string;
  format?: string;
  text?: string;
  buttons?: { type: string; text: string; url?: string; phone_number?: string }[];
};

export type TemplateVariable = {
  key: string;
  component: "header" | "body" | "button";
  name: string;
  label: string;
  index?: number;
};

export type Template = {
  id: number;
  meta_template_id: string | null;
  name: string;
  language: string;
  category: string | null;
  status: string;
  parameter_format: string;
  components: TemplateComponent[];
  rejected_reason: string | null;
  variables: TemplateVariable[];
  header_media: string | null;
  updated_at: string;
};

export type UploadResult = {
  id: number;
  filename: string;
  columns: string[];
  row_count: number;
  sample_rows: Record<string, string>[];
  suggested: { phone: string | null; name: string | null };
};

export type MessageStatus =
  | "invalid" | "queued" | "accepted" | "sent" | "delivered" | "read" | "failed" | "cancelled";

export type Campaign = {
  id: number;
  name: string;
  status: "draft" | "queued" | "sending" | "paused" | "completed" | "cancelled";
  template: { id: number; name: string; language: string; category: string | null } | null;
  default_country: string;
  total_rows: number;
  duplicate_count: number;
  counts: Record<MessageStatus, number>;
  total: number;
  sendable: number;
  processed: number;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  errors?: { code: number | null; title: string | null; count: number }[];
};

export type MessageRow = {
  id: number;
  row_index: number;
  contact_name: string | null;
  raw_phone: string | null;
  phone: string | null;
  status: MessageStatus;
  error_code: number | null;
  error_title: string | null;
  error_detail: string | null;
  variables: Record<string, string>;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
};

export type MessagePage = { total: number; page: number; page_size: number; items: MessageRow[] };

export type Mapping = { type: "column" | "static"; value: string };
