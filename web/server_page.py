"""Per-server dashboard page: one server, all of its modules.

The main dashboard at ``/`` lists servers; this page (``/server/<id>``) is
dedicated to a single server and renders every module from
``web.modules`` generically (forms, lists, add/delete). Styling uses the shared
PhaseWorld system in ``web.design`` (the tokens from ``theme.md``).
"""

from __future__ import annotations

from html import escape

from config.settings import settings
from web.design import document

SERVER_CSS = """
.srv-head {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding-bottom: 32px; margin-bottom: 32px; border-bottom: 1px solid var(--line);
}
.srv-icon {
  width: 56px; height: 56px; flex: none; border-radius: 12px; object-fit: cover;
  background: var(--bg-3); border: 1px solid var(--line);
}
.srv-icon--empty { display: grid; place-items: center; color: var(--fg-3); font: 500 20px var(--font-mono); }
.srv-title { min-width: 0; }
.srv-title h1 { font: 600 26px/1.2 var(--font-display); letter-spacing: -0.02em; margin: 2px 0 4px; }
.srv-meta { color: var(--fg-3); font: 400 12px var(--font-mono); }
.srv-back { margin-left: auto; }

.srv-layout {
  display: grid; grid-template-columns: 240px 1fr; gap: 32px; align-items: start;
}
.srv-nav {
  position: sticky; top: 92px; display: grid; gap: 2px;
  border: 1px solid var(--line); border-radius: var(--radius);
  background: var(--bg-2); padding: 6px;
}
.nav-item {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%; padding: 9px 12px; border: 0; border-radius: var(--radius-sm);
  background: transparent; color: var(--fg-2);
  font: 400 13px var(--font-body); text-align: left; cursor: pointer;
  transition: background-color 140ms var(--ease), color 140ms var(--ease);
}
.nav-item:hover { background: var(--bg-3); color: var(--fg); }
.nav-item.active { background: var(--bg-3); color: var(--fg); box-shadow: inset 2px 0 0 var(--signal); }

.module-head { margin-bottom: 20px; }
.module-head .section-title { font-size: 1.4rem; }
.module-card {
  padding: 22px; border: 1px solid var(--line); border-radius: var(--radius);
  background: var(--bg-2); margin-bottom: 14px;
}
.module-card > .section-title { font-size: 1.05rem; margin-bottom: 14px; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.field-label { display: grid; gap: 6px; font: 400 12px var(--font-mono); color: var(--fg-3); }
.field-label .field { font-family: var(--font-body); }
.check {
  display: inline-flex; align-items: center; gap: 10px; cursor: pointer;
  font: 400 14px var(--font-body); color: var(--fg);
}
.check input { width: 16px; height: 16px; accent-color: var(--signal); }
.field-help { color: var(--fg-3); font: 400 11px var(--font-mono); }
.module-actions { margin-top: 18px; display: flex; gap: 10px; align-items: center; }

.data-table { width: 100%; border-collapse: collapse; font: 400 13px var(--font-body); }
.data-table th {
  text-align: left; padding: 8px 10px; color: var(--fg-3);
  font: 400 11px var(--font-mono); border-bottom: 1px solid var(--line);
}
.data-table td {
  padding: 10px; border-bottom: 1px solid var(--line); color: var(--fg);
  vertical-align: middle;
}
.data-table tr:last-child td { border-bottom: 0; }
.data-table .mono { font-family: var(--font-mono); font-size: 12px; color: var(--fg-2); }
.row-delete {
  height: 28px; padding: 0 10px; border: 1px solid var(--line-2); border-radius: var(--radius-sm);
  background: transparent; color: var(--fg-2); font: 400 12px var(--font-mono); cursor: pointer;
}
.row-delete:hover { color: var(--danger); border-color: var(--danger); }
.add-form {
  margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--line);
  display: flex; flex-wrap: wrap; gap: 10px; align-items: end;
}
.add-form .field-label { flex: 1 1 160px; }
.empty-row td { color: var(--fg-3); text-align: center; padding: 18px; }

.toast {
  margin-top: 14px; padding: 10px 14px; border: 1px solid var(--line-2);
  border-radius: var(--radius-sm); background: var(--bg-2); color: var(--fg);
  font: 400 13px var(--font-mono);
}
.toast.ok { border-color: var(--signal); }
.toast.bad { border-color: var(--danger); }

@media (max-width: 760px) {
  .srv-layout { grid-template-columns: 1fr; }
  .srv-nav { position: static; display: flex; overflow-x: auto; }
  .nav-item { width: auto; white-space: nowrap; }
}
"""

SERVER_JS = """
<script>
(() => {
  const SERVER_ID = window.DASH_SERVER_ID;
  const nav = document.getElementById("module-nav");
  const content = document.getElementById("module-content");
  if (!nav || !content) return;

  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach((key) => {
        const value = attrs[key];
        if (value == null) return;
        if (key === "class") node.className = value;
        else if (key === "text") node.textContent = value;
        else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value);
      });
    }
    children.flat().forEach((child) => {
      if (child == null) return;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    });
    return node;
  }

  async function api(path, options) {
    const res = await fetch(path, Object.assign({ cache: "no-store" }, options || {}));
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      const message = data && data.error ? data.error : ("HTTP " + res.status);
      throw new Error(message);
    }
    return data;
  }

  function toast(text, kind) {
    const existing = content.querySelector(".toast");
    if (existing) existing.remove();
    content.append(h("div", { class: "toast " + (kind || ""), text: text }));
    setTimeout(() => {
      const node = content.querySelector(".toast");
      if (node) node.remove();
    }, 4000);
  }

  function renderField(field) {
    const type = field.type;
    const labelText = field.label || field.name;
    const help = field.help ? h("div", { class: "field-help", text: field.help }) : null;

    if (type === "bool") {
      const input = h("input", { type: "checkbox" });
      input.checked = Boolean(field.value);
      const wrap = h("label", { class: "check" }, input, labelText);
      return { node: h("div", null, wrap, help), get: () => input.checked };
    }

    let input;
    if (type === "textarea") {
      input = h("textarea", { class: "field", rows: "3" });
      input.value = field.value == null ? "" : String(field.value);
    } else if (type === "int") {
      input = h("input", { class: "field", type: "number", step: "1" });
      if (field.min != null) input.min = String(field.min);
      if (field.max != null) input.max = String(field.max);
      input.value = field.value == null ? "" : String(field.value);
    } else if (type === "select" || type === "channel" || type === "voice" || type === "category" || type === "role") {
      input = h("select", { class: "field" });
      const options = field.options || [];
      const empty = h("option", { value: "", text: "— none —" });
      input.append(empty);
      options.forEach((opt) => {
        const option = h("option", { value: String(opt.value), text: opt.label });
        if (field.value != null && String(field.value) === String(opt.value)) option.selected = true;
        input.append(option);
      });
      if (field.value == null) input.value = "";
    } else {
      input = h("input", { class: "field", type: "text" });
      if (field.placeholder) input.placeholder = field.placeholder;
      input.value = field.value == null ? "" : String(field.value);
    }

    const wrap = h("label", { class: "field-label" }, labelText, input);
    if (help) wrap.append(help);
    return { node: wrap, get: () => input.value };
  }

  async function post(key, body) {
    return api("/api/servers/" + SERVER_ID + "/modules/" + key, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  function renderForm(section, key) {
    const parts = [];
    const getters = {};
    (section.fields || []).forEach((field) => {
      const r = renderField(field);
      getters[field.name] = r.get;
      parts.push(r.node);
    });
    const save = h("button", {
      class: "btn primary", type: "button",
      onclick: async () => {
        const values = {};
        Object.keys(getters).forEach((name) => { values[name] = getters[name](); });
        try {
          await post(key, { values });
          toast("Saved.", "ok");
          select(key);
        } catch (error) { toast(error.message, "bad"); }
      }
    }, section.submit || "Save");

    return h("section", { class: "module-card" },
      section.title ? h("h3", { class: "section-title", text: section.title }) : null,
      h("div", { class: "form-grid" }, parts),
      h("div", { class: "module-actions" }, save)
    );
  }

  function renderList(section, key) {
    const columns = section.columns || [];
    const rows = section.rows || [];
    const canDelete = section.delete && Array.isArray(section.delete.keys);

    const thead = h("thead", null, h("tr", null,
      columns.map((col) => h("th", { text: col.label })),
      canDelete ? h("th", null) : null
    ));

    const tbody = h("tbody", null);
    if (!rows.length) {
      const span = columns.length + (canDelete ? 1 : 0);
      tbody.append(h("tr", { class: "empty-row" },
        h("td", { colspan: String(span), text: "Nothing here yet." })));
    } else {
      rows.forEach((row) => {
        const cells = columns.map((col) => {
          const value = row[col.key];
          const isId = col.key.toLowerCase().includes("id");
          return h("td", isId ? { class: "mono", text: value == null ? "—" : String(value) }
                              : { text: value == null ? "—" : String(value) });
        });
        if (canDelete) {
          cells.push(h("td", null, h("button", {
            class: "row-delete", type: "button",
            onclick: async () => {
              try {
                await post(key, { action: "delete", row });
                toast("Removed.", "ok");
                select(key);
              } catch (error) { toast(error.message, "bad"); }
            }
          }, section.delete.label || "Delete")));
        }
        tbody.append(h("tr", null, cells));
      });
    }

    let addForm = null;
    if (section.add) {
      const getters = {};
      const fields = (section.add.fields || []).map((field) => {
        const r = renderField(field);
        getters[field.name] = r.get;
        return r.node;
      });
      const submit = h("button", {
        class: "btn primary", type: "button",
        onclick: async () => {
          const values = {};
          Object.keys(getters).forEach((name) => { values[name] = getters[name](); });
          try {
            await post(key, { action: "add", values });
            toast("Added.", "ok");
            select(key);
          } catch (error) { toast(error.message, "bad"); }
        }
      }, section.add.submit || "Add");
      addForm = h("div", { class: "add-form" }, fields, submit);
    }

    return h("section", { class: "module-card" },
      section.title ? h("h3", { class: "section-title", text: section.title }) : null,
      h("table", { class: "data-table" }, thead, tbody),
      addForm
    );
  }

  function renderNote(section) {
    return h("section", { class: "module-card" },
      h("p", { class: "field-help", text: section.text || "" }));
  }

  let currentKey = null;
  function render(data) {
    content.textContent = "";
    content.append(h("div", { class: "module-head" },
      h("h2", { class: "section-title", text: data.label }),
      h("p", { class: "section-note", text: data.description })));
    (data.sections || []).forEach((section) => {
      if (section.type === "form") content.append(renderForm(section, data.key));
      else if (section.type === "list") content.append(renderList(section, data.key));
      else if (section.type === "note") content.append(renderNote(section));
    });
  }

  async function select(key) {
    currentKey = key;
    Array.from(nav.children).forEach((button) => {
      button.classList.toggle("active", button.dataset.key === key);
    });
    content.textContent = "";
    content.append(h("div", { class: "empty", text: "Loading…" }));
    try {
      const data = await api("/api/servers/" + SERVER_ID + "/modules/" + key);
      render(data);
    } catch (error) {
      content.textContent = "";
      content.append(h("div", { class: "empty", text: error.message }));
    }
  }

  async function loadModules() {
    try {
      const data = await api("/api/servers/" + SERVER_ID + "/modules");
      const modules = data.modules || [];
      nav.textContent = "";
      if (!modules.length) {
        content.textContent = "";
        content.append(h("div", { class: "empty", text: "No modules available." }));
        return;
      }
      modules.forEach((module) => {
        const button = h("button", {
          class: "nav-item", type: "button", "data-key": module.key,
          title: module.description, onclick: () => select(module.key)
        }, module.label);
        nav.append(button);
      });
      select(modules[0].key);
    } catch (error) {
      content.textContent = "";
      content.append(h("div", { class: "empty", text: error.message }));
    }
  }

  loadModules();
})();
</script>
"""


def render_server_page(
    *,
    guild_name: str,
    guild_id: int,
    guild_icon: str | None,
    member_count: int | None,
) -> str:
    if guild_icon:
        icon = f'<img class="srv-icon" src="{escape(guild_icon)}" alt="" loading="lazy">'
    else:
        initial = escape((guild_name or "?")[:1].upper())
        icon = f'<div class="srv-icon srv-icon--empty" aria-hidden="true">{initial}</div>'

    members = f"{member_count:,} members" if member_count is not None else ""
    body = f"""
<div class="srv-head">
  {icon}
  <div class="srv-title">
    <p class="eyebrow">Server · {escape(settings.bot_name)}</p>
    <h1>{escape(guild_name)}</h1>
    <div class="srv-meta">{escape(str(guild_id))}{(" · " + escape(members)) if members else ""}</div>
  </div>
  <a class="btn srv-back" href="/">← All servers</a>
</div>
<div class="srv-layout">
  <nav class="srv-nav" id="module-nav" aria-label="Modules"></nav>
  <section class="srv-content" id="module-content">
    <div class="empty">Loading modules…</div>
  </section>
</div>
"""
    # Emit the ID as a JS string: Discord snowflakes exceed Number.MAX_SAFE_INTEGER,
    # so a numeric literal would be rounded and every API call would then ask for
    # a guild the bot is not in ("server not found").
    prelude = f'<script>window.DASH_SERVER_ID="{int(guild_id)}";</script>'
    return document(
        f"{guild_name} · {settings.bot_name} dashboard",
        prelude + body + SERVER_JS,
        active="dashboard",
        description=f"Manage {guild_name}.",
        url=settings.dashboard_url,
        extra_css=SERVER_CSS)