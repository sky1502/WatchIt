"use client";
import { useEffect, useRef, useState } from "react";

const API = "http://127.0.0.1:4849";

export default function Home() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [pin, setPin] = useState("");
  const [minutes, setMinutes] = useState(15);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetch(`${API}/v1/decisions?limit=50`)
      .then(r=>r.json()).then(j=>setDecisions(j.decisions||[]));

    const es = new EventSource(`${API}/v1/stream/decisions`);
    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        setDecisions((prev)=>[msg, ...prev].slice(0,200));
      } catch {}
    };
    es.onerror = () => { /* auto-reconnect by re-render */ };
    esRef.current = es;
    return () => { es.close(); };
  }, []);

  const pause = async () => {
    await fetch(`${API}/v1/control/pause`, {
      method:"POST", headers:{ "content-type":"application/json" },
      body: JSON.stringify({ pin, minutes })
    });
  };
  const resume = async () => {
    await fetch(`${API}/v1/control/resume`, {
      method:"POST", headers:{ "content-type":"application/json" },
      body: JSON.stringify({ pin })
    });
  };

  return (
    <main style={{ padding: 24, fontFamily: "ui-sans-serif" }}>
      <h1 style={{ fontSize: 28, fontWeight: 700 }}>WatchIt Dashboard</h1>

      <section style={{ marginTop: 24, display:"flex", gap:16 }}>
        <input placeholder="Parent PIN" value={pin} onChange={e=>setPin(e.target.value)} />
        <input type="number" min={1} value={minutes} onChange={e=>setMinutes(parseInt(e.target.value||"15"))}/>
        <button onClick={pause}>Pause</button>
        <button onClick={resume}>Resume</button>
      </section>

      <section style={{ marginTop: 24 }}>
        <h2>Recent Decisions (live)</h2>
        <table cellPadding={6} style={{ width:"100%", borderCollapse:"collapse" }}>
          <thead><tr><th>When</th><th>Action</th><th>Reason</th><th>Title</th><th>URL</th></tr></thead>
          <tbody>
            {decisions.map((d, i) => (
              <tr key={i} style={{ borderTop:"1px solid #ddd" }}>
                <td>{new Date().toLocaleTimeString()}</td>
                <td>{d.action}</td>
                <td>{d.reason}</td>
                <td>{d.title || ""}</td>
                <td>{d.url || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
