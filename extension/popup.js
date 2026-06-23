const AURA_BASE_URL = "http://127.0.0.1:5000";

document.addEventListener("DOMContentLoaded", async () => {
  const connStatus = document.getElementById("connection-status");
  const paperTitle = document.getElementById("paper-title-placeholder");
  const scoreContainer = document.getElementById("score-container");
  const paperScore = document.getElementById("paper-score");
  const actionBtn = document.getElementById("action-btn");
  const statusInfo = document.getElementById("status-info");
  const errorBox = document.getElementById("error-box");

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
    const checkUrl = `${AURA_BASE_URL}/api/extension/check?arxiv_id=${encodeURIComponent(arxivId)}`;
    const response = await fetch(checkUrl);
    
    if (!response.ok) {
      throw new Error(`AURA server error: ${response.statusText}`);
    }
    
    const data = await response.json();
    connStatus.textContent = "Connected";
    connStatus.style.background = "#065f46";
    connStatus.style.color = "#a7f3d0";
    
    paperTitle.textContent = data.title || arxivId;
    scoreContainer.style.display = "block";
    paperScore.textContent = `${round(data.score * 100)}%`;
    
    if (data.exists) {
      actionBtn.textContent = "In AURA Library";
      actionBtn.disabled = true;
      statusInfo.textContent = "This paper is already in your AURA library.";
    } else {
      actionBtn.textContent = "Add to AURA";
      actionBtn.disabled = false;
      statusInfo.textContent = "Ready to add paper and generate AI summary.";
      
      // Add event listener for adding paper
      actionBtn.addEventListener("click", async () => {
        actionBtn.disabled = true;
        actionBtn.textContent = "Adding...";
        statusInfo.textContent = "Fetching paper content, embedding, and generating summary...";
        
        try {
          const addResponse = await fetch(`${AURA_BASE_URL}/api/extension/add`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ arxiv_id: arxivId })
          });
          
          if (!addResponse.ok) {
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
    paperTitle.textContent = "AURA Server Connection Failed";
    statusInfo.textContent = "Make sure the AURA local server is running at http://127.0.0.1:5000.";
    errorBox.style.display = "block";
    errorBox.textContent = "Connection refused. Please start AURA server.";
  }

  function round(val) {
    return Math.round(val);
  }
});
