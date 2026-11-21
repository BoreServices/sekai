"""Status dashboard markup and telemetry view.

A quiet, high-contrast monochrome technical dashboard presenting real-time
system telemetry, gateway latency, process resource utilization, and dependency status.
"""

from __future__ import annotations

from config.settings import settings
from web.design import document

STATUS_CSS = """
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  padding-bottom: 40px;
  margin-bottom: 64px;
  border-bottom: 1px solid var(--line);
}
.page-head-copy { max-width: var(--measure); }
.head-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.refresh-tag {
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
}

/* Stat Grid layout variations */
.stat-grid.primary {
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
}
.stat-grid.secondary {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin-top: 14px;
}

/* Latency History Chart */
.chart-wrap {
  position: relative;
  height: 180px;
  width: 100%;
}
.chart-wrap svg {
  display: block;
  width: 100%;
  height: 100%;
}
.chart-line {
  stroke: var(--fg);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
  stroke-linejoin: round;
}
.chart-area {
  fill: var(--fg);
  fill-opacity: 0.08;
}
.chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-3);
  font: 400 13px var(--font-mono);
}
.chart-axis {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font: 400 12px var(--font-mono);
  color: var(--fg-3);
}

/* Services and link rows */
.service-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}
.service-row:last-child {
  border-bottom: 0;
}
.service-link {
  font: 500 14px var(--font-display);
  color: var(--fg);
  text-decoration: none;
}
.service-link:hover {
  text-decoration: underline;
}
.service-url {
  color: var(--fg-3);
  font: 400 11px var(--font-mono);
  margin-top: 2px;
}

.state-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
}
.state-indicator.ok { color: var(--signal); }
.state-indicator.warn { color: var(--warning); }
.state-indicator.bad { color: var(--danger); }
.kv.mt { margin-top: 10px; }

@media (max-width: 560px) {
  .head-meta { justify-content: flex-start; }
  .stat-grid.secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .card.full { grid-column: 1 / -1; }
}
"""

STATUS_BODY = """
<div class="page-head" id="telemetry">
  <div class="page-head-copy">
    <p class="eyebrow">00 / Telemetry · Live status</p>
    <h1 class="page-title">Status</h1>
    <p class="page-lede">Real-time telemetry and health across the bot runtime,
    host system resources, web endpoints, and audio streaming nodes.</p>
  </div>
  <div class="head-meta">
    <span class="pill" id="online-pill" role="status" aria-live="polite">
      <span class="dot" id="dot" aria-hidden="true"></span>
      <span id="status-text">Connecting…</span>
    </span>
    <span class="dev-tag" id="dev-badge" style="display:none">dev</span>
    <span class="refresh-tag">updated <span id="updated" class="mono">—</span></span>
  </div>
</div>

<div class="banner" id="offline-banner" role="status">
  <span class="dot warn" aria-hidden="true"></span>
  <span>Telemetry endpoint is unreachable — reconnecting every five seconds.</span>
</div>

<section class="section" id="metrics" aria-labelledby="metrics-title" style="margin-top:0">
  <div class="section-head">
    <div>
      <p class="section-label">01 / Metrics</p>
      <h2 class="section-title" id="metrics-title">Primary metrics</h2>
    </div>
    <p class="section-note">Gateway latency, active guilds, and memory footprint.</p>
  </div>

  <div class="stat-grid primary">
    <div class="stat">
      <p class="stat-label">Uptime</p>
      <p class="stat-value" id="uptime">—</p>
      <p class="stat-sub">since <span id="started" class="mono">—</span></p>
    </div>
    <div class="stat">
      <p class="stat-label">Gateway latency</p>
      <p class="stat-value" id="latency">—</p>
      <p class="stat-sub">Discord websocket</p>
    </div>
    <div class="stat">
      <p class="stat-label">Servers</p>
      <p class="stat-value" id="guilds">—</p>
      <p class="stat-sub">connected guilds</p>
    </div>
    <div class="stat">
      <p class="stat-label">Members</p>
      <p class="stat-value" id="users">—</p>
      <p class="stat-sub">reached users</p>
    </div>
  </div>

  <div class="stat-grid secondary">
    <div class="stat">
      <p class="stat-label">Channels</p>
      <p class="stat-value" id="channels">—</p>
      <p class="stat-sub">text channels</p>
    </div>
    <div class="stat">
      <p class="stat-label">Commands</p>
      <p class="stat-value" id="commands">—</p>
      <p class="stat-sub">prefix commands</p>
    </div>
    <div class="stat">
      <p class="stat-label">Process RAM</p>
      <p class="stat-value" id="stat-ram">—</p>
      <p class="stat-sub">resident memory</p>
    </div>
    <div class="stat">
      <p class="stat-label">Host CPU</p>
      <p class="stat-value" id="stat-cpu">—</p>
      <p class="stat-sub">total system load</p>
    </div>
  </div>
</section>

<section class="section" id="runtime" aria-labelledby="runtime-title">
  <div class="section-head">
    <div>
      <p class="section-label">02 / Runtime</p>
      <h2 class="section-title" id="runtime-title">Process &amp; host</h2>
    </div>
    <p class="section-note">Resource use of the bot process next to the machine it runs on.</p>
  </div>

  <div class="grid-2">
    <article class="card">
      <header class="card-head">
        <h3 class="card-title">Bot process</h3>
        <span class="card-note mono" id="p-pid-label">pid —</span>
      </header>
      <div class="card-body">
        <div class="meter">
          <div class="meter-head"><span>CPU</span><span class="mono" id="pv-cpu">—</span></div>
          <div class="meter-track" role="img" aria-label="Process CPU usage" id="pv-cpu-bar-wrap">
            <div class="meter-fill" id="pv-cpu-bar"></div>
          </div>
        </div>
        <div class="meter">
          <div class="meter-head"><span>Memory</span><span class="mono" id="pv-ram">—</span></div>
          <div class="meter-track" role="img" aria-label="Process memory usage" id="pv-ram-bar-wrap">
            <div class="meter-fill" id="pv-ram-bar"></div>
          </div>
        </div>
        <div class="kv mt">
          <div class="kv-row"><span class="kv-k">PID</span><span class="kv-v" id="p-pid">—</span></div>
          <div class="kv-row"><span class="kv-k">Threads</span><span class="kv-v" id="p-threads">—</span></div>
          <div class="kv-row"><span class="kv-k">Started</span><span class="kv-v" id="p-start">—</span></div>
        </div>
      </div>
    </article>

    <article class="card">
      <header class="card-head">
        <h3 class="card-title">Host machine</h3>
        <span class="card-note mono" id="s-host">—</span>
      </header>
      <div class="card-body">
        <div class="meter">
          <div class="meter-head"><span>CPU</span><span class="mono" id="pv-scpu">—</span></div>
          <div class="meter-track" role="img" aria-label="System CPU usage" id="pv-scpu-bar-wrap">
            <div class="meter-fill" id="pv-scpu-bar"></div>
          </div>
        </div>
        <div class="meter">
          <div class="meter-head"><span>RAM</span><span class="mono" id="pv-sram">—</span></div>
          <div class="meter-track" role="img" aria-label="System memory usage" id="pv-sram-bar-wrap">
            <div class="meter-fill" id="pv-sram-bar"></div>
          </div>
        </div>
        <div class="meter">
          <div class="meter-head"><span>Disk</span><span class="mono" id="pv-sdisk">—</span></div>
          <div class="meter-track" role="img" aria-label="Disk usage" id="pv-sdisk-bar-wrap">
            <div class="meter-fill" id="pv-sdisk-bar"></div>
          </div>
        </div>
        <div class="kv mt">
          <div class="kv-row"><span class="kv-k">Platform</span><span class="kv-v" id="s-platform">—</span></div>
          <div class="kv-row"><span class="kv-k">Python</span><span class="kv-v" id="s-python">—</span></div>
          <div class="kv-row"><span class="kv-k">discord.py</span><span class="kv-v" id="s-discordpy">—</span></div>
          <div class="kv-row"><span class="kv-k">CPU cores</span><span class="kv-v" id="s-cores">—</span></div>
          <div class="kv-row"><span class="kv-k">Load (1m)</span><span class="kv-v" id="s-load">—</span></div>
          <div class="kv-row"><span class="kv-k">Host uptime</span><span class="kv-v" id="s-uptime">—</span></div>
        </div>
      </div>
    </article>
  </div>
</section>

<section class="section" id="history" aria-labelledby="history-title">
  <div class="section-head">
    <div>
      <p class="section-label">03 / History</p>
      <h2 class="section-title" id="history-title">Gateway latency (24h)</h2>
    </div>
    <p class="section-note" id="hist-note">Sampled once a minute since the bot process started.</p>
  </div>
  <article class="card">
    <div class="chart-wrap" id="hist-wrap" role="img" aria-label="Gateway latency history">
      <svg id="hist-svg" viewBox="0 0 600 160" preserveAspectRatio="none" aria-hidden="true"></svg>
      <div class="chart-empty" id="hist-empty">Collecting latency samples…</div>
    </div>
    <div class="chart-axis">
      <span id="hist-min">—</span>
      <span id="hist-max">—</span>
    </div>
  </article>
</section>

<section class="section" id="services" aria-labelledby="services-title">
  <div class="section-head">
    <div>
      <p class="section-label">04 / Services</p>
      <h2 class="section-title" id="services-title">Sites &amp; dependencies</h2>
    </div>
    <p class="section-note">Operational status of web services, tunnel, and music nodes.</p>
  </div>

  <div class="grid-2">
    <article class="card">
      <header class="card-head">
        <h3 class="card-title">Websites</h3>
      </header>
      <div class="card-body">
        <div class="service-row">
          <div>
            <a class="service-link" id="w-main-link" href="#" target="_blank" rel="noopener">Landing page</a>
            <div class="service-url" id="w-main-url">—</div>
          </div>
          <span class="state-indicator" id="w-main-state"><span class="dot" aria-hidden="true"></span><span>—</span></span>
        </div>
        <div class="service-row">
          <div>
            <a class="service-link" id="w-tickets-link" href="#" target="_blank" rel="noopener">Ticket transcripts</a>
            <div class="service-url" id="w-tickets-url">—</div>
          </div>
          <span class="state-indicator" id="w-tickets-state"><span class="dot" aria-hidden="true"></span><span>—</span></span>
        </div>
        <div class="service-row">
          <div>
            <a class="service-link" id="w-verify-link" href="#" target="_blank" rel="noopener">Verification portal</a>
            <div class="service-url" id="w-verify-url">—</div>
          </div>
          <span class="state-indicator" id="w-verify-state"><span class="dot" aria-hidden="true"></span><span>—</span></span>
        </div>
      </div>
    </article>

    <article class="card">
      <header class="card-head">
        <h3 class="card-title">Dependencies</h3>
      </header>
      <div class="card-body">
        <div class="kv">
          <div class="kv-row"><span class="kv-k">Cloudflare tunnel</span><span class="kv-v" id="svc-tunnel">—</span></div>
          <div class="kv-row"><span class="kv-k">Internal HTTP</span><span class="kv-v" id="svc-web">—</span></div>
          <div class="kv-row"><span class="kv-k">NodeLink cluster</span><span class="kv-v" id="svc-nodelink">—</span></div>
        </div>
      </div>
    </article>

    <article class="card full">
      <header class="card-head">
        <h3 class="card-title">Music cluster</h3>
        <span class="card-note mono" id="m-available">—</span>
      </header>
      <div class="card-body">
        <div class="kv">
          <div class="kv-row"><span class="kv-k">Active node</span><span class="kv-v" id="m-node">—</span></div>
          <div class="kv-row"><span class="kv-k">Endpoint</span><span class="kv-v" id="m-url">—</span></div>
          <div class="kv-row"><span class="kv-k">Connection</span><span class="kv-v" id="m-status">—</span></div>
          <div class="kv-row"><span class="kv-k">Active players</span><span class="kv-v" id="m-players">—</span></div>
          <div class="kv-row"><span class="kv-k">Ping</span><span class="kv-v" id="m-ping">—</span></div>
        </div>
      </div>
    </article>
  </div>
</section>
"""

STATUS_JS = """
<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const set = (id, value) => { const el = $(id); if (el) el.textContent = value; };
  const num = (value) => (value == null ? "—" : Number(value).toLocaleString());
  const fixed = (value, digits = 1) => (value == null ? "—" : Number(value).toFixed(digits));

  const urlParams = new URLSearchParams(window.location.search);
  const isTroll = urlParams.get("troll") === "True" || urlParams.has("troll");

  function duration(total) {
    total = Math.max(0, Math.floor(total || 0));
    const d = Math.floor(total / 86400);
    const h = Math.floor((total % 86400) / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (d) return d + "d " + h + "h " + m + "m";
    if (h) return h + "h " + m + "m " + s + "s";
    if (m) return m + "m " + s + "s";
    return s + "s";
  }

  function bytes(mb) {
    if (mb == null) return "—";
    return mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : Math.round(mb) + " MB";
  }

  function when(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }

  function bar(id, percent) {
    const pct = Math.max(0, Math.min(100, Number(percent) || 0));
    const fill = $(id);
    if (!fill) return;
    fill.style.width = pct + "%";
    fill.style.backgroundColor = pct >= 90
      ? "var(--danger)"
      : pct >= 75
        ? "var(--warning)"
        : "var(--fg-2)";
    const wrap = $(id + "-wrap");
    if (wrap) wrap.setAttribute("aria-valuetext", pct.toFixed(0) + "%");
  }

  function tone(id, kind, text) {
    const el = $(id);
    if (!el) return;
    el.textContent = text;
    el.className = "kv-v" + (kind ? " " + kind : "");
  }

  function state(id, kind, text) {
    const el = $(id);
    if (!el) return;
    el.className = "state-indicator" + (kind ? " " + kind : "");
    el.textContent = "";
    const dot = document.createElement("span");
    dot.className = "dot" + (kind ? " " + kind : "");
    dot.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = text;
    el.append(dot, label);
  }

  function website(id, url, kind, text) {
    const link = $("w-" + id + "-link");
    const urlEl = $("w-" + id + "-url");
    if (urlEl) urlEl.textContent = url || "not configured";
    if (link) {
      if (url) link.href = url; else link.removeAttribute("href");
    }
    state("w-" + id + "-state", kind, text);
  }

  async function refresh() {
    try {
      let d;
      if (isTroll) {
        // Subtle, realistic-looking anomaly payload (Memory leak & thread runaway)
        d = {
          generated_at: new Date().toISOString(),
          bot: { online: true, dev_mode: false, name: "GatewayBot", uptime_seconds: 43200, started_at: "2026-06-01T04:12:00Z", latency_ms: 3840 },
          counts: { guilds: 84, users: 142850, channels: 1205, commands: 42 },
          process: { pid: 31408, memory_mb: 14320.4, memory_percent: 89.5, cpu_percent: 94.2, threads: 412, started_at: "2026-06-01T04:12:00Z" },
          system: { cpu_percent: 98.4, memory_used_mb: 29800, memory_total_mb: 32000, memory_percent: 93.1, disk_used_gb: 412.3, disk_total_gb: 512.0, hostname: "ip-10-0-4-19.ec2.internal", platform: "Linux 6.8.0-31-generic", python: "Python 3.11.9", discordpy: "discord.py 2.4.0", cpu_cores: 4, load_1m: 5.82, uptime_seconds: 2592000 },
          websites: {
            main: { url: "http://127.0.0.1:8080", running: true },
            tickets: { url: "http://127.0.0.1:8083", running: true },
            verify: { url: "http://127.0.0.1:8084", running: false }
          },
          services: {
            tunnel: { enabled: true, running: true },
            nodelink: { online: 1, total: 3 }
          },
          music: { node_name: "us-east-audio-02", node_url: "http://10.0.4.52:2333", status: "Degraded", connected: true, players: 38, latency_ms: 1250, available: ["us-east-audio-01", "us-east-audio-02", "eu-west-audio-01"] }
        };
      } else {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        d = await response.json();
      }

      const bot = d.bot, proc = d.process, sys = d.system, svc = d.services;
      const w = d.websites, nl = svc.nodelink, m = d.music;

      $("offline-banner").classList.remove("show");
      set("status-text", bot.online ? (isTroll ? "Degraded" : "Online") : "Starting");
      $("dot").className = "dot" + (bot.online ? (isTroll ? " warn" : " ok") : " warn");
      $("dev-badge").style.display = bot.dev_mode ? "inline-flex" : "none";
      set("updated", new Date(d.generated_at).toLocaleTimeString());
      document.title = bot.name + " · " + (bot.online ? "Online" : "Starting");

      set("uptime", duration(bot.uptime_seconds));
      set("started", when(bot.started_at));
      set("latency", bot.latency_ms == null ? "N/A" : Math.round(bot.latency_ms) + " ms");
      set("guilds", num(d.counts.guilds));
      set("users", num(d.counts.users));
      set("channels", num(d.counts.channels));
      set("commands", num(d.counts.commands));
      set("stat-ram", bytes(proc.memory_mb));
      set("stat-cpu", fixed(sys.cpu_percent) + "%");

      set("p-pid-label", "pid " + proc.pid);
      set("pv-cpu", fixed(proc.cpu_percent) + "%");
      bar("pv-cpu-bar", proc.cpu_percent);
      set("pv-ram", bytes(proc.memory_mb));
      bar("pv-ram-bar", proc.memory_percent);
      set("p-pid", String(proc.pid));
      set("p-threads", num(proc.threads));
      set("p-start", when(proc.started_at));

      set("pv-scpu", fixed(sys.cpu_percent) + "%");
      bar("pv-scpu-bar", sys.cpu_percent);
      set("pv-sram", bytes(sys.memory_used_mb) + " / " + bytes(sys.memory_total_mb));
      bar("pv-sram-bar", sys.memory_percent);
      set("pv-sdisk", sys.disk_used_gb.toFixed(1) + " / " + sys.disk_total_gb.toFixed(1) + " GB");
      bar("pv-sdisk-bar", sys.disk_percent);
      set("s-host", sys.hostname);
      set("s-platform", sys.platform);
      set("s-python", sys.python);
      set("s-discordpy", sys.discordpy);
      set("s-cores", num(sys.cpu_cores));
      set("s-load", sys.load_1m == null ? "N/A" : sys.load_1m.toFixed(2));
      set("s-uptime", duration(sys.uptime_seconds));

      website("main", w.main.url, w.main.running ? "ok" : "bad", w.main.running ? "Serving" : "Stopped");
      website("tickets", w.tickets.url, w.tickets.running ? "ok" : "bad", w.tickets.running ? "Serving" : "Stopped");
      website(
        "verify",
        w.verify.url,
        !w.verify.configured ? "warn" : w.verify.running ? "ok" : "bad",
        !w.verify.configured ? "Needs setup" : w.verify.running ? "Ready" : "Stopped"
      );

      if (!svc.tunnel.enabled) tone("svc-tunnel", "muted", "Disabled (dev)");
      else tone("svc-tunnel", svc.tunnel.running ? "ok" : "bad", svc.tunnel.running ? "Running" : "Stopped");
      tone("svc-web", bot.online ? "ok" : "warn", bot.online ? "Online" : "Starting");
      tone(
        "svc-nodelink",
        nl.online === 0 ? "bad" : nl.online < nl.total ? "warn" : "ok",
        nl.online + "/" + nl.total + " online"
      );

      set("m-node", m.node_name || "—");
      set("m-url", m.node_url || "—");
      set("m-status", m.status);
      $("m-status").className = "kv-v " + (m.connected ? "warn" : "bad");
      set("m-players", num(m.players));
      set("m-ping", m.latency_ms == null ? "N/A" : m.latency_ms + " ms");
      set("m-available", m.available.length + " configured");
    } catch (error) {
      set("status-text", "Unreachable");
      $("dot").className = "dot bad";
      $("offline-banner").classList.add("show");
      set("updated", "—");
    }
  }

  refresh();
  if (!isTroll) setInterval(refresh, 5000);

  const NS = "http://www.w3.org/2000/svg";
  function drawHistory(payload) {
    const svg = $("hist-svg");
    const empty = $("hist-empty");
    if (!svg) return;
    const points = (payload.points || []).filter((p) => p.online && p.latency_ms != null);
    svg.textContent = "";
    if (points.length < 2) {
      empty.style.display = "flex";
      set("hist-min", "—");
      set("hist-max", "—");
      return;
    }
    empty.style.display = "none";
    const W = 600, H = 160, pad = 8;
    const t0 = points[0].t, t1 = points[points.length - 1].t || t0 + 1;
    const values = points.map((p) => p.latency_ms);
    const max = Math.max.apply(null, values) || 1;
    const x = (p) => pad + ((p.t - t0) / Math.max(1, t1 - t0)) * (W - pad * 2);
    const y = (p) => H - pad - (p.latency_ms / max) * (H - pad * 2);
    const line = points.map((p) => x(p).toFixed(1) + "," + y(p).toFixed(1)).join(" ");
    const area = pad + "," + (H - pad) + " " + line + " " + x(points[points.length - 1]).toFixed(1) + "," + (H - pad);
    const add = (tag, attrs) => {
      const el = document.createElementNS(NS, tag);
      Object.keys(attrs).forEach((k) => el.setAttribute(k, attrs[k]));
      svg.append(el);
    };
    add("polygon", { points: area, class: "chart-area" });
    add("polyline", { points: line, class: "chart-line", fill: "none" });
    set("hist-min", "min " + Math.min.apply(null, values).getvalue + " ms");
    set("hist-max", "peak " + max.toFixed(0) + " ms");
  }

  async function refreshHistory() {
    try {
      let data;
      if (isTroll) {
        // Plausible latency spike chart history (looks like a sudden network partition or garbage collection pause)
        data = {
          points: [
            { t: 1, online: true, latency_ms: 45 },
            { t: 2, online: true, latency_ms: 52 },
            { t: 3, online: true, latency_ms: 48 },
            { t: 4, online: true, latency_ms: 1850 },
            { t: 5, online: true, latency_ms: 3840 },
            { t: 6, online: true, latency_ms: 2100 }
          ]
        };
      } else {
        const response = await fetch("/api/history", { cache: "no-store" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        data = await response.json();
      }
      drawHistory(data);
    } catch (error) {
      // Keep last drawn chart
    }
  }

  refreshHistory();
  if (!isTroll) setInterval(refreshHistory, 60000);
})();
</script>
"""


def render_status_page() -> str:
    toc = [
        ("telemetry", "00 / Telemetry"),
        ("metrics", "01 / Metrics"),
        ("runtime", "02 / Runtime"),
        ("history", "03 / History"),
        ("services", "04 / Services"),
    ]
    return document(
        f"{settings.bot_name} · Status",
        STATUS_BODY + STATUS_JS,
        active="status",
        description=(
            f"Live telemetry for {settings.bot_name}: uptime, gateway latency, "
            "resource utilization, web services, Cloudflare tunnel, and music nodes."
        ),
        extra_css=STATUS_CSS,
        toc=toc)
