// State
let manifest = null;
let cuts = [];
let inProgressStart = null;
let syncTimeout = null;
let progressPollTimer = null;

// DOM
const srcDirInput = document.getElementById("srcDir");
const destDirInput = document.getElementById("destDir");
const selInterval = document.getElementById("selInterval");
const btnDetectSD = document.getElementById("btnDetectSD");
const btnScan = document.getElementById("btnScan");
const selectionStatus = document.getElementById("selectionStatus");
const selectionText = document.getElementById("selectionText");
const btnClearCurrentSelection = document.getElementById("btnClearCurrentSelection");
const sliderSize = document.getElementById("sliderSize");
const btnSizeDec = document.getElementById("btnSizeDec");
const btnSizeInc = document.getElementById("btnSizeInc");
const lblSize = document.getElementById("lblSize");
const statClipCount = document.getElementById("statClipCount");
const statDuration = document.getElementById("statDuration");
const statCutCount = document.getElementById("statCutCount");
const btnCutCount = document.getElementById("btnCutCount");
const sidebarCount = document.getElementById("sidebarCount");
const syncStatus = document.getElementById("syncStatus");
const verticalTimeline = document.getElementById("verticalTimeline");
const emptyPlaceholder = document.getElementById("emptyPlaceholder");
const cutsSidebar = document.getElementById("cutsSidebar");
const cutsListScroll = document.getElementById("cutsListScroll");
const btnToggleSidebar = document.getElementById("btnToggleSidebar");
const btnCloseSidebar = document.getElementById("btnCloseSidebar");
const btnClearAllCuts = document.getElementById("btnClearAllCuts");
const btnCutOnly = document.getElementById("btnCutOnly");
const btnCutAndStitch = document.getElementById("btnCutAndStitch");
const hoverMagnifier = document.getElementById("hoverMagnifier");
const magnifierImg = document.getElementById("magnifierImg");
const magnifierClip = document.getElementById("magnifierClip");
const magnifierTime = document.getElementById("magnifierTime");
const modalBackdrop = document.getElementById("modalBackdrop");
const modalSpinner = document.getElementById("modalSpinner");
const modalPercent = document.getElementById("modalPercent");
const modalTitle = document.getElementById("modalTitle");
const modalMsg = document.getElementById("modalMsg");
const modalProgressFill = document.getElementById("modalProgressFill");
const modalDetails = document.getElementById("modalDetails");
const modalActions = document.getElementById("modalActions");
const modalCloseBtn = document.getElementById("modalCloseBtn");

// New Pre-Scan Dialogs & SD Banner DOM
const sdBanner = document.getElementById("sdBanner");
const sdBannerText = document.getElementById("sdBannerText");
const btnDismissSdBanner = document.getElementById("btnDismissSdBanner");
const btnResetSdCuts = document.getElementById("btnResetSdCuts");

const modalConfirmDest = document.getElementById("modalConfirmDest");
const confirmDestMsg = document.getElementById("confirmDestMsg");
const confirmDestInput = document.getElementById("confirmDestInput");
const btnCloseDestModal = document.getElementById("btnCloseDestModal");
const btnCancelDestScan = document.getElementById("btnCancelDestScan");
const btnConfirmDestProceed = document.getElementById("btnConfirmDestProceed");

const modalReuseThumbs = document.getElementById("modalReuseThumbs");
const reuseThumbsMsg = document.getElementById("reuseThumbsMsg");
const btnCloseReuseModal = document.getElementById("btnCloseReuseModal");
const btnCancelReuseThumbs = document.getElementById("btnCancelReuseThumbs");
const btnReuseThumbs = document.getElementById("btnReuseThumbs");
const btnRegenerateThumbs = document.getElementById("btnRegenerateThumbs");

const btnRefreshApp = document.getElementById("btnRefreshApp");

let userManuallyChangedDest = false;

destDirInput.addEventListener("input", () => {
  userManuallyChangedDest = true;
});

// Refresh App: cleans cache and reloads page
if (btnRefreshApp) {
  btnRefreshApp.addEventListener("click", () => {
    // Clear session cache and hard reload
    localStorage.removeItem("pf_sourceDir");
    localStorage.removeItem("pf_destDir");
    window.location.reload(true);
  });
}

function formatSec(seconds) {
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
}

// 1. Initialization
window.addEventListener("DOMContentLoaded", async () => {
  // Restore settings from localStorage
  const savedSrc = localStorage.getItem("pf_sourceDir");
  const savedDst = localStorage.getItem("pf_destDir");
  const savedInt = localStorage.getItem("pf_interval");
  const savedSize = localStorage.getItem("pf_frameSize");

  if (savedSrc) srcDirInput.value = savedSrc;
  if (savedDst) destDirInput.value = savedDst;
  if (savedInt) selInterval.value = savedInt;
  if (savedSize) {
    sliderSize.value = savedSize;
    updateFrameSize(savedSize);
  }

  // Detect GoPro drives if empty, but do NOT automatically pop up scans on load
  if (!srcDirInput.value) {
    await autoDetectSD();
  }
});

// Frame Size Controls
function updateFrameSize(val) {
  const num = parseInt(val, 10);
  document.documentElement.style.setProperty("--frame-width", `${num}px`);
  lblSize.textContent = `${num}px`;
  localStorage.setItem("pf_frameSize", num);
}

sliderSize.addEventListener("input", (e) => updateFrameSize(e.target.value));
btnSizeDec.addEventListener("click", () => {
  const cur = parseInt(sliderSize.value, 10);
  sliderSize.value = Math.max(280, cur - 40);
  updateFrameSize(sliderSize.value);
});
btnSizeInc.addEventListener("click", () => {
  const cur = parseInt(sliderSize.value, 10);
  sliderSize.value = Math.min(920, cur + 40);
  updateFrameSize(sliderSize.value);
});

// Auto-detect GoPro
async function autoDetectSD() {
  try {
    const res = await fetch("/api/detect_sd");
    const data = await res.json();
    if (data.suggestedSource) {
      srcDirInput.value = data.suggestedSource;
    }
    if (!destDirInput.value && data.suggestedDestination) {
      destDirInput.value = data.suggestedDestination;
    }
  } catch (err) {
    console.error("Auto detect failed:", err);
  }
}
btnDetectSD.addEventListener("click", autoDetectSD);

// Progress Polling
function startProgressPolling() {
  stopProgressPolling();
  progressPollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/progress");
      const data = await res.json();
      if (data) {
        modalPercent.textContent = `${data.percent || 0}%`;
        modalProgressFill.style.width = `${data.percent || 0}%`;
        if (data.title) modalTitle.textContent = data.title;
        if (data.message) modalMsg.textContent = data.message;
        if (data.details) modalDetails.textContent = data.details;
      }
    } catch (e) {}
  }, 250);
}

function stopProgressPolling() {
  if (progressPollTimer) {
    clearInterval(progressPollTimer);
    progressPollTimer = null;
  }
}

// 2. Pre-Scan Checks & Timeline Loading Workflow
btnScan.addEventListener("click", () => startTimelineWorkflow());

async function startTimelineWorkflow() {
  const src = srcDirInput.value.trim();
  const dst = destDirInput.value.trim();
  const interval = parseFloat(selInterval.value);

  if (!src) { alert("Please specify a GoPro SD source directory."); return; }
  if (!dst) { alert("Please specify a destination folder."); return; }

  // Check session state on server
  try {
    const res = await fetch("/api/check_session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sourceDir: src, destDir: dst, interval: interval })
    });
    const info = await res.json();

    // Condition 1: If output folder does not exist for this recording, OR user manually changed the folder path in the menu
    if (!info.destExists || userManuallyChangedDest) {
      userManuallyChangedDest = false; // reset flag once confirmed
      confirmDestInput.value = dst;
      confirmDestMsg.textContent = !info.destExists
        ? `Output folder does not exist: "${dst}". Confirm or edit destination path before initial scan:`
        : `You changed the destination folder to: "${dst}". Confirm destination path before scanning:`;
      modalConfirmDest.style.display = "flex";
      return;
    }

    // Condition 2: Output folder exists from previous run, check if thumbnails exist
    if (info.thumbnailsExist && info.thumbnailCount > 0) {
      reuseThumbsMsg.innerHTML = `Found <b>${info.thumbnailCount}</b> cached thumbnails in <code>${dst}</code>.<br>Reuse existing thumbnails for instant loading, or regenerate fresh ones?`;
      modalReuseThumbs.style.display = "flex";
      return;
    }

    // If destination exists but no thumbnails, proceed with regular scan
    executeScan(true);
  } catch (err) {
    console.error("Check session error:", err);
    executeScan(true);
  }
}

// Modal actions for Confirm Destination
btnCloseDestModal.addEventListener("click", () => {
  modalConfirmDest.style.display = "none";
});
btnCancelDestScan.addEventListener("click", () => {
  modalConfirmDest.style.display = "none";
});
btnConfirmDestProceed.addEventListener("click", () => {
  const newDst = confirmDestInput.value.trim();
  if (newDst) {
    destDirInput.value = newDst;
  }
  modalConfirmDest.style.display = "none";
  executeScan(true);
});

// Modal actions for Thumbnail Reuse
btnCloseReuseModal.addEventListener("click", () => {
  modalReuseThumbs.style.display = "none";
});
btnCancelReuseThumbs.addEventListener("click", () => {
  modalReuseThumbs.style.display = "none";
});
btnReuseThumbs.addEventListener("click", () => {
  modalReuseThumbs.style.display = "none";
  executeScan(true);
});
btnRegenerateThumbs.addEventListener("click", () => {
  modalReuseThumbs.style.display = "none";
  executeScan(false);
});

// SD Banner Actions
btnDismissSdBanner.addEventListener("click", () => {
  sdBanner.style.display = "none";
});
btnResetSdCuts.addEventListener("click", async () => {
  if (confirm("Are you sure you want to clear all cuts from both the SD card and destination?")) {
    const src = srcDirInput.value.trim();
    const dst = destDirInput.value.trim();
    await fetch("/api/clear_sd_cuts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sourceDir: src, destDir: dst })
    });
    cuts = [];
    localStorage.removeItem(`pf_cuts_${dst}`);
    sdBanner.style.display = "none";
    updateCutVisualOverlays();
    updateStats();
    renderCutsSidebar();
  }
});

async function executeScan(reuseThumbnails = true) {
  const src = srcDirInput.value.trim();
  const dst = destDirInput.value.trim();
  const interval = parseFloat(selInterval.value);

  localStorage.setItem("pf_sourceDir", src);
  localStorage.setItem("pf_destDir", dst);
  localStorage.setItem("pf_interval", interval);

  showModal(
    reuseThumbnails ? "Loading Timeline..." : "Scanning GoPro Footage...",
    reuseThumbnails ? "Loading cached thumbnails..." : "Extracting frames at full speed...",
    true
  );
  startProgressPolling();

  try {
    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sourceDir: src,
        destDir: dst,
        interval: interval,
        reuseThumbnails: reuseThumbnails
      })
    });
    const data = await res.json();
    stopProgressPolling();

    if (data.error) {
      hideModal();
      alert("Error: " + data.error);
      return;
    }

    modalPercent.textContent = "100%";
    modalProgressFill.style.width = "100%";
    manifest = data;
    hideModal();

    // Restore cuts
    if (data.savedCuts && data.savedCuts.length > 0) {
      cuts = data.savedCuts;
      if (data.cutsSource === "sd_card") {
        sdBannerText.innerHTML = `Loaded <b>${cuts.length}</b> saved attempts directly from GoPro SD card.`;
        sdBanner.style.display = "flex";
      } else {
        sdBanner.style.display = "none";
      }
    } else {
      sdBanner.style.display = "none";
      const localCutsKey = `pf_cuts_${dst}`;
      const localCuts = localStorage.getItem(localCutsKey);
      if (localCuts) {
        try { cuts = JSON.parse(localCuts); } catch(e) {}
      }
    }

    renderContinuousTimeline();
    updateStats();
    renderCutsSidebar();
  } catch (err) {
    stopProgressPolling();
    hideModal();
    alert("Failed to scan GoPro footage: " + err.message);
  }
}

// 3. Render Continuous Vertical Timeline (Single Column)
function renderContinuousTimeline() {
  if (!manifest || !manifest.clips || manifest.clips.length === 0) {
    emptyPlaceholder.style.display = "block";
    verticalTimeline.innerHTML = "";
    return;
  }

  emptyPlaceholder.style.display = "none";
  verticalTimeline.innerHTML = "";

  manifest.clips.forEach((clip, cIdx) => {
    const section = document.createElement("section");
    section.className = "clip-section";
    section.dataset.clip = clip.clipName;

    // Sticky Chapter Header
    const sessionNum = clip.sessionIndex !== undefined ? clip.sessionIndex : (cIdx + 1);
    const isTooShort = !clip.frames || clip.frames.length === 0;

    const header = document.createElement("div");
    header.className = `clip-sticky-header ${isTooShort ? "clip-header-discarded" : ""}`;
    header.innerHTML = `
      <div class="clip-header-title">
        <span>🎬 ${clip.clipName}</span>
        <span class="clip-badge">Session ${sessionNum} &bull; Chapter ${clip.chapter}</span>
        ${isTooShort ? '<span class="clip-badge-discard">Discarded</span>' : ''}
      </div>
      <div class="clip-header-meta">
        Duration: <b>${clip.durationStr}</b> &bull; ${clip.frameCount} frames
      </div>
    `;
    section.appendChild(header);

    // SINGLE COLUMN VERTICAL CONTAINER
    const column = document.createElement("div");
    column.className = "frames-column";

    if (isTooShort) {
      const notice = document.createElement("div");
      notice.className = "clip-discard-notice";
      notice.innerHTML = `
        <span class="discard-icon">⚠️</span>
        <div class="discard-text">
          <b>Clip is too short (${clip.durationStr}), discarding...</b>
          <span>Recording duration is under sampling interval (${manifest.interval}s) or contains no usable frames.</span>
        </div>
      `;
      column.appendChild(notice);
    } else {
      clip.frames.forEach((f) => {
        const card = document.createElement("div");
        card.className = "frame-card";
        card.dataset.clip = clip.clipName;
        card.dataset.sec = f.sec;
        card.dataset.idx = f.index;

        const imgUrl = `/api/thumbnail?dest=${encodeURIComponent(manifest.destDir)}&path=${encodeURIComponent(f.relPath)}`;
        const img = document.createElement("img");
        img.src = imgUrl;
        img.loading = "lazy";
        // Auto-retry on glitch
        img.onerror = () => {
          setTimeout(() => { img.src = `${imgUrl}&_t=${Date.now()}`; }, 300);
        };

        const timeBadge = document.createElement("div");
        timeBadge.className = "badge-time";
        timeBadge.textContent = f.timeStr;

        const idxBadge = document.createElement("div");
        idxBadge.className = "badge-frame-idx";
        idxBadge.textContent = `#${f.index + 1}`;

        card.appendChild(img);
        card.appendChild(timeBadge);
        card.appendChild(idxBadge);

        // Frame Click Handler (Instant Multi-Cut)
        card.addEventListener("click", (e) => {
          if (e.target.closest(".cut-delete-btn")) return;
          onFrameClicked(clip.clipName, f.sec, f.index);
        });

        // Hover Magnifier
        card.addEventListener("mouseenter", () => {
          magnifierImg.src = img.src;
          magnifierClip.textContent = clip.clipName;
          magnifierTime.textContent = `${f.timeStr} (${f.sec.toFixed(1)}s)`;
          hoverMagnifier.style.display = "block";
        });
        card.addEventListener("mouseleave", () => {
          hoverMagnifier.style.display = "none";
        });

        column.appendChild(card);
      });
    }

    section.appendChild(column);
    verticalTimeline.appendChild(section);
  });

  updateCutVisualOverlays();
}

// 4. Mouse Multi-Cut Selection Logic
function onFrameClicked(clipName, sec, frameIdx) {
  if (inProgressStart === null) {
    // 1st click: Set start
    inProgressStart = { clipName, sec, frameIdx };
    selectionText.innerHTML = `Start set at <b>${clipName} [${formatSec(sec)}]</b>. Click another frame to finish attempt.`;
    btnClearCurrentSelection.style.display = "inline-flex";
  } else {
    // 2nd click: Complete attempt
    let startSec = inProgressStart.sec;
    let stopSec = sec;

    if (clipName === inProgressStart.clipName) {
      if (Math.abs(sec - inProgressStart.sec) < 0.5) {
        selectionText.innerHTML = `⚠️ Clicked the same frame! Please click a <b>different frame</b> to set end.`;
        return;
      }
      if (sec < inProgressStart.sec) {
        startSec = sec;
        stopSec = inProgressStart.sec;
      }
    } else {
      startSec = 0;
      stopSec = Math.max(1, sec);
    }

    const dur = Math.max(1, Math.round(stopSec - startSec));
    const newCut = {
      id: Date.now(),
      clipName: inProgressStart.clipName,
      startSec: startSec,
      stopSec: stopSec,
      startTime: formatSec(startSec),
      stopTime: formatSec(stopSec),
      duration: dur,
      label: `Attempt_${cuts.length + 1}`
    };

    cuts.push(newCut);
    inProgressStart = null;
    selectionText.innerHTML = `Created <b>${newCut.label} (${dur}s)</b>! Click any frame to set next attempt.`;
    btnClearCurrentSelection.style.display = "none";

    autoSyncCuts();
  }

  updateCutVisualOverlays();
  updateStats();
  renderCutsSidebar();
}

btnClearCurrentSelection.addEventListener("click", () => {
  inProgressStart = null;
  selectionText.innerHTML = "Click any frame to set <b>Attempt Start</b>";
  btnClearCurrentSelection.style.display = "none";
  updateCutVisualOverlays();
});

// 5. Update Timeline Overlays (Colors & Ribbons)
function updateCutVisualOverlays() {
  const cards = document.querySelectorAll(".frame-card");
  
  cards.forEach(card => {
    const cClip = card.dataset.clip;
    const cSec = parseFloat(card.dataset.sec);

    card.classList.remove("in-progress-start", "cut-start", "cut-stop", "in-cut-range");
    const existingDelBtn = card.querySelector(".cut-delete-btn");
    if (existingDelBtn) existingDelBtn.remove();

    if (inProgressStart && inProgressStart.clipName === cClip && inProgressStart.sec === cSec) {
      card.classList.add("in-progress-start");
    }

    cuts.forEach(cut => {
      if (cut.clipName === cClip) {
        if (cSec === cut.startSec) {
          card.classList.add("cut-start");
        }
        if (cSec === cut.stopSec) {
          card.classList.add("cut-stop");
          const delBtn = document.createElement("button");
          delBtn.className = "cut-delete-btn";
          delBtn.innerHTML = "&times;";
          delBtn.title = `Delete ${cut.label}`;
          delBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteCut(cut.id);
          });
          card.appendChild(delBtn);
        }
        if (cSec > cut.startSec && cSec < cut.stopSec) {
          card.classList.add("in-cut-range");
        }
      }
    });
  });
}

// 6. Delete Cut
function deleteCut(id) {
  cuts = cuts.filter(c => c.id !== id);
  cuts.forEach((c, idx) => {
    if (c.label.startsWith("Attempt_")) {
      c.label = `Attempt_${idx + 1}`;
    }
  });
  autoSyncCuts();
  updateCutVisualOverlays();
  updateStats();
  renderCutsSidebar();
}

btnClearAllCuts.addEventListener("click", () => {
  if (confirm("Clear all marked attempts?")) {
    cuts = [];
    autoSyncCuts();
    updateCutVisualOverlays();
    updateStats();
    renderCutsSidebar();
  }
});

// 7. Auto-Sync to cuts.txt and localStorage
function autoSyncCuts() {
  const dst = destDirInput.value.trim();
  const src = srcDirInput.value.trim();
  const interval = parseFloat(selInterval.value);

  if (dst) {
    localStorage.setItem(`pf_cuts_${dst}`, JSON.stringify(cuts));
  }

  syncStatus.textContent = "🟡 Syncing...";
  clearTimeout(syncTimeout);
  syncTimeout = setTimeout(async () => {
    try {
      await fetch("/api/sync_cuts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sourceDir: src,
          destDir: dst,
          interval: interval,
          cuts: cuts
        })
      });
      syncStatus.textContent = "🟢 Auto-saved to cuts.txt";
    } catch (err) {
      syncStatus.textContent = "🔴 Sync error";
    }
  }, 200);
}

// 8. Cuts Sidebar Rendering
function renderCutsSidebar() {
  sidebarCount.textContent = cuts.length;
  btnCutCount.textContent = cuts.length;

  if (cuts.length === 0) {
    cutsListScroll.innerHTML = `<div class="empty-cuts-hint">No attempts marked yet. Click a start frame then end frame on the timeline to create an attempt.</div>`;
    return;
  }

  cutsListScroll.innerHTML = "";
  cuts.forEach((cut) => {
    const item = document.createElement("div");
    item.className = "cut-item-card";
    item.innerHTML = `
      <div class="cut-item-header">
        <input type="text" class="cut-item-label-input" value="${cut.label}" title="Click to rename">
        <button class="btn-icon" style="color: #da3633; font-size: 16px;" title="Delete">&times;</button>
      </div>
      <div class="cut-item-clip">🎬 ${cut.clipName}</div>
      <div class="cut-item-timing">
        <span class="timing-range">${cut.startTime} &rarr; ${cut.stopTime}</span>
        <span class="timing-dur">${cut.duration}s</span>
      </div>
    `;

    const input = item.querySelector(".cut-item-label-input");
    input.addEventListener("change", (e) => {
      cut.label = e.target.value.trim().replace(/\s+/g, "_") || cut.label;
      autoSyncCuts();
    });

    item.querySelector(".btn-icon").addEventListener("click", () => {
      deleteCut(cut.id);
    });

    cutsListScroll.appendChild(item);
  });
}

function updateStats() {
  if (manifest) {
    statClipCount.textContent = manifest.clipCount || 0;
    statDuration.textContent = manifest.totalDurationStr || "0m";
  }
  statCutCount.textContent = cuts.length;
}

btnToggleSidebar.addEventListener("click", () => cutsSidebar.classList.toggle("collapsed"));
btnCloseSidebar.addEventListener("click", () => cutsSidebar.classList.add("collapsed"));

// 9. Processing Actions: Cut / Stitch with live progress
btnCutOnly.addEventListener("click", () => runProcessing("cut"));
btnCutAndStitch.addEventListener("click", () => runProcessing("cut_and_stitch"));

async function runProcessing(action) {
  if (cuts.length === 0) {
    alert("Please mark at least one attempt before cutting!");
    return;
  }

  const actionName = action === "cut_and_stitch" ? "Cutting & Stitching Highlights" : "Cutting Attempts";
  showModal(actionName, `Preparing GPU NVENC...`, true);
  startProgressPolling();

  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: action,
        sourceDir: srcDirInput.value.trim(),
        destDir: destDirInput.value.trim(),
        cuts: cuts
      })
    });
    const data = await res.json();
    stopProgressPolling();

    modalSpinner.style.display = "none";
    modalPercent.textContent = "100%";
    modalProgressFill.style.width = "100%";
    modalActions.style.display = "flex";

    const destFolder = destDirInput.value.trim();
    if (action === "cut_and_stitch") {
      if (data.stitchResult && data.stitchResult.error) {
        modalTitle.textContent = "⚠️ Highlight Stitch Warning";
        modalMsg.textContent = data.stitchResult.error;
        modalDetails.innerHTML = `Attempt clips are saved in:<br><code style="user-select: all; background: #0d1117; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 6px;">${destFolder}\\attempts\\</code>`;
      } else {
        const hlFile = data.stitchResult && data.stitchResult.outputFile ? data.stitchResult.outputFile : `${destFolder}\\PumpFoil_Highlights.mp4`;
        modalTitle.textContent = "🎉 Highlights Successfully Created!";
        modalMsg.textContent = `Generated highlight reel with smooth transitions!`;
        modalDetails.innerHTML = `Output file:<br><code style="user-select: all; background: #0d1117; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 6px;">${hlFile}</code>`;
      }
    } else {
      const succCount = (data.cutResults || []).filter(r => r.status === "success").length;
      modalTitle.textContent = "🎉 Attempts Successfully Cut!";
      modalMsg.textContent = `Extracted ${succCount} valid attempt clip(s) into destination!`;
      modalDetails.innerHTML = `Saved to:<br><code style="user-select: all; background: #0d1117; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 6px;">${destFolder}\\attempts\\</code>`;
    }
  } catch (err) {
    stopProgressPolling();
    modalSpinner.style.display = "none";
    modalActions.style.display = "flex";
    modalTitle.textContent = "❌ Error Processing Video";
    modalMsg.textContent = err.message;
  }
}

modalCloseBtn.addEventListener("click", hideModal);

function showModal(title, msg, showSpinner = true) {
  modalTitle.textContent = title;
  modalMsg.textContent = msg;
  modalPercent.textContent = "0%";
  modalProgressFill.style.width = "0%";
  modalSpinner.style.display = showSpinner ? "block" : "none";
  modalActions.style.display = "none";
  modalBackdrop.style.display = "flex";
}
function hideModal() {
  modalBackdrop.style.display = "none";
}