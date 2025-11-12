const API = "http://127.0.0.1:4849";
const childId = "child_main";

let es = null;
function connectSSE(){
  if(es) es.close();
  es = new EventSource(`${API}/v1/stream/decisions`);
  es.onmessage = (e)=>{
    try{
      const msg = JSON.parse(e.data);
      chrome.tabs.query({}, tabs => tabs.forEach(t => chrome.tabs.sendMessage(t.id, { type: "watchit_decision", payload: msg })));
    }catch(_){}
  };
  es.onerror = ()=> setTimeout(connectSSE, 1500);
}
connectSSE();

async function getDomSample(tabId){
  try{
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => document.body && document.body.innerText.slice(0, 4000)
    });
    return result || "";
  }catch(_){ return ""; }
}

async function captureTabScreenshot(windowId){
  return new Promise((resolve)=>{
    chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (dataUrl)=>{
      if(chrome.runtime.lastError || !dataUrl) return resolve(null);
      resolve(dataUrl.split(",")[1]); // strip prefix
    });
  });
}

chrome.webNavigation.onCommitted.addListener(async (details)=>{
  if(details.frameId !== 0) return;
  const tab = await chrome.tabs.get(details.tabId);
  const domSample = await getDomSample(details.tabId);

  // FAST pass
  const baseEvt = {
    child_id: childId, ts: Date.now(), kind: "visit",
    url: details.url, title: tab.title || "", tab_id: `c-${details.tabId}`, referrer: "",
    data_json: JSON.stringify({ dom_sample: domSample })
  };

  try{
    const r = await fetch(`${API}/v1/event`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(baseEvt) });
    const dec = await r.json();
    const eventId = dec.event_id;
    chrome.tabs.sendMessage(details.tabId, { type: "watchit_decision", payload: dec });
    if(!dec.needs_ocr) return;

    // Upgrade with screenshot (PaddleOCR server-side) only when backend confidence is low
    const b64 = await captureTabScreenshot(tab.windowId);
    if(!b64) return;
    const upgradeEvt = {
      id: eventId, child_id: childId, ts: Date.now(), kind: "content",
      url: details.url, title: tab.title || "", tab_id: `c-${details.tabId}`, referrer: "",
      data_json: JSON.stringify({ dom_sample: domSample, screenshots_b64: [b64] })
    };
    const r2 = await fetch(`${API}/v1/event/upgrade`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(upgradeEvt) });
    const dec2 = await r2.json();
    chrome.tabs.sendMessage(details.tabId, { type: "watchit_decision", payload: dec2 });
  }catch(_){}
});
