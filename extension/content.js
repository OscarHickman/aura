(async function() {
  const match = window.location.pathname.match(/\/abs\/([^\s#?]+)/);
  if (!match) return;
  const arxivId = match[1];

  let baseUrl = "http://127.0.0.1:5000";
  let token = "";

  try {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.sync) {
      const stored = await chrome.storage.sync.get(["serverUrl", "apiToken"]);
      if (stored.serverUrl) baseUrl = stored.serverUrl.replace(/\/+$/, "");
      if (stored.apiToken) token = stored.apiToken;
    }
  } catch (e) {
    // Fall back to default local baseUrl
  }

  const reqHeaders = { "Content-Type": "application/json" };
  if (token) {
    reqHeaders["Authorization"] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${baseUrl}/api/extension/check?arxiv_id=${encodeURIComponent(arxivId)}`, {
      headers: reqHeaders
    });
    if (!response.ok) return;
    const data = await response.json();

    // Create a floating container
    const container = document.createElement("div");
    container.id = "aura-extension-badge";
    container.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #0f172a;
      border: 1px solid #334155;
      color: #f8fafc;
      padding: 16px;
      border-radius: 12px;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
      z-index: 99999;
      font-family: system-ui, -apple-system, sans-serif;
      width: 240px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    `;

    const header = document.createElement("div");
    header.style.cssText = "display: flex; justify-content: space-between; align-items: center;";
    
    const title = document.createElement("span");
    title.innerText = "AURA Recommender";
    title.style.cssText = "font-weight: 700; color: #38bdf8; font-size: 14px;";
    header.appendChild(title);

    const scoreBadge = document.createElement("span");
    scoreBadge.innerText = `${Math.round(data.score * 100)}% Match`;
    scoreBadge.style.cssText = `
      background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
      color: white;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 12px;
    `;
    header.appendChild(scoreBadge);
    container.appendChild(header);

    const info = document.createElement("div");
    info.style.cssText = "font-size: 12px; color: #94a3b8; line-height: 1.4;";
    
    if (data.exists) {
      info.innerText = "✓ This paper is in your AURA library.";
      container.appendChild(info);
    } else {
      info.innerText = "Paper not in library.";
      container.appendChild(info);

      const addBtn = document.createElement("button");
      addBtn.innerText = "Add to AURA";
      addBtn.style.cssText = `
        background: #38bdf8;
        color: #0f172a;
        border: none;
        padding: 8px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.2s;
      `;
      addBtn.addEventListener("click", async () => {
        addBtn.disabled = true;
        addBtn.innerText = "Adding...";
        try {
          const addResp = await fetch(`${baseUrl}/api/extension/add`, {
            method: "POST",
            headers: reqHeaders,
            body: JSON.stringify({ arxiv_id: arxivId })
          });
          if (addResp.ok) {
            addBtn.innerText = "Added";
            info.innerText = "✓ Paper added and summarized successfully!";
          } else {
            addBtn.innerText = "Failed";
            addBtn.disabled = false;
          }
        } catch {
          addBtn.innerText = "Error";
          addBtn.disabled = false;
        }
      });
      container.appendChild(addBtn);
    }

    document.body.appendChild(container);
  } catch (e) {
    // AURA server is offline or unreachable, silently ignore
  }
})();
