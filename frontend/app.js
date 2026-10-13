const { useState, useEffect, useCallback } = React;

const API = ""; // same origin as the served frontend

// --- API helpers -----------------------------------------------------------
async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

const STATUSES = [
  "Saved", "Ready to Apply", "Applied", "Under Review", "Recruiter Contacted",
  "Interview", "Technical Interview", "Final Interview", "Offer",
  "Rejected", "Withdrawn", "No Response",
];
const SPONSORSHIP = [
  "Confirmed Yes", "Confirmed No", "Requested", "Unknown",
  "Previously Sponsored", "Currently Sponsoring", "Job Posting Says No",
];

function badgeClass(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("interview")) return "interview";
  if (s === "applied" || s.includes("review") || s.includes("contacted")) return "applied";
  if (s === "rejected" || s.includes("withdrawn")) return "rejected";
  if (s === "offer") return "offer";
  return "saved";
}

// --- Toast ------------------------------------------------------------------
function useToast() {
  const [msg, setMsg] = useState(null);
  const show = useCallback((m) => {
    setMsg(m);
    setTimeout(() => setMsg(null), 3000);
  }, []);
  const node = msg ? <div className="toast">{msg}</div> : null;
  return [node, show];
}

// --- Dashboard cards --------------------------------------------------------
function Cards({ stats }) {
  if (!stats) return null;
  const items = [
    { label: "Total Applications", value: stats.total_applications, cls: "accent" },
    { label: "Applied This Week", value: stats.applied_this_week, cls: "" },
    { label: "Interviews", value: stats.interviews, cls: "green" },
    { label: "Offers", value: stats.offers, cls: "amber" },
    { label: "Rejections", value: stats.rejections, cls: "red" },
    { label: "Pending Response", value: stats.pending_response, cls: "" },
    { label: "Follow-ups Due", value: stats.follow_ups_due, cls: "amber" },
    { label: "Saved (not applied)", value: stats.jobs_saved_not_applied, cls: "" },
  ];
  return (
    <div className="cards">
      {items.map((it) => (
        <div className="card" key={it.label}>
          <div className="label">{it.label}</div>
          <div className={"value " + it.cls}>{it.value}</div>
        </div>
      ))}
    </div>
  );
}

// --- Application modal ------------------------------------------------------
function AppModal({ initial, onClose, onSaved, showToast }) {
  const isEdit = !!initial;
  const [form, setForm] = useState(
    initial
      ? {
          status: initial.status,
          date_applied: initial.date_applied || "",
          response: initial.response || "",
          notes: initial.notes || "",
          application_url: initial.application_url || "",
        }
      : {
          company_name: "",
          position: "",
          link: "",
          location: "",
          status: "Applied",
          sponsorship_status: "Unknown",
          date_applied: new Date().toISOString().slice(0, 10),
          notes: "",
        }
  );
  const set = (k, v) => setForm({ ...form, [k]: v });

  async function save() {
    try {
      const body = { ...form };
      Object.keys(body).forEach((k) => body[k] === "" && (body[k] = null));
      if (isEdit) {
        await api(`/api/applications/${initial.id}`, {
          method: "PATCH", body: JSON.stringify(body),
        });
      } else {
        await api("/api/applications", {
          method: "POST", body: JSON.stringify(body),
        });
      }
      showToast(isEdit ? "Application updated" : "Application added");
      onSaved();
      onClose();
    } catch (e) {
      showToast("Error: " + e.message);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{isEdit ? "Edit Application" : "Add Application"}</h3>
        <div className="form-grid">
          {!isEdit && (
            <React.Fragment>
              <div>
                <label>Company</label>
                <input type="text" value={form.company_name}
                  onChange={(e) => set("company_name", e.target.value)} />
              </div>
              <div>
                <label>Position</label>
                <input type="text" value={form.position}
                  onChange={(e) => set("position", e.target.value)} />
              </div>
              <div className="full">
                <label>Job Link</label>
                <input type="text" value={form.link}
                  onChange={(e) => set("link", e.target.value)} />
              </div>
              <div>
                <label>Location</label>
                <input type="text" value={form.location}
                  onChange={(e) => set("location", e.target.value)} />
              </div>
              <div>
                <label>Visa Sponsorship</label>
                <select value={form.sponsorship_status}
                  onChange={(e) => set("sponsorship_status", e.target.value)}>
                  {SPONSORSHIP.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
            </React.Fragment>
          )}
          <div>
            <label>Status</label>
            <select value={form.status} onChange={(e) => set("status", e.target.value)}>
              {STATUSES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label>Date Applied</label>
            <input type="date" value={form.date_applied || ""}
              onChange={(e) => set("date_applied", e.target.value)} />
          </div>
          {isEdit && (
            <div className="full">
              <label>Response</label>
              <input type="text" value={form.response}
                onChange={(e) => set("response", e.target.value)} />
            </div>
          )}
          <div className="full">
            <label>Notes</label>
            <textarea rows="3" value={form.notes}
              onChange={(e) => set("notes", e.target.value)} />
          </div>
        </div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" onClick={save}>{isEdit ? "Save" : "Add"}</button>
        </div>
      </div>
    </div>
  );
}

// --- Applications table -----------------------------------------------------
function Applications({ reload, showToast }) {
  const [apps, setApps] = useState([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(undefined); // undefined=closed

  const load = useCallback(async () => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    if (statusFilter) q.set("status", statusFilter);
    const data = await api("/api/applications?" + q.toString());
    setApps(data);
  }, [search, statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function remove(id) {
    if (!confirm("Delete this application?")) return;
    await api(`/api/applications/${id}`, { method: "DELETE" });
    showToast("Deleted");
    load(); reload();
  }

  async function addFollowUp(app) {
    const days = 7;
    const due = new Date(Date.now() + days * 864e5).toISOString().slice(0, 10);
    await api("/api/followups", {
      method: "POST",
      body: JSON.stringify({ application_id: app.id, due_date: due, status: "Pending" }),
    });
    showToast("Follow-up scheduled in 7 days");
    reload();
  }

  return (
    <div className="section">
      <div className="toolbar">
        <input type="text" placeholder="Search title..." value={search}
          onChange={(e) => setSearch(e.target.value)} />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={() => setEditing(null)}>+ Add Application</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Company</th><th>Position</th><th>Status</th>
            <th>Sponsorship</th><th>Applied</th><th className="right">Ageing</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {apps.map((a) => (
            <tr key={a.id}>
              <td>{a.job.company ? a.job.company.name : "—"}</td>
              <td>{a.job.title}</td>
              <td><span className={"badge " + badgeClass(a.status)}>{a.status}</span></td>
              <td className="muted">{a.job.sponsorship_status}</td>
              <td className="muted">{a.date_applied || "—"}</td>
              <td className="right">
                <span className={a.ageing != null && a.ageing >= 7 ? "aging-warn" : "muted"}>
                  {a.ageing != null ? a.ageing + "d" : "—"}
                </span>
              </td>
              <td className="right">
                <button className="btn ghost" onClick={() => setEditing(a)}>Edit</button>{" "}
                <button className="btn secondary" onClick={() => addFollowUp(a)}>Follow-up</button>{" "}
                <button className="btn danger" onClick={() => remove(a.id)}>Del</button>
              </td>
            </tr>
          ))}
          {apps.length === 0 && (
            <tr><td colSpan="7" className="empty">No applications yet. Add one or import your Excel tracker.</td></tr>
          )}
        </tbody>
      </table>
      {editing !== undefined && (
        <AppModal initial={editing} showToast={showToast}
          onClose={() => setEditing(undefined)}
          onSaved={() => { load(); reload(); }} />
      )}
    </div>
  );
}

// --- Follow-ups -------------------------------------------------------------
function FollowUps({ reload, showToast }) {
  const [items, setItems] = useState([]);
  const load = useCallback(async () => {
    setItems(await api("/api/followups?pending_only=true"));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function markDone(id) {
    await api(`/api/followups/${id}`, {
      method: "PATCH", body: JSON.stringify({ status: "Done" }),
    });
    showToast("Follow-up marked done");
    load(); reload();
  }
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="section">
      <h2>Pending Follow-ups</h2>
      <table>
        <thead><tr><th>Due</th><th>Note</th><th className="right">Action</th></tr></thead>
        <tbody>
          {items.map((f) => (
            <tr key={f.id}>
              <td className={f.due_date <= today ? "aging-warn" : ""}>{f.due_date}</td>
              <td className="muted">{f.note || "Follow up on application"}</td>
              <td className="right"><button className="btn secondary" onClick={() => markDone(f.id)}>Done</button></td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan="3" className="empty">No pending follow-ups.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// --- Import / Export --------------------------------------------------------
function DataTools({ reload, showToast }) {
  const [busy, setBusy] = useState(false);
  async function onImport(e) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/excel/import", { method: "POST", body: fd });
      if (!res.ok) throw new Error((await res.json()).detail);
      const r = await res.json();
      let msg = `Imported ${r.imported}, ${r.duplicates} duplicates skipped`;
      if (r.credential_columns_ignored) msg += " (credential column ignored)";
      showToast(msg);
      reload();
    } catch (err) {
      showToast("Import failed: " + err.message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }
  return (
    <div className="section">
      <h2>Import / Export</h2>
      <div className="pill-note">
        Import your existing Excel tracker. Any username/password column is ignored on purpose —
        this app never stores portal credentials.
      </div>
      <div className="toolbar">
        <label className="btn secondary" style={{ cursor: "pointer" }}>
          {busy ? "Importing..." : "Import Excel"}
          <input type="file" accept=".xlsx,.xlsm" style={{ display: "none" }}
            onChange={onImport} disabled={busy} />
        </label>
        <a className="btn" href="/api/excel/export">Download Excel</a>
      </div>

      <h2 style={{ marginTop: 28 }}>H-1B Sponsor Data (DOL LCA)</h2>
      <div className="pill-note">
        Loads public DOL Labor Condition Application disclosure data to build a
        sponsor database. This shows <strong>filing history</strong> — it does
        not guarantee a company will sponsor a specific role. DOL sometimes
        blocks automated downloads; if that happens, download the file manually
        from the DOL performance page and use "Import DOL File".
      </div>
      <DolTools showToast={showToast} />
    </div>
  );
}

// --- DOL H-1B tools ---------------------------------------------------------
function DolTools({ showToast }) {
  const [ingests, setIngests] = useState([]);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");

  const load = useCallback(async () => {
    try { setIngests(await api("/api/h1b/ingests")); } catch (e) {}
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 3000); // poll while a job runs
    return () => clearInterval(t);
  }, [load]);

  async function startDownload() {
    setBusy(true);
    try {
      await api("/api/h1b/download", {
        method: "POST",
        body: JSON.stringify({ url: url || null }),
      });
      showToast("DOL download started (runs in background)");
      load();
    } catch (e) {
      showToast("Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function onImportFile(e, endpoint, label) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(endpoint, { method: "POST", body: fd });
      if (!res.ok) throw new Error((await res.json()).detail);
      const r = await res.json();
      showToast(r.message || (label + " imported"));
      load();
    } catch (err) {
      showToast("Import failed: " + err.message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div>
      <div className="toolbar">
        <input type="text" style={{ flex: 1, minWidth: 260 }}
          placeholder="DOL file URL (optional — uses default if blank)"
          value={url} onChange={(e) => setUrl(e.target.value)} />
        <button className="btn" onClick={startDownload} disabled={busy}>
          Auto-download & Import
        </button>
        <label className="btn secondary" style={{ cursor: "pointer" }}>
          Import DOL File
          <input type="file" accept=".xlsx,.csv,.txt" style={{ display: "none" }}
            onChange={(e) => onImportFile(e, "/api/h1b/import-file", "DOL file")}
            disabled={busy} />
        </label>
        <label className="btn secondary" style={{ cursor: "pointer" }}>
          Import USCIS File
          <input type="file" accept=".csv,.txt,.xlsx" style={{ display: "none" }}
            onChange={(e) => onImportFile(e, "/api/h1b/uscis/import-file", "USCIS file")}
            disabled={busy} />
        </label>
      </div>
      <div className="pill-note">
        <strong>USCIS H-1B Employer Data Hub</strong> is the other official
        source (actual petition approvals/denials). Download a fiscal-year CSV
        from the USCIS Employer Data Hub Files page and use "Import USCIS File".
        Note: h1bgrader.com and similar sites are built on this same public DOL +
        USCIS data, but they block scraping — so we use the primary sources
        directly.
      </div>
      {ingests.length > 0 && (
        <table>
          <thead><tr><th>Status</th><th>File</th><th>Rows</th><th>Companies</th><th>Message</th></tr></thead>
          <tbody>
            {ingests.map((i) => (
              <tr key={i.id}>
                <td><span className={"badge " + (i.status === "done" ? "interview" : i.status === "error" ? "rejected" : "applied")}>{i.status}</span></td>
                <td className="muted">{i.filename || "—"}</td>
                <td>{i.rows_read}</td>
                <td>{i.companies_upserted}</td>
                <td className="muted">{i.message || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// --- Sponsors tab -----------------------------------------------------------
function scoreClass(score) {
  if (score >= 70) return "green";
  if (score >= 40) return "amber";
  return "";
}

function Sponsors({ showToast }) {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [recentOnly, setRecentOnly] = useState(false);
  const [links, setLinks] = useState(null); // {company, career, jobs}

  const load = useCallback(async () => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    if (recentOnly) q.set("recent_only", "true");
    try { setRows(await api("/api/sponsors?" + q.toString())); }
    catch (e) { showToast("Error: " + e.message); }
  }, [search, recentOnly]);
  useEffect(() => { load(); }, [load]);

  async function showLinks(company, role) {
    const chosen = role || "Cybersecurity";
    const career = await api(`/api/sponsors/${company.id}/career-links`);
    const jobs = await api(
      `/api/sponsors/${company.id}/job-links?role=${encodeURIComponent(chosen)}`
    );
    setLinks({ company, career, jobs, role: chosen });
  }

  return (
    <div className="section">
      <h2>H-1B Sponsors (approval history)</h2>
      <div className="pill-note">
        Ranked by a 0–100 signal from H-1B petition volume + recency + approval
        rate (DOL LCA filings and USCIS approvals). Higher means a stronger H-1B
        <em> history</em>, not a guarantee for any specific role. Use "Links" to
        find each sponsor's careers page and search their open jobs.
      </div>
      <div className="toolbar">
        <input type="text" placeholder="Search company..." value={search}
          onChange={(e) => setSearch(e.target.value)} />
        <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0 }}>
          <input type="checkbox" checked={recentOnly}
            onChange={(e) => setRecentOnly(e.target.checked)} /> Recently sponsoring only
        </label>
      </div>
      <table>
        <thead>
          <tr>
            <th>Company</th><th className="right">Score</th><th className="right">Approvals</th>
            <th className="right">Recent</th><th className="right">Last FY</th>
            <th>Status</th><th className="right">Find Jobs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td className="right"><span className={"value " + scoreClass(c.sponsorship_score)} style={{ fontSize: 15, fontWeight: 700 }}>{c.sponsorship_score}</span></td>
              <td className="right muted">{((c.uscis_initial_approvals || 0) + (c.uscis_continuing_approvals || 0)) || c.h1b_filings_total}</td>
              <td className="right muted">{c.h1b_filings_recent || "—"}</td>
              <td className="right muted">{c.uscis_last_fiscal_year || c.h1b_last_filing_year || "—"}</td>
              <td className="muted">{c.sponsorship_status}</td>
              <td className="right"><button className="btn secondary" onClick={() => showLinks(c)}>Links</button></td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan="7" className="empty">No sponsors yet. Load DOL data from the Data tab.</td></tr>
          )}
        </tbody>
      </table>
      {links && (
        <div className="modal-overlay" onClick={() => setLinks(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{links.company.name}</h3>
            <p className="muted" style={{ fontSize: 13 }}>
              Top titles: {links.company.h1b_top_titles || "—"}<br />
              Top states: {links.company.h1b_top_states || "—"}<br />
              USCIS approvals: {(links.company.uscis_initial_approvals || 0) + (links.company.uscis_continuing_approvals || 0)}
              {" "}(denials: {(links.company.uscis_initial_denials || 0) + (links.company.uscis_continuing_denials || 0)})
              {links.company.uscis_last_fiscal_year ? `, last FY ${links.company.uscis_last_fiscal_year}` : ""}
            </p>
            <h4>Find their careers page</h4>
            {links.career.map((q, i) => (
              <div key={i} style={{ marginBottom: 6 }}>
                <a className="btn ghost" href={q.url} target="_blank" rel="noreferrer">{q.label}</a>
              </div>
            ))}
            <h4>Jobs at this company</h4>
            <div style={{ marginBottom: 10 }}>
              <label>Role to search for</label>
              <select value={links.role}
                onChange={(e) => showLinks(links.company, e.target.value)}>
                {["Cybersecurity", "Cybersecurity Analyst", "SOC Analyst",
                  "Security Engineer", "Cloud Security Engineer",
                  "Information Security Analyst", "Incident Response Analyst",
                  "DevSecOps Engineer", "Network Security Engineer"]
                  .map((r) => <option key={r}>{r}</option>)}
              </select>
            </div>
            {links.jobs.map((q, i) => (
              <div key={i} style={{ marginBottom: 6 }}>
                <a className="btn ghost" href={q.url} target="_blank" rel="noreferrer">{q.label}</a>
              </div>
            ))}
            <div className="modal-actions">
              <button className="btn" onClick={() => setLinks(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Jobs tab (live ATS postings + bulletin search) -------------------------
const JOB_STATUSES = [
  "Applied", "Saved", "Ready to Apply", "Under Review", "Recruiter Contacted",
  "Interview", "Technical Interview", "Final Interview", "Offer",
  "Rejected", "Withdrawn", "No Response", "Closed",
];

function Jobs({ reload, showToast }) {
  const [jobs, setJobs] = useState([]);
  const [search, setSearch] = useState("");
  const [onlyUnapplied, setOnlyUnapplied] = useState(true);
  const [entryOnly, setEntryOnly] = useState(false);
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [includeSponsors, setIncludeSponsors] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fetchRun, setFetchRun] = useState(null);

  // Bulletin (Google-dork) search state.
  const [options, setOptions] = useState({ roles: [], targets: [] });
  const [role, setRole] = useState("SOC Analyst");
  const [locationMode, setLocationMode] = useState("any"); // remote|onsite|any
  const [exclusions, setExclusions] = useState("jobgether");
  const [selectedTargets, setSelectedTargets] = useState([]);
  const [queries, setQueries] = useState([]);

  const load = useCallback(async () => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    if (onlyUnapplied) q.set("only_unapplied", "true");
    try { setJobs(await api("/api/jobs?" + q.toString())); }
    catch (e) { showToast("Error: " + e.message); }
  }, [search, onlyUnapplied]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api("/api/discover/options").then((o) => {
      setOptions(o);
      if (o.roles && o.roles.length) setRole(o.roles[0]);
    }).catch(() => {});
  }, []);

  async function fetchJobs() {
    setBusy(true);
    setFetchRun(null);
    try {
      const run = await api("/api/jobs/fetch", {
        method: "POST",
        body: JSON.stringify({
          entry_only: entryOnly, remote_only: remoteOnly,
          include_sponsors: includeSponsors,
        }),
      });
      showToast("Fetching live jobs in the background...");
      pollRun(run.id);
    } catch (e) {
      showToast("Error: " + e.message);
      setBusy(false);
    }
  }

  function pollRun(id) {
    const tick = async () => {
      try {
        const r = await api(`/api/jobs/fetch/${id}`);
        setFetchRun(r);
        if (r.status === "done" || r.status === "error") {
          setBusy(false);
          if (r.status === "done") {
            showToast(`Done: ${r.cyber_matched} cyber roles, added ${r.inserted}`);
            load();
          } else {
            showToast("Fetch error: " + (r.message || "unknown"));
          }
          return;
        }
      } catch (e) { /* keep polling */ }
      setTimeout(tick, 2000);
    };
    tick();
  }

  async function generateLinks() {
    try {
      const body = {
        role,
        location_mode: locationMode,
        exclusions: exclusions.split(",").map((s) => s.trim()).filter(Boolean),
        targets: selectedTargets,
      };
      setQueries(await api("/api/discover/queries", {
        method: "POST", body: JSON.stringify(body),
      }));
    } catch (e) {
      showToast("Error: " + e.message);
    }
  }

  function toggleTarget(key) {
    setSelectedTargets((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]);
  }

  async function apply(job, status) {
    try {
      await api(`/api/jobs/${job.id}/apply`, {
        method: "POST", body: JSON.stringify({ status }),
      });
      showToast(`Added to tracker as "${status}"`);
      load(); reload();
    } catch (e) {
      showToast("Error: " + e.message);
    }
  }

  function sponsorBadge(status) {
    if (status === "Confirmed Yes") return "interview";
    if (status === "Currently Sponsoring" || status === "Previously Sponsored") return "applied";
    return "saved";
  }

  return (
    <div>
      <div className="section">
        <h2>Jobs — live cybersecurity roles (company career boards)</h2>
        <div className="pill-note">
          Pulls <strong>currently-open</strong> cybersecurity jobs directly from
          company career boards via their official ATS APIs
          (Greenhouse, Lever, Ashby). Closed roles never appear. Every job links
          straight to the company's own application page. Set a job's status
          (Applied, Saved, Closed, Rejected, Interview...) to add it to your
          tracker.
        </div>
        <div className="toolbar">
          <button className="btn" onClick={fetchJobs} disabled={busy}>
            {busy ? "Fetching..." : "Fetch Live Jobs"}
          </button>
          <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0 }}>
            <input type="checkbox" checked={entryOnly}
              onChange={(e) => setEntryOnly(e.target.checked)} /> Entry-level only
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0 }}>
            <input type="checkbox" checked={remoteOnly}
              onChange={(e) => setRemoteOnly(e.target.checked)} /> Remote only
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0 }}>
            <input type="checkbox" checked={includeSponsors}
              onChange={(e) => setIncludeSponsors(e.target.checked)} /> Include H-1B sponsors
          </label>
          <div style={{ flex: 1 }} />
          <input type="text" placeholder="Search title..." value={search}
            onChange={(e) => setSearch(e.target.value)} />
          <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0 }}>
            <input type="checkbox" checked={onlyUnapplied}
              onChange={(e) => setOnlyUnapplied(e.target.checked)} /> Hide tracked
          </label>
        </div>
        {fetchRun && fetchRun.status !== "done" && (
          <div className="pill-note">
            Fetch status: <strong>{fetchRun.status}</strong> — queried{" "}
            {fetchRun.companies_queried} companies, {fetchRun.cyber_matched} cyber
            roles found, {fetchRun.inserted} added so far.
          </div>
        )}
        <table>
          <thead>
            <tr>
              <th>Company</th><th>Title</th><th>Location</th>
              <th>Sponsorship</th><th>Posted</th><th className="right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.company ? j.company.name : "—"}</td>
                <td>{j.title}</td>
                <td className="muted">{j.location || "—"}</td>
                <td><span className={"badge " + sponsorBadge(j.sponsorship_status)}>{j.sponsorship_status}</span></td>
                <td className="muted">{j.date_discovered || "—"}</td>
                <td className="right">
                  {j.job_url && (
                    <a className="btn ghost" href={j.job_url} target="_blank" rel="noreferrer">Open</a>
                  )}{" "}
                  <select defaultValue=""
                    onChange={(e) => { if (e.target.value) { apply(j, e.target.value); e.target.value = ""; } }}
                    title="Add to tracker with this status">
                    <option value="" disabled>Set status…</option>
                    {JOB_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr><td colSpan="6" className="empty">No jobs yet. Click "Fetch Live Jobs".</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="section">
        <h2>Find more jobs — bulletin search (remote &amp; on-site USA)</h2>
        <div className="pill-note">
          Generates ready-to-click search links across ATS platforms (the
          bulletin / Google-dork method). Pick a role and location mode, then
          open the links to browse real postings and apply. On-site targets
          jobs in the United States and excludes remote-only listings.
        </div>
        <div className="form-grid">
          <div>
            <label>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {options.roles.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label>Location</label>
            <select value={locationMode} onChange={(e) => setLocationMode(e.target.value)}>
              <option value="any">Any (remote or on-site)</option>
              <option value="remote">Remote</option>
              <option value="onsite">On-site (USA)</option>
            </select>
          </div>
          <div className="full">
            <label>Exclusions (comma-separated)</label>
            <input type="text" value={exclusions}
              onChange={(e) => setExclusions(e.target.value)} />
          </div>
          <div className="full">
            <label>ATS targets (none = all)</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {options.targets.map((t) => (
                <button key={t.key}
                  className={"tab " + (selectedTargets.includes(t.key) ? "active" : "")}
                  onClick={() => toggleTarget(t.key)}>{t.label}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="toolbar" style={{ marginTop: 14 }}>
          <button className="btn" onClick={generateLinks}>Generate Search Links</button>
        </div>
        {queries.length > 0 && (
          <table>
            <thead><tr><th>Platform</th><th>Query</th><th className="right">Open</th></tr></thead>
            <tbody>
              {queries.map((q, i) => (
                <tr key={i}>
                  <td>{q.label}</td>
                  <td className="muted" style={{ fontFamily: "monospace", fontSize: 12 }}>{q.query}</td>
                  <td className="right"><a className="btn secondary" href={q.url} target="_blank" rel="noreferrer">Search</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// --- Resume / ATS match tab -------------------------------------------------
// Francis's base resume, used as the default master resume. Editable in the
// UI and overridable via localStorage ("masterResume").
const DEFAULT_RESUME = `FRANCIS ANTHONY KONIKKARA
College Park, MD 20740 | +1 240-960-3581 | francisanthony0328@gmail.com
linkedin.com/in/francis-anthony-konikkara-5721021bb | github.com/franciskonikkara
Open to Relocation Within the USA

SUMMARY
Cybersecurity graduate student with hands-on Security Operations Center (SOC) monitoring, incident response, and penetration testing experience across enterprise and cloud environments. CEH certified with practical experience triaging real-time security alerts, correlating logs across SIEM and EDR platforms (CrowdStrike, Microsoft Defender, Microsoft Sentinel, Splunk, ELK), and investigating network, cloud, and host-based security events. Solid understanding of TCP/IP, Windows systems administration (Active Directory), Linux, and the MITRE ATT&CK framework. CTF competitor and strong collaborator seeking to bring front-line triage and forensic analysis skills to a Cyber Triage and Forensics team.

TECHNICAL SKILLS
SOC Monitoring & Triage, Incident Response, Security Event & Log Correlation, Threat Detection & Investigation, Network Security, Host-Based Security, Cloud Security (AWS, Azure, GCP), Endpoint Detection & Response (CrowdStrike, Microsoft Defender, Microsoft Sentinel), SIEM (Splunk, ELK), Intrusion Detection Systems, TCP/IP, Windows Systems Administration & Active Directory, Linux Hardening, Penetration Testing, Vulnerability Assessment, MITRE ATT&CK, OWASP Top 10, Nessus, Metasploit, Burp Suite, Wireshark, Nmap, OSINT, Digital Forensics, Malware Analysis, Docker, Kubernetes, Terraform, CI/CD Security, Zero Trust, Python, Go, JavaScript, TypeScript, Bash, PowerShell, SQL, Git, GitHub

EXPERIENCE
Cybersecurity Intern | Nidec Motor Corporation | Jun 2026 - Aug 2026
- Performed front-line, real-time monitoring and triage of security alerts as part of the Security Operations Center (SOC) team, correlating logs across multiple security devices to determine true-positive security incidents
- Investigated network, cloud, and host-based security events using CrowdStrike and Microsoft security tools (Defender, Sentinel) for endpoint detection, threat hunting, and incident investigation
- Conducted cloud security assessments and penetration testing to identify vulnerabilities and misconfigurations across enterprise cloud environments
- Documented investigation findings and followed defined procedures for escalating and mitigating confirmed security incidents

Analyst | Deloitte Touche Tohmatsu LLP | Oct 2023 - Jul 2025
- Supported security-adjacent analytics and machine learning workflows using Python and JavaScript, including secure data handling and model evaluation pipelines
- Worked across cloud platforms (AWS, Azure) supporting enterprise-scale analytics environments while coordinating deliverables across cross-functional teams and maintaining compliance requirements

Full Stack Development Intern | Zedex Info Pvt. Ltd | Jul 2022 - Apr 2023
- Designed and deployed a secure web-based ERP system using React, Node.js, and GraphQL, implementing authentication, authorization, and API security controls. Integrated third-party APIs while enforcing validation, secure logging, and error-handling.

Information Security Analyst Intern | CybersmithSecure Pvt Ltd | Apr 2021 - Aug 2021
- Conducted vulnerability assessments and penetration testing using Nessus, Burp Suite, and Metasploit, identifying web, network, and configuration vulnerabilities
- Authored detailed technical reports and collaborated with senior analysts on threat categorization and remediation planning

EDUCATION
University of Maryland - College Park, MD | Master of Engineering in Cybersecurity
University of Mumbai - Mumbai, India | Bachelor of Engineering in Computer Engineering

KEY SECURITY PROJECTS
SIEM & Detection Engineering Lab: Built a SIEM platform using the ELK stack to ingest, normalize, and analyze security logs. Developed detection rules mapped to MITRE ATT&CK techniques and validated alerts to support SOC triage and incident response workflows.
Malware Analysis Lab: Performed static and dynamic analysis of Windows and Linux malware samples; extracted IOCs and documented findings using reverse engineering and sandboxing techniques.
Secure CI/CD Pipeline (DevSecOps): Designed a compliance-ready CI/CD pipeline with embedded SAST, secrets scanning, and container vulnerability scanning, aligned with SOC 2 and ISO/IEC 27001 controls.

CERTIFICATIONS & ACTIVITIES
Certifications: Certified Ethical Hacker (CEH), Practical Ethical Hacking (TCM Security), Cisco Packet Tracer, AI for Everyone
CTF Competitions: UMBC Nightwing CTF (3rd Place), Fword CTF, Cyber Apocalypse CTF.
Leadership: President, Agnel Cyber Cell - led cybersecurity workshops and training; content reached 22K+ viewers`;

function ResumeMatch({ showToast }) {
  const [resume, setResume] = useState(() => localStorage.getItem("masterResume") || DEFAULT_RESUME);
  const [jd, setJd] = useState("");
  const [result, setResult] = useState(null);
  const [tailored, setTailored] = useState(null);
  const [busy, setBusy] = useState(false);

  function saveResume() {
    localStorage.setItem("masterResume", resume);
    showToast("Master resume saved in this browser");
  }

  async function run() {
    if (!resume.trim() || !jd.trim()) {
      showToast("Paste both your resume and the job description");
      return;
    }
    setBusy(true);
    try {
      const [m, t] = await Promise.all([
        api("/api/resume/match", {
          method: "POST", body: JSON.stringify({ resume, job_description: jd }),
        }),
        api("/api/resume/tailor", {
          method: "POST", body: JSON.stringify({ resume, job_description: jd }),
        }),
      ]);
      setResult(m);
      setTailored(t);
    } catch (e) {
      showToast("Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  function copyTailored() {
    navigator.clipboard.writeText(tailored.tailored_resume).then(
      () => showToast("Tailored resume copied"),
      () => showToast("Copy failed — select and copy manually")
    );
  }

  function scoreColor(v) {
    if (v >= 75) return "green";
    if (v >= 50) return "amber";
    return "red";
  }

  return (
    <div className="section">
      <h2>Resume Tailoring &amp; ATS Match</h2>
      <div className="pill-note">
        Save your master resume once. Each time you paste a job description and
        click <strong>Tailor Resume</strong>, it rewrites your resume — adding a
        JD-targeted summary and a Core Competencies block that naturally weaves
        in the keywords you already back up, to raise your ATS score. Keywords
        the JD wants that aren't in your resume are listed separately as
        "consider adding" — <strong>never fabricated</strong> into your
        experience.
      </div>
      <div className="form-grid">
        <div>
          <label>Master Resume (plain text)</label>
          <textarea rows="12" value={resume}
            onChange={(e) => setResume(e.target.value)}
            placeholder="Paste your full resume text once..." />
          <button className="btn ghost" style={{ marginTop: 6 }} onClick={saveResume}>
            Save resume in browser
          </button>
        </div>
        <div>
          <label>Job Description</label>
          <textarea rows="12" value={jd}
            onChange={(e) => setJd(e.target.value)}
            placeholder="Paste the job description..." />
          <button className="btn" style={{ marginTop: 6 }} onClick={run} disabled={busy}>
            {busy ? "Working..." : "Tailor Resume"}
          </button>
        </div>
      </div>

      {result && tailored && (
        <div style={{ marginTop: 20 }}>
          <div className="cards">
            <div className="card">
              <div className="label">ATS Before</div>
              <div className={"value " + scoreColor(tailored.before_score)}>{tailored.before_score}%</div>
            </div>
            <div className="card">
              <div className="label">ATS After (tailored)</div>
              <div className={"value " + scoreColor(tailored.after_score)}>{tailored.after_score}%</div>
            </div>
            <div className="card">
              <div className="label">Skills Matched</div>
              <div className={"value " + scoreColor(result.skills_match)}>{result.matched_skills.length}/{result.jd_skills.length}</div>
            </div>
          </div>

          <h4 style={{ marginTop: 16 }}>Tailored resume (review, edit, then use)</h4>
          <textarea rows="20" value={tailored.tailored_resume} readOnly
            style={{ width: "100%", fontFamily: "monospace", fontSize: 12 }} />
          <div className="toolbar" style={{ marginTop: 8 }}>
            <button className="btn secondary" onClick={copyTailored}>Copy Tailored Resume</button>
          </div>

          <div className="form-grid" style={{ marginTop: 12 }}>
            <div>
              <h4 style={{ color: "var(--green)" }}>Woven in ({tailored.injected_keywords.length})</h4>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {tailored.injected_keywords.map((s) => (
                  <span key={s} className="badge interview">{s}</span>
                ))}
                {tailored.injected_keywords.length === 0 && <span className="muted">None yet — add more real skills to your resume</span>}
              </div>
            </div>
            <div>
              <h4 style={{ color: "var(--amber)" }}>Consider adding — only if genuinely true ({tailored.gap_keywords.length})</h4>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {tailored.gap_keywords.map((s) => (
                  <span key={s} className="badge saved">{s}</span>
                ))}
                {tailored.gap_keywords.length === 0 && <span className="muted">None — great coverage</span>}
              </div>
            </div>
          </div>

          {tailored.notes.map((n, i) => (
            <div key={i} className="pill-note" style={{ marginTop: 8 }}>{n}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Outreach tab -----------------------------------------------------------
const OUTREACH_KINDS = [
  { key: "recruiter_email", label: "Recruiter Email" },
  { key: "referral_request", label: "Referral Request" },
  { key: "follow_up", label: "Follow-up Email" },
  { key: "linkedin_connection", label: "LinkedIn Connection Note" },
  { key: "linkedin_message", label: "LinkedIn Message" },
  { key: "cover_letter", label: "Cover Letter" },
];

function Outreach({ showToast }) {
  const [form, setForm] = useState(() => ({
    kind: "recruiter_email",
    company: "",
    role: "",
    contact_name: "",
    your_name: localStorage.getItem("yourName") || "",
    your_background: localStorage.getItem("yourBackground") || "",
    highlight: "",
    shared_context: "",
  }));
  const [draft, setDraft] = useState(null);
  const set = (k, v) => setForm({ ...form, [k]: v });

  async function generate() {
    try {
      localStorage.setItem("yourName", form.your_name);
      localStorage.setItem("yourBackground", form.your_background);
      setDraft(await api("/api/outreach/draft", {
        method: "POST", body: JSON.stringify(form),
      }));
    } catch (e) {
      showToast("Error: " + e.message);
    }
  }

  function copy() {
    const text = draft.subject ? draft.subject + "\n\n" + draft.body : draft.body;
    navigator.clipboard.writeText(text).then(
      () => showToast("Copied to clipboard"),
      () => showToast("Copy failed — select and copy manually")
    );
  }

  return (
    <div className="section">
      <h2>Outreach Drafts</h2>
      <div className="pill-note">
        Generates a first draft you review and send yourself. Nothing is sent
        automatically. Fill in your real details — the templates never invent
        experience. For LinkedIn, send manually (automation violates their
        terms).
      </div>
      <div className="form-grid">
        <div>
          <label>Type</label>
          <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
            {OUTREACH_KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </div>
        <div>
          <label>Company</label>
          <input type="text" value={form.company} onChange={(e) => set("company", e.target.value)} />
        </div>
        <div>
          <label>Role</label>
          <input type="text" value={form.role} onChange={(e) => set("role", e.target.value)} />
        </div>
        <div>
          <label>Contact name</label>
          <input type="text" value={form.contact_name} onChange={(e) => set("contact_name", e.target.value)} />
        </div>
        <div>
          <label>Your name</label>
          <input type="text" value={form.your_name} onChange={(e) => set("your_name", e.target.value)} />
        </div>
        <div>
          <label>Your background</label>
          <input type="text" value={form.your_background}
            placeholder="Master's in Cybersecurity at UMD"
            onChange={(e) => set("your_background", e.target.value)} />
        </div>
        <div className="full">
          <label>One real highlight (accomplishment / skill)</label>
          <input type="text" value={form.highlight}
            placeholder="I built a SOC lab using Splunk and automated detection with Python"
            onChange={(e) => set("highlight", e.target.value)} />
        </div>
        <div className="full">
          <label>Shared context (optional — alumni, mutual connection, event)</label>
          <input type="text" value={form.shared_context}
            placeholder="are both UMD alumni"
            onChange={(e) => set("shared_context", e.target.value)} />
        </div>
      </div>
      <div className="toolbar" style={{ marginTop: 14 }}>
        <button className="btn" onClick={generate}>Generate Draft</button>
      </div>

      {draft && (
        <div style={{ marginTop: 16 }}>
          {draft.subject && (
            <p><strong>Subject:</strong> {draft.subject}</p>
          )}
          <textarea rows="14" value={draft.body} readOnly
            style={{ width: "100%" }} />
          <div className="toolbar" style={{ marginTop: 8 }}>
            <button className="btn secondary" onClick={copy}>Copy</button>
          </div>
        </div>
      )}
    </div>
  );
}

// --- App shell --------------------------------------------------------------
function App() {
  const [tab, setTab] = useState("dashboard");
  const [stats, setStats] = useState(null);
  const [toast, showToast] = useToast();

  const loadStats = useCallback(async () => {
    try { setStats(await api("/api/dashboard/stats")); }
    catch (e) { showToast("Cannot reach API: " + e.message); }
  }, []);
  useEffect(() => { loadStats(); }, [loadStats]);

  return (
    <div>
      <div className="topbar">
        <div className="brand">
          <span className="dot">◆</span>
          <h1>H-1B Cyber Job Copilot</h1>
        </div>
        <span className="muted">Phase 2</span>
      </div>
      <div className="container">
        <div className="tabs">
          {["dashboard", "applications", "jobs", "sponsors", "resume", "outreach", "follow-ups", "data"].map((t) => (
            <button key={t} className={"tab " + (tab === t ? "active" : "")}
              onClick={() => setTab(t)}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        {tab === "dashboard" && (
          <React.Fragment>
            <Cards stats={stats} />
            <Applications reload={loadStats} showToast={showToast} />
          </React.Fragment>
        )}
        {tab === "applications" && <Applications reload={loadStats} showToast={showToast} />}
        {tab === "jobs" && <Jobs reload={loadStats} showToast={showToast} />}
        {tab === "sponsors" && <Sponsors showToast={showToast} />}
        {tab === "resume" && <ResumeMatch showToast={showToast} />}
        {tab === "outreach" && <Outreach showToast={showToast} />}
        {tab === "follow-ups" && <FollowUps reload={loadStats} showToast={showToast} />}
        {tab === "data" && <DataTools reload={loadStats} showToast={showToast} />}
      </div>
      {toast}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
