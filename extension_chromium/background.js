const API = "http://127.0.0.1:4849"; // adjust for TLS if needed
let childId = "child_main";

// ---- EventSource (SSE) ----
let es = null;
function connectSSE() {
  if (es) { es.close(); es = null; }
  es = new EventSource(`${API}/v1/stream/decisions`);
  es.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      // broadcast to all tabs (content scripts) to enforce
      chrome.tabs.query({}, (tabs) => {
        for (const t of tabs) {
          chrome.tabs.sendMessage(t.id, { type: "watchit_decision", payload: msg });
        }
      });
    } catch(e){}
  };
  es.onerror = () => {
    setTimeout(connectSSE, 2000);
  };
}
connectSSE();

// ---- Helper to get DOM sample/screenshot/audio (minimal) ----
async function getDomSample(tabId) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId }, func: () => document.body && document.body.innerText.slice(0, 4000)
    });
    return result || "";
  } catch (e) { return ""; }
}

// ---- On navigation: POST event ----
chrome.webNavigation.onCommitted.addListener(async (details) => {
  if (details.frameId !== 0) return; // main frame only
  const tab = await chrome.tabs.get(details.tabId);
  const domSample = await getDomSample(details.tabId);

  const evt = {
    child_id: childId,
    ts: Date.now(),
    kind: "visit",
    url: details.url,
    title: tab.title || "",
    tab_id: `c-${details.tabId}`,
    referrer: "",
    data_json: JSON.stringify({ dom_sample: domSample })
  };

  try {
    const r = await fetch(`${API}/v1/event`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(evt)
    });
    const decision = await r.json();
    // notify the tab immediately as well
    chrome.tabs.sendMessage(details.tabId, { type: "watchit_decision", payload: decision });
  } catch(e){}
});
