document.addEventListener("DOMContentLoaded", async () => {
  const connStatus = document.getElementById("connection-status");
  const paperTitle = document.getElementById("paper-title-placeholder");
  const scoreContainer = document.getElementById("score-container");
  const paperScore = document.getElementById("paper-score");
  const actionBtn = document.getElementById("action-btn");
  const statusInfo = document.getElementById("status-info");
  const errorBox = document.getElementById("error-box");

  const settingsToggle = document.getElementById("settings-toggle-btn");
  const settingsUi = document.getElementById("settings-ui");
  const serverInput = document.getElementById("setting-server-url");
  const tokenInput = document.getElementById("setting-api-token");
  const saveBtn = document.getElementById("save-settings-btn");

  // Load configured settings
  const stored = await chrome.storage.sync.get(["serverUrl", "apiToken"]);
  const baseUrl = (stored.serverUrl || "http://127.0.0.1:5000").replace(/\/+$/, "");
  const token = stored.apiToken || "";

  if (serverInput) serverInput.value = baseUrl;
  if (tokenInput) tokenInput.value = token;

  settingsToggle?.addEventListener("click", () => {
    settingsUi.style.display = settingsUi.style.display === "none" ? "block" : "none";
  });

  saveBtn?.addEventListener("click", async () => {
    const newUrl = serverInput.value.trim().replace(/\/+$/, "");
    const newToken = tokenInput.value.trim();
    await chrome.storage.sync.set({
      serverUrl: newUrl,
      apiToken: newToken
    });
    settingsUi.style.display = "none";
    window.location.reload();
  });

  // Build standard headers
  const reqHeaders = { "Content-Type": "application/json" };
  if (token) {
    reqHeaders["Authorization"] = `Bearer ${token}`;
  }

  // Helper to extract arXiv ID
  function getArxivId(url) {
    const match = url.match(/arxiv\.org\/abs\/([^\s#?]+)/);
    return match ? match[1] : null;
  }

  // 1. Get active tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url) {
    connStatus.textContent = "Offline";
    paperTitle.textContent = "No active page detected";
    return;
  }

  const arxivId = getArxivId(tab.url);
  if (!arxivId) {
    connStatus.textContent = "Ready";
    paperTitle.textContent = "Not an arXiv abstract page";
    statusInfo.textContent = "Navigate to an arXiv abstract page (e.g., https://arxiv.org/abs/...) to use AURA.";
    return;
  }

  // 2. Query AURA API
  connStatus.textContent = "Connecting...";
  try {
    const checkUrl = `${baseUrl}/api/extension/check?arxiv_id=${encodeURIComponent(arxivId)}`;
    const response = await fetch(checkUrl, { headers: reqHeaders });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error("Authentication required. Click ⚙️ to set your API Bearer token.");
      }
      throw new Error(`AURA server error: ${response.statusText}`);
    }

    const data = await response.json();
    connStatus.textContent = "Connected";
    connStatus.style.background = "#065f46";
    connStatus.style.color = "#a7f3d0";

    paperTitle.textContent = data.title || arxivId;
    scoreContainer.style.display = "block";
    paperScore.textContent = `${Math.round(data.score * 100)}%`;

    if (data.exists) {
      actionBtn.textContent = "In AURA Library";
      actionBtn.disabled = true;
      statusInfo.textContent = "This paper is already in your AURA library.";
    } else {
      actionBtn.textContent = "Add to AURA";
      actionBtn.disabled = false;
      statusInfo.textContent = "Ready to add paper and generate AI summary.";

      actionBtn.addEventListener("click", async () => {
        actionBtn.disabled = true;
        actionBtn.textContent = "Adding...";
        statusInfo.textContent = "Fetching paper content, embedding, and generating summary...";

        try {
          const addResponse = await fetch(`${baseUrl}/api/extension/add`, {
            method: "POST",
            headers: reqHeaders,
            body: JSON.stringify({ arxiv_id: arxivId })
          });

          if (!addResponse.ok) {
            if (addResponse.status === 401) {
              throw new Error("Authentication required. Click ⚙️ to set your API token.");
            }
            throw new Error("Failed to add paper.");
          }

          actionBtn.textContent = "Added Successfully";
          statusInfo.textContent = "Paper added! AI summary generated successfully.";
        } catch (err) {
          errorBox.style.display = "block";
          errorBox.textContent = err.message;
          actionBtn.textContent = "Add to AURA";
          actionBtn.disabled = false;
        }
      });
    }
  } catch (err) {
    connStatus.textContent = "AURA Offline";
    connStatus.style.background = "#7f1d1d";
    connStatus.style.color = "#fca5a5";
    paperTitle.textContent = "AURA Connection Failed";
    statusInfo.textContent = `Ensure AURA is reachable at ${baseUrl}. Click ⚙️ to update settings.`;
    errorBox.style.display = "block";
    errorBox.textContent = err.message || "Connection refused.";
  }
});
