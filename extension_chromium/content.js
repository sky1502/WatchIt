// Simple in-page enforcement for warn/blur/block
const BANNER_ID = "__watchit_warn_banner__";
const INTERSTITIAL_ID = "__watchit_block__";
const BLUR_CLASS = "__watchit_blur__";

function ensureStyles() {
  if (document.getElementById("__watchit_styles__")) return;
  const style = document.createElement("style");
  style.id = "__watchit_styles__";
  style.textContent = `
  .${BLUR_CLASS} img, .${BLUR_CLASS} video { filter: blur(14px) !important; }
  #${BANNER_ID} {
    position: fixed; top:0; left:0; right:0; z-index: 2147483647;
    background:#ffcc00; color:#000; font-family:sans-serif; padding:10px; text-align:center;
    box-shadow:0 2px 6px rgba(0,0,0,0.2);
  }
  #${INTERSTITIAL_ID} {
    position:fixed; inset:0; background:#111; color:#fff; display:flex;
    align-items:center; justify-content:center; z-index:2147483647; font-family:sans-serif;
  }
  `;
  document.documentElement.appendChild(style);
}

function showWarnBanner(reason) {
  ensureStyles();
  removeBanner();
  const div = document.createElement("div");
  div.id = BANNER_ID;
  div.textContent = `WatchIt: This page may need adult supervision (${reason}).`;
  document.documentElement.appendChild(div);
}

function removeBanner() {
  const el = document.getElementById(BANNER_ID);
  if (el) el.remove();
}

function applyBlur() {
  ensureStyles();
  document.documentElement.classList.add(BLUR_CLASS);
}

function removeBlur() {
  document.documentElement.classList.remove(BLUR_CLASS);
}

function blockPage(reason) {
  ensureStyles();
  // wipe page and show interstitial
  document.documentElement.innerHTML = `
    <div id="${INTERSTITIAL_ID}">
      <div>
        <h1>Blocked by WatchIt</h1>
        <p>Reason: ${reason}</p>
      </div>
    </div>`;
}

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg || msg.type !== "watchit_decision") return;
  const d = msg.payload || {};
  const action = d.action;
  const reason = d.reason || "policy";

  // Reset
  removeBanner();
  removeBlur();

  if (action === "warn") {
    showWarnBanner(reason);
  } else if (action === "blur") {
    applyBlur();
    showWarnBanner(reason);
  } else if (action === "block") {
    blockPage(reason);
  } else {
    // allow
  }
});
