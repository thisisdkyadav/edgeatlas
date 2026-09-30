export type Route = {
  route: "local" | "cloud" | "tombstone";
  reason: string;
  flags: string[];
  priority: number;
};
export type Memory = {
  id: string;
  title: string;
  body: string;
  category: string;
  site: string;
  tags: string[];
  visibility: "local" | "team";
  priority: string;
  source: string;
  ttl_days: number;
  version: number;
  cloud_revision: number;
  created_at: number;
  updated_at: number;
  deleted: boolean;
  origin_device: string;
  routing: Route;
  sync_state: string;
  score?: number;
  queue?: { attempts: number; error: string; retry_at: number };
  conflict?: { remote: Memory; detected_at: number } | null;
};
export type Status = {
  device_id: string;
  device_name: string;
  engine: string;
  model: string;
  dimensions: number;
  online: boolean;
  metered: boolean;
  auto_sync: boolean;
  metered_min_priority: number;
  connection: string;
  cloud_url: string;
  last_sync: number | null;
  last_search_ms: number | null;
  cursor: number;
  total: number;
  local: number;
  shared: number;
  queued: number;
  conflicts: number;
  archived: number;
  storage_bytes: number;
};
export type Event = {
  seq: number;
  kind: string;
  message: string;
  record_id: string | null;
  time: number;
};
export type Search = {
  results: Memory[];
  duration_ms: number;
  mode: string;
  engine: string;
  answer_method: string;
  answer: { id: string; title: string; excerpt: string; source: string }[];
};
export type History = {
  seq: number;
  action: string;
  time: number;
  document: Memory;
};
export type Page =
  "overview" | "library" | "search" | "sync" | "activity" | "settings";
