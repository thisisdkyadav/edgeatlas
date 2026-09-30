import { useEffect, useState, useCallback, type FormEvent } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  Cloud,
  CloudOff,
  Copy,
  Cpu,
  Database,
  FileText,
  GitMerge,
  HardDrive,
  LayoutDashboard,
  Lock,
  MapPin,
  Menu,
  Plus,
  Radio,
  RefreshCw,
  Search as SearchIcon,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Triangle,
  Wifi,
  WifiOff,
  X,
  Archive,
  RotateCcw,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { api, download } from "./api";
import type { Memory, Status, Page, Event, Search, History } from "./types";

const date = (t: number) =>
  new Date(t * 1000).toLocaleString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const ago = (t: number | null) => {
  if (!t) return "Never";
  const sec = Math.max(0, Date.now() / 1000 - t);
  return sec < 60
    ? "Just now"
    : sec < 3600
      ? Math.floor(sec / 60) + "m ago"
      : sec < 86400
        ? Math.floor(sec / 3600) + "h ago"
        : Math.floor(sec / 86400) + "d ago";
};
const categories = ["Observation", "Procedure", "Incident", "Reference"];
const nav = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "library", label: "Memory library", icon: BookOpen },
  { id: "search", label: "Search & recall", icon: SearchIcon },
  { id: "sync", label: "Sync center", icon: RefreshCw },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "settings", label: "Device & policy", icon: Settings2 },
] as const;
const names: Record<Page, string> = {
  overview: "Workspace overview",
  library: "Memory library",
  search: "Search & recall",
  sync: "Synchronization",
  activity: "Device activity",
  settings: "Device & policy",
};

function Badge({ memory }: { memory: Memory }) {
  const state = memory.sync_state;
  return (
    <span
      className={
        "badge " +
        (state === "conflict"
          ? "amber"
          : memory.routing?.route === "local"
            ? "neutral"
            : state === "synced"
              ? "green"
              : "blue")
      }
    >
      {state === "conflict" ? (
        <GitMerge size={12} />
      ) : memory.routing?.route === "local" ? (
        <Lock size={12} />
      ) : state === "synced" ? (
        <CheckCheck size={12} />
      ) : (
        <Clock size={12} />
      )}{" "}
      {state === "conflict"
        ? "Needs review"
        : memory.routing?.route === "local"
          ? "Device only"
          : state === "synced"
            ? "Synced"
            : state === "retry"
              ? "Retry queued"
              : "Awaiting sync"}
    </span>
  );
}
function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty">
      <Database size={32} />
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
function MemoryCard({
  memory,
  onOpen,
}: {
  memory: Memory;
  onOpen: () => void;
}) {
  return (
    <button className="memory-card" onClick={onOpen}>
      <div className="card-top">
        <span className={"category-dot " + memory.category.toLowerCase()}>
          <FileText size={17} />
        </span>
        <Badge memory={memory} />
      </div>
      <div className="eyebrow">{memory.category}</div>
      <h3>{memory.title}</h3>
      <p>{memory.body}</p>
      <div className="tags">
        {memory.tags.slice(0, 3).map((t) => (
          <span key={t}>{t}</span>
        ))}
      </div>
      <div className="card-bottom">
        <span>
          <MapPin size={13} />
          {memory.site}
        </span>
        <span>{ago(memory.updated_at)}</span>
      </div>
    </button>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [status, setStatus] = useState<Status | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [selected, setSelected] = useState<Memory | null>(null);
  const [editing, setEditing] = useState<Memory | null | undefined>(undefined);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [token, setToken] = useState("");
  const [needsToken, setNeedsToken] = useState(false);
  const [cloudEdit, setCloudEdit] = useState<Memory | null>(null);
  const refresh = useCallback(async () => {
    try {
      const [s, m, e] = await Promise.all([
        api<Status>("/status"),
        api<Memory[]>("/memories?include_deleted=true"),
        api<Event[]>("/activity"),
      ]);
      setStatus(s);
      setMemories(m);
      setEvents(e);
      setNeedsToken(false);
    } catch (e) {
      const message = (e as Error).message;
      if (message.includes("access token")) setNeedsToken(true);
      else setError(message);
    }
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 8000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => setNotice(""), 6000);
      return () => clearTimeout(t);
    }
  }, [notice]);
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelected(null);
        setEditing(undefined);
        setCloudEdit(null);
        setMobile(false);
      }
    };
    document.addEventListener("keydown", f);
    return () => document.removeEventListener("keydown", f);
  }, []);
  const run = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      setNotice(message);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const sync = () =>
    run(async () => {
      const r = await api<{ status: string; pushed: number; pulled: number }>(
        "/sync",
        "POST",
      );
      if (r.status === "offline")
        throw new Error(
          "Cloud link is disabled. Enable it in Sync center first.",
        );
      if (r.status === "unavailable")
        throw new Error(
          "Cloud is unavailable. Your changes remain queued on this device.",
        );
    }, "Synchronization complete.");
  const go = (next: Page) => {
    setPage(next);
    setMobile(false);
    setError("");
  };
  const active = memories.filter((m) => !m.deleted);
  if (needsToken)
    return (
      <main className="access">
        <Triangle size={42} />
        <h1>Connect to your device</h1>
        <p>Enter the access token configured for this EdgeAtlas device.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sessionStorage.setItem("edgeatlas-token", token);
            refresh();
          }}
        >
          <label>
            Device access token
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
            />
          </label>
          <button className="primary">
            Connect <ArrowRight size={16} />
          </button>
        </form>
      </main>
    );
  return (
    <div className="app">
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <button className="brand" onClick={() => go("overview")}>
          <span className="brandmark">
            <Triangle size={24} />
          </span>
          EdgeAtlas<span className="brand-dot">.</span>
        </button>
        <div className="workspace-label">FIELD INTELLIGENCE</div>
        <div className="workspace">
          <div className="avatar">N</div>
          <div>
            <strong>North station</strong>
            <span>Operations workspace</span>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map((item) => (
            <button
              className={page === item.id ? "active" : ""}
              key={item.id}
              onClick={() => go(item.id)}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {item.id === "sync" && !!status?.queued && <b>{status.queued}</b>}
              {item.id === "library" && <em>{status?.total || 0}</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-assurance">
            <ShieldCheck size={21} />
            <strong>Your memory stays yours.</strong>
            <p>Search locally. Share deliberately.</p>
          </div>
          <div className="device-mini">
            <span
              className={"status-dot " + (!status?.online ? "offline" : "")}
            />
            <div>
              <strong>{status?.device_name || "Connecting…"}</strong>
              <span>
                {status?.online ? "Cloud link enabled" : "Cloud link disabled"}
              </span>
            </div>
            <button aria-label="Device settings" onClick={() => go("settings")}>
              <Settings2 size={16} />
            </button>
          </div>
        </div>
      </aside>
      {mobile && (
        <button
          className="scrim"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <div className="main">
        <header className="topbar">
          <div className="crumb">
            <button
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{names[page]}</strong>
          </div>
          <div className="top-actions">
            <span className="engine-badge">
              <Cpu size={14} />
              Powered by Qdrant Edge
            </span>
            <span className="user-avatar">DY</span>
          </div>
        </header>
        <main className="content">
          {error && (
            <div className="error" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {!status ? (
            <div className="loading">
              <RefreshCw className="spin" />
              <h2>Opening your device memory…</h2>
              <p>The local embedding model and index are loading.</p>
            </div>
          ) : (
            <>
              {page === "overview" && (
                <>
                  <div className="page-heading">
                    <div>
                      <div className="eyebrow">THE FIELD, REMEMBERED.</div>
                      <h1>
                        Good work starts
                        <br />
                        with good memory<span>.</span>
                      </h1>
                      <p>
                        Your team's knowledge, ready wherever the work takes
                        you.
                      </p>
                    </div>
                    <button
                      className="primary"
                      onClick={() => setEditing(null)}
                    >
                      <Plus size={17} />
                      Capture memory
                    </button>
                  </div>
                  <div className="stats">
                    <Stat
                      label="Memories on device"
                      value={status.total}
                      icon={Database}
                      detail="Available without internet"
                    />
                    <Stat
                      label="Kept private"
                      value={status.local}
                      icon={ShieldCheck}
                      detail="Never leaves this device"
                    />
                    <Stat
                      label="Shared knowledge"
                      value={status.shared}
                      icon={Cloud}
                      detail="Eligible for team synchronization"
                    />
                    <Stat
                      label="Pending changes"
                      value={status.queued}
                      icon={RefreshCw}
                      detail={
                        status.conflicts
                          ? status.conflicts + " conflicts need review"
                          : "Durably queued on your device"
                      }
                    />
                  </div>
                  <div className="overview-row">
                    <section className="panel network-panel">
                      <div className="section-head">
                        <div>
                          <span className="eyebrow">EDGE → CLOUD → EDGE</span>
                          <h2>A connection is a bonus.</h2>
                          <p>Your memory works either way.</p>
                        </div>
                        <span
                          className={
                            "badge " + (status.online ? "green" : "neutral")
                          }
                        >
                          {status.online ? (
                            <Wifi size={12} />
                          ) : (
                            <WifiOff size={12} />
                          )}{" "}
                          {status.online ? "Link enabled" : "Offline mode"}
                        </span>
                      </div>
                      <Topology status={status} />
                      <div className="network-footer">
                        <span>
                          <span className="status-dot" />
                          Local search always available
                        </span>
                        <button
                          className="text-button"
                          onClick={() => go("sync")}
                        >
                          Manage sync
                          <ArrowRight size={14} />
                        </button>
                      </div>
                    </section>
                    <section className="panel recall-panel">
                      <div className="recall-icon">
                        <Sparkles size={24} />
                      </div>
                      <span className="eyebrow">FIND WHAT YOU KNOW</span>
                      <h2>
                        A symptom, not
                        <br />
                        an exact keyword.
                      </h2>
                      <p>
                        Recall relevant field notes with meaning and keyword
                        search, entirely on your device.
                      </p>
                      <button
                        className="secondary"
                        onClick={() => go("search")}
                      >
                        Search your memory
                        <ArrowUpRight size={16} />
                      </button>
                      <div className="model-caption">
                        <Cpu size={12} />
                        Local embeddings · 384 dimensions
                      </div>
                    </section>
                  </div>
                  <div className="section-title">
                    <div>
                      <h2>Recently remembered</h2>
                      <p>
                        Observations, procedures, and lessons worth keeping.
                      </p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => go("library")}
                    >
                      View all memories
                      <ArrowRight size={15} />
                    </button>
                  </div>
                  <div className="memory-grid">
                    {active.slice(0, 3).map((m) => (
                      <MemoryCard
                        key={m.id}
                        memory={m}
                        onOpen={() => setSelected(m)}
                      />
                    ))}
                  </div>
                  <div className="overview-bottom">
                    <section className="panel">
                      <div className="section-head">
                        <h2>A little more peace of mind</h2>
                        <Lock size={18} />
                      </div>
                      <p>
                        Device-only memories and notes with detected sensitive
                        details stay local. Every sharing decision has a reason
                        you can inspect.
                      </p>
                      <button
                        className="text-button"
                        onClick={() => go("settings")}
                      >
                        Review routing policy
                        <ArrowRight size={14} />
                      </button>
                    </section>
                    <section className="panel">
                      <div className="section-head">
                        <h2>Latest activity</h2>
                        <button
                          className="text-button"
                          onClick={() => go("activity")}
                        >
                          View log
                          <ArrowUpRight size={14} />
                        </button>
                      </div>
                      {events.slice(0, 3).map((e) => (
                        <div className="compact-event" key={e.seq}>
                          <span className="tiny-dot" />
                          <span>{e.message}</span>
                          <time>{ago(e.time)}</time>
                        </div>
                      ))}
                    </section>
                  </div>
                </>
              )}
              {page === "library" && (
                <Library
                  memories={memories}
                  onOpen={setSelected}
                  onNew={() => setEditing(null)}
                  exportFile={(f) =>
                    run(() => download(f), "Export downloaded.")
                  }
                />
              )}
              {page === "search" && (
                <SearchPage
                  memories={active}
                  onOpen={setSelected}
                  onError={setError}
                />
              )}
              {page === "sync" && (
                <SyncPage
                  status={status}
                  memories={memories}
                  sync={sync}
                  busy={busy}
                  run={run}
                  onOpen={setSelected}
                  cloudEdit={setCloudEdit}
                />
              )}
              {page === "activity" && (
                <>
                  <PageHeading
                    eyebrow="A TRACEABLE WORKSPACE"
                    title="Nothing lost in the handover."
                    subtitle="Memory changes, policy decisions, and synchronization attempts."
                  />
                  <div className="panel activity-list">
                    {events.length ? (
                      events.map((e) => (
                        <div className="activity-row" key={e.seq}>
                          <span className={"event-icon " + e.kind}>
                            {e.kind === "sync" ? (
                              <RefreshCw size={17} />
                            ) : e.kind === "conflict" ? (
                              <GitMerge size={17} />
                            ) : e.kind === "network" ? (
                              <Radio size={17} />
                            ) : (
                              <FileText size={17} />
                            )}
                          </span>
                          <div>
                            <strong>{e.message}</strong>
                            <span>
                              {e.kind}{" "}
                              {e.record_id
                                ? "· " + e.record_id.slice(0, 8)
                                : ""}
                            </span>
                          </div>
                          <time>{date(e.time)}</time>
                        </div>
                      ))
                    ) : (
                      <Empty
                        title="A clean slate"
                        body="Activity will appear as you capture and synchronize memories."
                      />
                    )}
                  </div>
                </>
              )}
              {page === "settings" && (
                <SettingsPage status={status} run={run} busy={busy} />
              )}
              <footer className="footer">
                <span>
                  <Triangle size={13} />
                  EdgeAtlas · Built for the field
                </span>
                <span>Illustrative demo data · Team inrow · PS 03</span>
              </footer>
            </>
          )}
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <Check size={17} />
          {notice}
        </div>
      )}
      {selected && (
        <Inspector
          memory={memories.find((m) => m.id === selected.id) || selected}
          onClose={() => setSelected(null)}
          edit={() => {
            setEditing(memories.find((m) => m.id === selected.id) || selected);
            setSelected(null);
          }}
          run={run}
        />
      )}
      {editing !== undefined && (
        <Editor
          memory={editing}
          onClose={() => setEditing(undefined)}
          save={async (value) => {
            await run(async () => {
              await api(
                "/memories" + (editing ? "/" + editing.id : ""),
                editing ? "PUT" : "POST",
                value,
              );
              setEditing(undefined);
            }, "Memory saved on this device.");
          }}
        />
      )}
      {cloudEdit && (
        <Editor
          memory={cloudEdit}
          controlRoom
          onClose={() => setCloudEdit(null)}
          save={async (value) => {
            await run(async () => {
              await api("/cloud/memories/" + cloudEdit.id, "PUT", {
                ...value,
                visibility: "team",
                expected_version: cloudEdit.cloud_revision,
              });
              setCloudEdit(null);
            }, "Shared memory updated at the control room. Sync to receive it.");
          }}
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
  detail,
}: {
  label: string;
  value: number;
  icon: typeof Database;
  detail: string;
}) {
  return (
    <section className="stat">
      <div>
        <span>{label}</span>
        <Icon size={18} />
      </div>
      <strong>{String(value).padStart(2, "0")}</strong>
      <p>{detail}</p>
    </section>
  );
}
function PageHeading({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading compact">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
function Topology({ status }: { status: Status }) {
  return (
    <div className="topology">
      <div className="topology-node">
        <div className="device-box">
          <Cpu size={30} />
        </div>
        <strong>{status.device_name}</strong>
        <span>Qdrant Edge · Local memory</span>
        <small>{status.total} memories ready</small>
      </div>
      <div className={"link-line " + (!status.online ? "disabled" : "")}>
        <span>
          {status.online ? "Approved changes" : "Waiting for connection"}
        </span>
        <div>
          <i />
          <ArrowRight size={17} />
        </div>
        <small>{status.queued} in queue</small>
      </div>
      <div className="topology-node">
        <div className="cloud-box">
          {status.online ? <Cloud size={32} /> : <CloudOff size={32} />}
        </div>
        <strong>Shared knowledge</strong>
        <span>Qdrant Server · Control room</span>
        <small>Selective, revision-aware sync</small>
      </div>
    </div>
  );
}

function Library({
  memories,
  onOpen,
  onNew,
  exportFile,
}: {
  memories: Memory[];
  onOpen: (m: Memory) => void;
  onNew: () => void;
  exportFile: (f: string) => void;
}) {
  const [filter, setFilter] = useState("All memories");
  const [term, setTerm] = useState("");
  const [category, setCategory] = useState("");
  const [site, setSite] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const visible = memories.filter(
    (m) =>
      (filter === "Archived" ? m.deleted : !m.deleted) &&
      (filter !== "Device only" || m.routing.route === "local") &&
      (filter !== "Shared" || m.routing.route === "cloud") &&
      (!category || m.category === category) &&
      (!site || m.site === site) &&
      (!term ||
        (m.title + " " + m.body + " " + m.tags.join(" "))
          .toLowerCase()
          .includes(term.toLowerCase())),
  );
  return (
    <>
      <PageHeading
        eyebrow="KNOWLEDGE, CLOSE AT HAND"
        title="Your field memory."
        subtitle="Every useful observation has a place here."
        action={
          <div className="heading-actions">
            <div className="export-menu">
              <button
                className="secondary"
                onClick={() => setExportOpen(!exportOpen)}
              >
                <ArrowDownToLine size={16} />
                Export
              </button>
              {exportOpen && (
                <div className="dropdown">
                  <button
                    onClick={() => {
                      exportFile("json");
                      setExportOpen(false);
                    }}
                  >
                    JSON with provenance
                  </button>
                  <button
                    onClick={() => {
                      exportFile("csv");
                      setExportOpen(false);
                    }}
                  >
                    CSV spreadsheet
                  </button>
                </div>
              )}
            </div>
            <button className="primary" onClick={onNew}>
              <Plus size={17} />
              Capture memory
            </button>
          </div>
        }
      />
      <div className="library-controls">
        <div className="tabs">
          {["All memories", "Device only", "Shared", "Archived"].map((t) => (
            <button
              key={t}
              className={filter === t ? "active" : ""}
              onClick={() => setFilter(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="filters">
          <label className="search-small">
            <SearchIcon size={16} />
            <input
              aria-label="Filter memories"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Filter by title or tag…"
            />
          </label>
          <select
            aria-label="Category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
          <select
            aria-label="Site"
            value={site}
            onChange={(e) => setSite(e.target.value)}
          >
            <option value="">All sites</option>
            {[...new Set(memories.map((m) => m.site))]
              .filter(Boolean)
              .map((s) => (
                <option key={s}>{s}</option>
              ))}
          </select>
        </div>
      </div>
      <div className="result-count">
        {visible.length} {filter.toLowerCase()}{" "}
        <span>Sorted by latest update</span>
      </div>
      <div className="memory-grid">
        {visible.map((m) => (
          <MemoryCard memory={m} key={m.id} onOpen={() => onOpen(m)} />
        ))}
      </div>
      {!visible.length && (
        <Empty
          title="No memories here yet"
          body="Capture a new note or adjust your filters."
        />
      )}
    </>
  );
}

function SearchPage({
  memories,
  onOpen,
  onError,
}: {
  memories: Memory[];
  onOpen: (m: Memory) => void;
  onError: (e: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [category, setCategory] = useState("");
  const [site, setSite] = useState("");
  const [result, setResult] = useState<Search | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<
    { seq: number; query: string; mode: string; duration: number }[]
  >([]);
  useEffect(() => {
    api<typeof history>("/search-history")
      .then(setHistory)
      .catch(() => {});
  }, []);
  const search = async (q = query) => {
    if (q.trim().length < 2) return;
    setQuery(q);
    setBusy(true);
    try {
      setResult(
        await api<Search>("/search", "POST", {
          query: q,
          mode,
          category,
          site,
          limit: 8,
        }),
      );
      setHistory(await api("/search-history"));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="MEANING OVER EXACT WORDS"
        title="Recall the useful details."
        subtitle="A question, a symptom, or a half-remembered observation. Start there."
      />
      <section className="search-workspace panel">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            search();
          }}
        >
          <div className="search-main">
            <SearchIcon size={24} />
            <input
              aria-label="Search field memory"
              placeholder="What do you need to remember?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              minLength={2}
              maxLength={1000}
              required
            />
            <button className="primary" aria-label="Recall" disabled={busy}>
              {busy ? (
                <RefreshCw className="spin" size={17} />
              ) : (
                <ArrowRight size={18} />
              )}
              <span>Recall</span>
            </button>
          </div>
          <div className="search-options">
            <div className="tabs">
              {["hybrid", "semantic", "keyword"].map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => setMode(t)}
                  className={mode === t ? "active" : ""}
                >
                  {t === "hybrid" ? <Sparkles size={13} /> : null}
                  {t[0].toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <select
              aria-label="Search category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <select
              aria-label="Search site"
              value={site}
              onChange={(e) => setSite(e.target.value)}
            >
              <option value="">All sites</option>
              {[...new Set(memories.map((m) => m.site))].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
        </form>
        <div className="suggestions">
          <span>Try a question</span>
          {[
            "pump shaking on startup",
            "pressure drops after a filter change",
            "sensor calibration",
          ].map((q) => (
            <button key={q} onClick={() => search(q)}>
              {q}
              <ArrowUpRight size={12} />
            </button>
          ))}
        </div>
      </section>
      {result ? (
        <>
          <div className="search-summary">
            <strong>{result.results.length} memories recalled</strong>
            <span>
              {result.duration_ms.toFixed(1)} ms · {result.mode} retrieval · on
              this device
            </span>
          </div>
          {result.answer.length > 0 && (
            <section className="evidence-panel">
              <div className="section-head">
                <h2>
                  <Sparkles size={19} />
                  What your notes say
                </h2>
                <span className="badge green">
                  <Lock size={12} />
                  Local recall
                </span>
              </div>
              <p className="muted">
                Source excerpts, kept in context. Review the original note
                before acting.
              </p>
              {result.answer.map((a, i) => (
                <div className="evidence" key={a.id}>
                  <button
                    className="citation"
                    onClick={() => {
                      const m = memories.find((m) => m.id === a.id);
                      if (m) onOpen(m);
                    }}
                  >
                    {i + 1}
                  </button>
                  <div>
                    <strong>{a.title}</strong>
                    <p>{a.excerpt}</p>
                    <span>{a.source}</span>
                  </div>
                </div>
              ))}
            </section>
          )}
          <div className="search-results">
            {result.results.map((m, i) => (
              <button
                className="search-result panel"
                key={m.id}
                onClick={() => onOpen(m)}
              >
                <span className="result-index">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <div className="result-meta">
                    {m.category}
                    <span>·</span>
                    {m.site}
                  </div>
                  <h3>{m.title}</h3>
                  <p>{m.body}</p>
                  <div className="tags">
                    {m.tags.map((t) => (
                      <span key={t}>{t}</span>
                    ))}
                  </div>
                </div>
                <div className="result-right">
                  <Badge memory={m} />
                  <span>Rank score {m.score?.toFixed(4)}</span>
                  <ArrowUpRight size={17} />
                </div>
              </button>
            ))}
          </div>
          {!result.results.length && (
            <Empty
              title="No matching memories"
              body="Try a broader query or remove category and site filters."
            />
          )}
        </>
      ) : (
        <div className="search-empty">
          <div className="orb">
            <Sparkles size={34} />
          </div>
          <h2>Knowledge that follows you.</h2>
          <p>
            Semantic meaning + BM25 keywords, combined locally.
            <br />
            No query text is sent to the cloud.
          </p>
          {history.length > 0 && (
            <div className="history-queries">
              <span className="eyebrow">RECENT RECALLS</span>
              {history.slice(0, 4).map((h) => (
                <button key={h.seq} onClick={() => search(h.query)}>
                  <Clock size={14} />
                  {h.query}
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}

type Run = (fn: () => Promise<unknown>, message: string) => Promise<void>;
function SyncPage({
  status,
  memories,
  sync,
  busy,
  run,
  onOpen,
  cloudEdit,
}: {
  status: Status;
  memories: Memory[];
  sync: () => void;
  busy: boolean;
  run: Run;
  onOpen: (m: Memory) => void;
  cloudEdit: (m: Memory) => void;
}) {
  const [cloud, setCloud] = useState<{
    memories: Memory[];
    engine: string;
    collection: string;
    withdrawn: number;
  } | null>(null);
  const [cloudError, setCloudError] = useState("");
  const loadCloud = useCallback(() => {
    api<typeof cloud>("/cloud")
      .then((c) => {
        setCloud(c);
        setCloudError("");
      })
      .catch((e) => {
        setCloud(null);
        setCloudError(e.message);
      });
  }, []);
  useEffect(() => {
    loadCloud();
  }, [loadCloud, status.last_sync, status.online]);
  const changeLink = (online: boolean, metered = status.metered) =>
    run(
      () => api("/connection", "PUT", { online, metered }),
      online
        ? "Cloud link enabled."
        : "Offline mode enabled. Local capture and search stay available.",
    );
  const queue = memories.filter((m) =>
    ["queued", "retry", "conflict"].includes(m.sync_state),
  );
  return (
    <>
      <PageHeading
        eyebrow="CONNECTIONS COME AND GO. KNOWLEDGE STAYS."
        title="Share on your terms."
        subtitle="Only approved knowledge leaves your device. Every change has a revision."
        action={
          <button
            className="primary"
            disabled={busy || !status.online}
            onClick={sync}
          >
            <RefreshCw size={17} className={busy ? "spin" : ""} />
            Sync now
          </button>
        }
      />
      <div className="sync-layout">
        <section className="panel">
          <div className="section-head">
            <h2>Device ↔ control room</h2>
            <span className={"badge " + (status.online ? "green" : "neutral")}>
              {status.online ? "Cloud link enabled" : "Offline mode"}
            </span>
          </div>
          <Topology status={status} />
          <div className="connection-controls">
            <div>
              <Wifi size={20} />
              <div>
                <strong>Cloud connection</strong>
                <p>Disable the link to demonstrate offline operation.</p>
              </div>
              <button
                role="switch"
                aria-checked={status.online}
                aria-label="Cloud connection"
                className={"switch " + (status.online ? "on" : "")}
                onClick={() => changeLink(!status.online)}
              >
                <span />
              </button>
            </div>
            <div>
              <SlidersHorizontal size={20} />
              <div>
                <strong>Metered connection</strong>
                <p>Defer low-priority sharing to save bandwidth.</p>
              </div>
              <button
                role="switch"
                aria-checked={status.metered}
                aria-label="Metered connection"
                className={"switch " + (status.metered ? "on" : "")}
                onClick={() => changeLink(status.online, !status.metered)}
              >
                <span />
              </button>
            </div>
          </div>
          <div className="sync-summary">
            <span>{status.connection}</span>
            <span>Last success: {ago(status.last_sync)}</span>
          </div>
        </section>
        <section className="panel sync-facts">
          <div className="eyebrow">DURABLE BY DESIGN</div>
          <h2>A queue, not a leap of faith.</h2>
          <div>
            <Check size={16} />
            <span>Changes persist across restarts</span>
          </div>
          <div>
            <Check size={16} />
            <span>Failed requests retry with backoff</span>
          </div>
          <div>
            <Check size={16} />
            <span>Conflicting edits keep both versions</span>
          </div>
          <div>
            <Check size={16} />
            <span>Withdrawals send content-free tombstones</span>
          </div>
          <div className="sync-counts">
            <div>
              <strong>{status.queued}</strong>
              <span>Pending</span>
            </div>
            <div>
              <strong>{status.conflicts}</strong>
              <span>Conflicts</span>
            </div>
            <div>
              <strong>{status.cursor}</strong>
              <span>Change cursor</span>
            </div>
          </div>
        </section>
      </div>
      <div className="section-title">
        <div>
          <h2>Changes on this device</h2>
          <p>Review queued work and resolve conflicting edits.</p>
        </div>
      </div>
      <div className="panel queue-list">
        {queue.length ? (
          queue.map((m) => (
            <button className="queue-row" key={m.id} onClick={() => onOpen(m)}>
              <span className="category-dot">
                <FileText size={18} />
              </span>
              <div>
                <strong>{m.title}</strong>
                <span>
                  {m.deleted
                    ? "Withdrawing shared copy"
                    : m.queue?.error || "Ready when the connection allows"}{" "}
                  · Local v{m.version} / cloud r{m.cloud_revision}
                </span>
              </div>
              <Badge memory={m} />
              <ChevronRight size={17} />
            </button>
          ))
        ) : (
          <Empty
            title="All caught up"
            body="No queued changes or unresolved conflicts on this device."
          />
        )}
      </div>
      <div className="section-title">
        <div>
          <h2>At the control room</h2>
          <p>
            The actual shared records stored in Qdrant Server. Private notes are
            excluded.
          </p>
        </div>
        <button className="text-button" onClick={loadCloud}>
          <RefreshCw size={14} />
          Refresh shared view
        </button>
      </div>
      {cloud ? (
        <>
          <div className="cloud-meta">
            <Cloud size={15} />
            {cloud.collection}
            <span>
              {cloud.memories.length} active memories · {cloud.withdrawn}{" "}
              withdrawn
            </span>
          </div>
          <div className="cloud-grid">
            {cloud.memories.map((m) => (
              <section className="panel cloud-card" key={m.id}>
                <div className="card-top">
                  <span className="eyebrow">{m.category}</span>
                  <span className="badge green">Cloud r{m.cloud_revision}</span>
                </div>
                <h3>{m.title}</h3>
                <p>{m.body}</p>
                <div className="card-bottom">
                  <span>{m.site}</span>
                  <button className="text-button" onClick={() => cloudEdit(m)}>
                    Edit at control room
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </section>
            ))}
          </div>
        </>
      ) : (
        <div className="cloud-offline">
          <CloudOff size={26} />
          <div>
            <strong>Shared view unavailable</strong>
            <p>{cloudError || "Connect to load the shared view."}</p>
          </div>
        </div>
      )}
    </>
  );
}

function SettingsPage({
  status,
  run,
  busy,
}: {
  status: Status;
  run: Run;
  busy: boolean;
}) {
  const [cutoff, setCutoff] = useState(status.metered_min_priority);
  const [auto, setAuto] = useState(status.auto_sync);
  useEffect(() => {
    setCutoff(status.metered_min_priority);
    setAuto(status.auto_sync);
  }, [status.metered_min_priority, status.auto_sync]);
  return (
    <>
      <PageHeading
        eyebrow="A DEVICE YOU CAN TRUST"
        title="Local first. Intentionally shared."
        subtitle="Inspect the engine and tune how your device exchanges knowledge."
      />
      <div className="settings-grid">
        <section className="panel">
          <div className="section-head">
            <h2>Device identity</h2>
            <Cpu size={22} />
          </div>
          <dl className="details">
            <dt>Name</dt>
            <dd>{status.device_name}</dd>
            <dt>Device ID</dt>
            <dd className="mono">{status.device_id}</dd>
            <dt>Vector engine</dt>
            <dd>{status.engine}</dd>
            <dt>Embedding model</dt>
            <dd>{status.model}</dd>
            <dt>Vector dimensions</dt>
            <dd>{status.dimensions}</dd>
            <dt>Storage on device</dt>
            <dd>{(status.storage_bytes / 1024 / 1024).toFixed(1)} MB</dd>
            <dt>Synchronization target</dt>
            <dd className="mono">{status.cloud_url}</dd>
          </dl>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              run(() => api("/optimize", "POST"), "Local index optimized.")
            }
          >
            <Database size={16} />
            Optimize local index
          </button>
        </section>
        <section className="panel">
          <div className="section-head">
            <h2>Connection policy</h2>
            <SlidersHorizontal size={20} />
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(
                () =>
                  api("/policy", "PUT", {
                    auto_sync: auto,
                    metered_min_priority: cutoff,
                  }),
                "Connection policy saved.",
              );
            }}
          >
            <label className="check-label">
              <input
                type="checkbox"
                checked={auto}
                onChange={(e) => setAuto(e.target.checked)}
              />
              <span>
                <strong>Automatic synchronization</strong>
                <small>Check for eligible changes every 15 seconds.</small>
              </span>
            </label>
            <label>
              Minimum priority on a metered link
              <select
                value={cutoff}
                onChange={(e) => setCutoff(+e.target.value)}
              >
                <option value={10}>All priorities</option>
                <option value={40}>Normal and above</option>
                <option value={70}>High and critical only</option>
                <option value={100}>Critical only</option>
              </select>
            </label>
            <p className="form-hint">
              Privacy withdrawals always take priority. Disabling auto sync lets
              you inspect and send changes manually.
            </p>
            <button className="primary" disabled={busy}>
              Save policy
              <Check size={16} />
            </button>
          </form>
        </section>
        <section className="panel privacy-panel">
          <div className="section-head">
            <h2>Every memory gets a routing decision.</h2>
            <ShieldCheck size={22} />
          </div>
          <div className="rule-grid">
            <div>
              <span className="rule-number">01</span>
              <h3>Device-only means device-only.</h3>
              <p>
                Explicitly private notes stay in the local shard, regardless of
                their priority.
              </p>
            </div>
            <div>
              <span className="rule-number">02</span>
              <h3>Sensitive patterns stop sharing.</h3>
              <p>
                Email addresses, credentials, phone numbers and configured
                private identifiers block sync. This is a heuristic, so review
                shared content yourself.
              </p>
            </div>
            <div>
              <span className="rule-number">03</span>
              <h3>Bandwidth follows importance.</h3>
              <p>
                Critical and high-priority knowledge travels first. Metered
                links defer less urgent updates.
              </p>
            </div>
            <div>
              <span className="rule-number">04</span>
              <h3>Retention stays reversible.</h3>
              <p>
                A memory's retention period can archive it. Its local history is
                kept, and a previously shared copy is withdrawn.
              </p>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function Editor({
  memory,
  onClose,
  save,
  controlRoom = false,
}: {
  memory: Memory | null;
  onClose: () => void;
  save: (v: Record<string, unknown>) => Promise<void>;
  controlRoom?: boolean;
}) {
  const [title, setTitle] = useState(memory?.title || "");
  const [body, setBody] = useState(memory?.body || "");
  const [category, setCategory] = useState(memory?.category || "Observation");
  const [site, setSite] = useState(memory?.site || "North station");
  const [tags, setTags] = useState(memory?.tags.join(", ") || "");
  const [visibility, setVisibility] = useState(memory?.visibility || "local");
  const [priority, setPriority] = useState(memory?.priority || "normal");
  const [source, setSource] = useState(memory?.source || "Field note");
  const [ttl, setTtl] = useState(memory?.ttl_days || 0);
  const [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await save({
        title,
        body,
        category,
        site,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        visibility,
        priority,
        source,
        ttl_days: ttl,
        expected_version: memory?.version,
      });
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="modal-backdrop">
      <section
        className="modal editor"
        role="dialog"
        aria-modal="true"
        aria-label={
          controlRoom
            ? "Edit shared memory"
            : memory
              ? "Edit memory"
              : "Capture memory"
        }
      >
        <div className="modal-header">
          <div>
            <div className="eyebrow">
              {controlRoom
                ? "CONTROL ROOM"
                : memory
                  ? "UPDATE YOUR KNOWLEDGE"
                  : "A NOTE WORTH KEEPING"}
            </div>
            <h2>
              {controlRoom
                ? "Edit the shared copy"
                : memory
                  ? "Edit memory"
                  : "Capture a memory"}
            </h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close editor"
            onClick={onClose}
          >
            <X size={21} />
          </button>
        </div>
        <form onSubmit={submit}>
          <label>
            Title
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              minLength={3}
              maxLength={150}
              placeholder="What happened, or what did you learn?"
              required
            />
          </label>
          <label>
            Observation or knowledge
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              minLength={10}
              maxLength={12000}
              rows={6}
              placeholder="Add context, findings, and a source you can return to…"
              required
            />
          </label>
          <div className="form-row">
            <label>
              Category
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              Site
              <input
                value={site}
                onChange={(e) => setSite(e.target.value)}
                maxLength={100}
                required
              />
            </label>
          </div>
          <div className="form-row">
            <label>
              Tags
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="pump, vibration, inspection"
              />
            </label>
            <label>
              Priority
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                {["low", "normal", "high", "critical"].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Source or reference
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              maxLength={300}
              required
            />
          </label>
          {!controlRoom && (
            <>
              <div className="sharing-choice">
                <span className="label-title">
                  Where should this knowledge live?
                </span>
                <div>
                  <button
                    type="button"
                    className={visibility === "local" ? "chosen" : ""}
                    onClick={() => setVisibility("local")}
                  >
                    <Lock size={19} />
                    <strong>Device only</strong>
                    <span>Keep it in your local memory</span>
                  </button>
                  <button
                    type="button"
                    className={visibility === "team" ? "chosen" : ""}
                    onClick={() => setVisibility("team")}
                  >
                    <Cloud size={19} />
                    <strong>Share with team</strong>
                    <span>Queue after the privacy check</span>
                  </button>
                </div>
              </div>
              <label>
                Archive automatically after (days)
                <input
                  type="number"
                  min={0}
                  max={3650}
                  value={ttl}
                  onChange={(e) => setTtl(+e.target.value)}
                />
                <small>0 keeps the memory until you archive it yourself.</small>
              </label>
            </>
          )}
          {controlRoom ? (
            <div className="form-note">
              <GitMerge size={17} />
              <p>
                This updates cloud revision {memory?.cloud_revision}. It reaches
                the device on its next sync; concurrent local edits will be
                preserved as a conflict.
              </p>
            </div>
          ) : (
            <div className="form-note">
              <ShieldCheck size={17} />
              <p>
                Embedding and indexing happen on this device. Team sharing is
                blocked when configured sensitive patterns are detected.
              </p>
            </div>
          )}
          <div className="modal-actions">
            <button type="button" className="secondary" onClick={onClose}>
              Cancel
            </button>
            <button className="primary" disabled={saving}>
              {saving ? (
                <RefreshCw className="spin" size={16} />
              ) : (
                <Check size={16} />
              )}{" "}
              {controlRoom ? "Update shared copy" : "Save memory"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function Inspector({
  memory,
  onClose,
  edit,
  run,
}: {
  memory: Memory;
  onClose: () => void;
  edit: () => void;
  run: Run;
}) {
  const [history, setHistory] = useState<History[]>([]);
  const [merge, setMerge] = useState("");
  const [showMerge, setShowMerge] = useState(false);
  useEffect(() => {
    api<History[]>("/memories/" + memory.id + "/history")
      .then(setHistory)
      .catch(() => {});
  }, [memory.id, memory.version, memory.cloud_revision]);
  const resolve = (choice: string) =>
    run(
      () =>
        api("/memories/" + memory.id + "/resolve", "POST", {
          choice,
          merged_body: merge,
        }),
      "Conflict resolved.",
    );
  return (
    <div className="modal-backdrop">
      <section
        className="modal inspector"
        role="dialog"
        aria-modal="true"
        aria-label="Memory details"
      >
        <div className="modal-header">
          <div className="eyebrow">
            MEMORY {memory.id.slice(0, 8).toUpperCase()}
          </div>
          <button
            className="icon-button"
            aria-label="Close memory"
            onClick={onClose}
          >
            <X size={21} />
          </button>
        </div>
        <div className="inspector-title">
          <div className="card-top">
            <span className="eyebrow">{memory.category}</span>
            <Badge memory={memory} />
          </div>
          <h2>{memory.title}</h2>
          <div className="inspector-meta">
            <MapPin size={14} />
            {memory.site}
            <span>·</span>
            {date(memory.updated_at)}
          </div>
        </div>
        <div className="memory-body">{memory.body}</div>
        <div className="tags">
          {memory.tags.map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
        <div className="source-line">
          <FileText size={15} />
          <div>
            <span>SOURCE</span>
            <strong>{memory.source}</strong>
          </div>
        </div>
        <section className="routing-card">
          <ShieldCheck size={21} />
          <div>
            <strong>
              {memory.routing.route === "cloud"
                ? "Eligible for team sharing"
                : memory.routing.route === "tombstone"
                  ? "Archived memory"
                  : "Kept on this device"}
            </strong>
            <p>{memory.routing.reason}</p>
          </div>
        </section>
        <dl className="details">
          <dt>Local version</dt>
          <dd>v{memory.version}</dd>
          <dt>Cloud revision</dt>
          <dd>r{memory.cloud_revision}</dd>
          <dt>Priority</dt>
          <dd>{memory.priority}</dd>
          <dt>Origin</dt>
          <dd>{memory.origin_device}</dd>
          <dt>Retention</dt>
          <dd>
            {memory.ttl_days
              ? memory.ttl_days + " days"
              : "Until manually archived"}
          </dd>
        </dl>
        {memory.conflict && (
          <section className="conflict-panel">
            <h3>
              <GitMerge size={19} />
              Two edits. Both remembered.
            </h3>
            <p>
              The cloud changed while your device had a local edit. Choose the
              source you want to keep or combine the notes.
            </p>
            <div className="comparison">
              <div>
                <strong>Your device · v{memory.version}</strong>
                <p>{memory.body || "Archived on device"}</p>
              </div>
              <div>
                <strong>
                  Control room · r{memory.conflict.remote.cloud_revision}
                </strong>
                <p>
                  {memory.conflict.remote.deleted
                    ? "Withdrawn at control room"
                    : memory.conflict.remote.body}
                </p>
              </div>
            </div>
            <div className="conflict-actions">
              <button className="secondary" onClick={() => resolve("local")}>
                Keep device version
              </button>
              <button className="secondary" onClick={() => resolve("cloud")}>
                Use cloud version
              </button>
              <button
                className="primary"
                onClick={() => {
                  setShowMerge(true);
                  setMerge(
                    memory.body + "\n\n" + (memory.conflict?.remote.body || ""),
                  );
                }}
              >
                <GitMerge size={14} />
                Merge notes
              </button>
            </div>
            {showMerge && (
              <div className="merge-editor">
                <label>
                  Combined note
                  <textarea
                    value={merge}
                    onChange={(e) => setMerge(e.target.value)}
                    rows={6}
                  />
                </label>
                <button className="primary" onClick={() => resolve("merge")}>
                  Save merged version
                  <Check size={15} />
                </button>
              </div>
            )}
          </section>
        )}
        <section className="revision-section">
          <h3>
            <Clock size={17} />
            Revision trail
          </h3>
          {history.map((h) => (
            <details key={h.seq}>
              <summary>
                <span>{h.action.replaceAll("-", " ")}</span>
                <span>
                  v{h.document.version} · {date(h.time)}
                </span>
              </summary>
              <p>{h.document.body || "Content-free cloud tombstone"}</p>
            </details>
          ))}
        </section>
        <div className="modal-actions">
          {!memory.conflict && (
            <>
              {memory.deleted ? (
                <button
                  className="secondary"
                  onClick={() =>
                    run(
                      () =>
                        api("/memories/" + memory.id + "/restore", "POST", {
                          expected_version: memory.version,
                        }),
                      "Memory restored.",
                    )
                  }
                >
                  <RotateCcw size={16} />
                  Restore
                </button>
              ) : (
                <>
                  <button
                    className="secondary"
                    onClick={() =>
                      run(
                        () =>
                          api("/memories/" + memory.id + "/archive", "POST", {
                            expected_version: memory.version,
                          }),
                        "Memory archived. It can be restored from the library.",
                      )
                    }
                  >
                    <Archive size={16} />
                    Archive
                  </button>
                  <button className="primary" onClick={edit}>
                    Edit memory
                    <ArrowUpRight size={15} />
                  </button>
                </>
              )}
            </>
          )}
          <button className="secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </section>
    </div>
  );
}
