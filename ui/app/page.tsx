"use client";
import { useEffect, useRef, useState } from "react";
import { getAuth, GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signOut, User } from "firebase/auth";
import firebaseApp from "../lib/firebase";

const API = "http://127.0.0.1:4849";
const auth = getAuth(firebaseApp);
const provider = new GoogleAuthProvider();
provider.setCustomParameters({ prompt: "select_account" });

export default function Home() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [pin, setPin] = useState("");
  const [minutes, setMinutes] = useState(15);
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [children, setChildren] = useState<any[]>([]);
  const [childSettings, setChildSettings] = useState<Record<string, { strictness: string; age: number }>>({});
  const [selectedChild, setSelectedChild] = useState<string | null>(null);
  const [savingChild, setSavingChild] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (nextUser) => {
      setUser(nextUser);
      setAuthReady(true);
      if (!nextUser) {
        setDecisions([]);
        setChildren([]);
        setChildSettings({});
        setSelectedChild(null);
        if (esRef.current) {
          esRef.current.close();
          esRef.current = null;
        }
      }
    });
    return () => unsub();
  }, []);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;

    fetch(`${API}/v1/decisions?limit=50`)
      .then((r) => r.json())
      .then((j) => {
        if (!cancelled) setDecisions(j.decisions || []);
      })
      .catch(() => {});

    const es = new EventSource(`${API}/v1/stream/decisions`);
    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        setDecisions((prev) => [msg, ...prev].slice(0, 200));
      } catch {}
    };
    es.onerror = () => {};
    esRef.current = es;

    return () => {
      cancelled = true;
      es.close();
    };
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    fetch(`${API}/v1/children`)
      .then((r) => r.json())
      .then((j) => {
        if (cancelled) return;
        const list = j.children || [];
        setChildren(list);
        const map: Record<string, { strictness: string; age: number }> = {};
        list.forEach((child: any) => {
          map[child.id] = {
            strictness: child.strictness || "standard",
            age: child.age || 12,
          };
        });
        setChildSettings(map);
        setSelectedChild((prev) => {
          if (!list.length) {
            return null;
          }
          if (!prev || !list.some((child: any) => child.id === prev)) {
            return list[0].id;
          }
          return prev;
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user]);

  const currentChild = selectedChild ? childSettings[selectedChild] : null;

  const pause = async () => {
    await fetch(`${API}/v1/control/pause`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ pin, minutes }),
    });
  };
  const resume = async () => {
    await fetch(`${API}/v1/control/resume`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ pin }),
    });
  };

  const signIn = async () => {
    await signInWithPopup(auth, provider);
  };

  const logout = async () => {
    await signOut(auth);
  };

  const updateChildSetting = (field: "strictness" | "age", value: string) => {
    if (!selectedChild) return;
    setChildSettings((prev) => ({
      ...prev,
      [selectedChild]: {
        ...(prev[selectedChild] || { strictness: "standard", age: 12 }),
        [field]:
          field === "age"
            ? Math.min(18, Math.max(3, parseInt(value || "0", 10) || 3))
            : value,
      },
    }));
  };

  const saveChildSettings = async () => {
    if (!selectedChild || !currentChild) return;
    setSavingChild(true);
    try {
      await fetch(`${API}/v1/children/${selectedChild}/settings`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          strictness: currentChild.strictness,
          age: currentChild.age,
        }),
      });
    } finally {
      setSavingChild(false);
    }
  };

  if (!authReady) {
    return (
      <main style={{ padding: 24, fontFamily: "ui-sans-serif" }}>
        <h1>WatchIt Dashboard</h1>
        <p>Loading authentication...</p>
      </main>
    );
  }

  if (!user) {
    return (
      <div style={{ minHeight: "100vh", background: "radial-gradient(circle at top,#1f3b73,#0b1220)", color: "#fff", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", gap: 16, fontFamily: "Inter, ui-sans-serif" }}>
        <h1 style={{ fontSize: 40, fontWeight: 700 }}>WatchIt Guardian Console</h1>
        <p style={{ maxWidth: 420, opacity: 0.85 }}>Sign in with your guardian Google account to review activity, adjust strictness, and pause monitoring.</p>
        <button onClick={signIn} style={{ padding: "12px 28px", borderRadius: 999, border: "none", background: "#3b82f6", color: "#fff", fontSize: 16, fontWeight: 600, cursor: "pointer" }}>
          Sign in with Google
        </button>
      </div>
    );
  }

  const latest = decisions[0];
  const decisionsToday = decisions.filter((d) => {
    const ts = Number(d.ts ?? 0);
    const date = new Date(ts);
    const today = new Date();
    return date.toDateString() === today.toDateString();
  }).length;
  const actionBadge = (action: string) => {
    const palette: Record<string, string> = {
      allow: "#22c55e",
      block: "#ef4444",
    };
    return (
      <span style={{ padding: "4px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, color: "#fff", background: palette[action] || "#f97316", textTransform: "uppercase", letterSpacing: 0.8 }}>
        {action}
      </span>
    );
  };

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(135deg,#020617,#0f172a 50%,#1e293b)", color: "#e2e8f0", fontFamily: "Inter, ui-sans-serif", padding: "32px 0" }}>
      <div style={{ width: "min(1100px, 92vw)", margin: "0 auto" }}>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
          <div>
            <p style={{ margin: 0, color: "#94a3b8", fontSize: 13 }}>Guardian Dashboard</p>
            <h1 style={{ margin: 0, fontSize: 32, fontWeight: 700 }}>WatchIt</h1>
            <p style={{ margin: 4, color: "#94a3b8" }}>Signed in as {user.displayName || user.email}</p>
          </div>
          <button onClick={logout} style={{ padding: "10px 18px", borderRadius: 12, border: "1px solid rgba(148,163,184,.4)", background: "transparent", color: "#e2e8f0", cursor: "pointer" }}>
            Sign out
          </button>
        </header>

        <section style={{ marginTop: 32, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 20 }}>
          <div style={{ background: "rgba(15,23,42,.8)", borderRadius: 20, padding: 20, border: "1px solid rgba(148,163,184,.2)" }}>
            <p style={{ margin: 0, color: "#94a3b8", fontSize: 13 }}>Latest action</p>
            <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10 }}>
              {latest ? actionBadge(latest.action) : <span style={{ color: "#94a3b8" }}>No data yet</span>}
              {latest && <span style={{ color: "#cbd5f5", fontSize: 14 }}>{latest.reason}</span>}
            </div>
          </div>
          <div style={{ background: "rgba(15,23,42,.8)", borderRadius: 20, padding: 20, border: "1px solid rgba(148,163,184,.2)" }}>
            <p style={{ margin: 0, color: "#94a3b8", fontSize: 13 }}>Events today</p>
            <h2 style={{ margin: "12px 0 0", fontSize: 28 }}>{decisionsToday}</h2>
          </div>
          <div style={{ background: "rgba(15,23,42,.8)", borderRadius: 20, padding: 20, border: "1px solid rgba(148,163,184,.2)" }}>
            <p style={{ margin: 0, color: "#94a3b8", fontSize: 13 }}>Stream</p>
            <p style={{ marginTop: 12, color: "#34d399", fontWeight: 600 }}>Live</p>
          </div>
        </section>

        <section style={{ marginTop: 32, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 24 }}>
          <div style={{ background: "rgba(15,23,42,.85)", borderRadius: 20, padding: 24, border: "1px solid rgba(148,163,184,.2)", boxShadow: "0 10px 40px rgba(8,15,40,.35)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>Monitoring Controls</h2>
              <span style={{ padding: "4px 12px", borderRadius: 999, background: "#0f172a", fontSize: 12, color: "#38bdf8" }}>PIN gated</span>
            </div>
            <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 14 }}>
              <input placeholder="Parent PIN" value={pin} onChange={(e) => setPin(e.target.value)} style={{ padding: "10px 12px", borderRadius: 12, border: "1px solid rgba(148,163,184,.3)", background: "rgba(15,23,42,.6)", color: "#e2e8f0" }} />
              <input type="number" min={1} value={minutes} onChange={(e) => setMinutes(parseInt(e.target.value || "15"))} style={{ padding: "10px 12px", borderRadius: 12, border: "1px solid rgba(148,163,184,.3)", background: "rgba(15,23,42,.6)", color: "#e2e8f0" }} />
              <div style={{ display: "flex", gap: 12 }}>
                <button onClick={pause} style={{ flex: 1, padding: "10px 0", borderRadius: 12, border: "none", background: "#f97316", color: "#fff", fontWeight: 600, cursor: "pointer" }}>Pause</button>
                <button onClick={resume} style={{ flex: 1, padding: "10px 0", borderRadius: 12, border: "1px solid rgba(148,163,184,.4)", background: "transparent", color: "#e2e8f0", fontWeight: 600, cursor: "pointer" }}>Resume</button>
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(15,23,42,.85)", borderRadius: 20, padding: 24, border: "1px solid rgba(148,163,184,.2)", boxShadow: "0 10px 40px rgba(8,15,40,.35)" }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Child Profile Controls</h2>
            {children.length === 0 ? (
              <p style={{ color: "#94a3b8", marginTop: 16 }}>No child profiles synced yet.</p>
            ) : (
              <>
                <label style={{ display: "block", marginTop: 16, fontSize: 14, color: "#cbd5f5" }}>
                  Child
                  <select style={{ marginTop: 6, width: "100%", padding: "10px 12px", borderRadius: 12, border: "1px solid rgba(148,163,184,.3)", background: "rgba(15,23,42,.6)", color: "#e2e8f0" }} value={selectedChild || ""} onChange={(e) => setSelectedChild(e.target.value)}>
                    <option value="" disabled>
                      Choose...
                    </option>
                    {children.map((child) => (
                      <option key={child.id} value={child.id}>
                        {child.name || child.id}
                      </option>
                    ))}
                  </select>
                </label>

                {currentChild && (
                  <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 14 }}>
                    <label style={{ fontSize: 14, color: "#cbd5f5" }}>
                      Strictness
                      <select style={{ marginTop: 6, width: "100%", padding: "10px 12px", borderRadius: 12, border: "1px solid rgba(148,163,184,.3)", background: "rgba(15,23,42,.6)", color: "#e2e8f0" }} value={currentChild.strictness} onChange={(e) => updateChildSetting("strictness", e.target.value)}>
                        <option value="lenient">Lenient</option>
                        <option value="standard">Standard</option>
                        <option value="strict">Strict</option>
                      </select>
                    </label>
                    <label style={{ fontSize: 14, color: "#cbd5f5" }}>
                      Age
                      <input style={{ marginTop: 6, width: "100%", padding: "10px 12px", borderRadius: 12, border: "1px solid rgba(148,163,184,.3)", background: "rgba(15,23,42,.6)", color: "#e2e8f0" }} type="number" min={3} max={18} value={currentChild.age} onChange={(e) => updateChildSetting("age", e.target.value)} />
                    </label>
                    <button onClick={saveChildSettings} disabled={savingChild} style={{ padding: "10px 0", borderRadius: 12, border: "none", background: "#3b82f6", color: "#fff", fontWeight: 600, cursor: "pointer" }}>
                      {savingChild ? "Saving..." : "Save changes"}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <section style={{ marginTop: 32, background: "rgba(2,6,23,.8)", borderRadius: 20, border: "1px solid rgba(148,163,184,.2)", boxShadow: "0 15px 50px rgba(2,6,23,.6)", overflow: "hidden" }}>
          <div style={{ padding: "20px 24px", borderBottom: "1px solid rgba(148,163,184,.15)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <p style={{ margin: 0, color: "#94a3b8", fontSize: 13 }}>Live Feed</p>
              <h2 style={{ margin: "6px 0 0", fontSize: 20 }}>Recent Decisions</h2>
            </div>
            <span style={{ color: "#94a3b8", fontSize: 13 }}>{decisions.length} items</span>
          </div>
          <div style={{ maxHeight: 420, overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ textAlign: "left", background: "rgba(15,23,42,.7)", color: "#94a3b8" }}>
                  <th style={{ padding: "12px 20px" }}>When</th>
                  <th style={{ padding: "12px 20px" }}>Action</th>
                  <th style={{ padding: "12px 20px" }}>Reason</th>
                  <th style={{ padding: "12px 20px" }}>Title</th>
                  <th style={{ padding: "12px 20px" }}>URL</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d, i) => (
                  <tr key={i} style={{ borderTop: "1px solid rgba(148,163,184,.15)" }}>
                    <td style={{ padding: "12px 20px", color: "#e2e8f0" }}>{new Date(Number(d.ts ?? Date.now())).toLocaleTimeString()}</td>
                    <td style={{ padding: "12px 20px" }}>{actionBadge(d.action)}</td>
                    <td style={{ padding: "12px 20px", color: "#94a3b8" }}>{d.reason}</td>
                    <td style={{ padding: "12px 20px", color: "#e2e8f0" }}>{d.title || "—"}</td>
                    <td style={{ padding: "12px 20px" }}>
                      <a href={d.url} target="_blank" rel="noreferrer" style={{ color: "#38bdf8" }}>
                        {d.url || "—"}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
