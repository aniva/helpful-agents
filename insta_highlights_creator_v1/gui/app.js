document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const customPathInput = document.getElementById("custom-path");
    const btnScan = document.getElementById("btn-scan");
    const videoSelect = document.getElementById("video-select");
    const musicPathInput = document.getElementById("music-path");
    const durationInput = document.getElementById("duration");
    const chkPreview = document.getElementById("chk-preview");
    const btnRun = document.getElementById("btn-run");
    const connectionStatus = document.getElementById("connection-status");
    const videoPlaceholder = document.getElementById("video-placeholder");
    const videoPlayer = document.getElementById("player");
    const progressBar = document.getElementById("progress-bar");
    const progressText = document.getElementById("progress-text");
    const jobBadge = document.getElementById("job-badge");
    const consoleOutput = document.getElementById("console-output");

    // Slider inputs & displays
    const slideRider = document.getElementById("slide-rider");
    const slideKite = document.getElementById("slide-kite");
    const slideScenery = document.getElementById("slide-scenery");
    const valRider = document.getElementById("val-rider");
    const valKite = document.getElementById("val-kite");
    const valScenery = document.getElementById("val-scenery");
    
    const slideMusicVol = document.getElementById("slide-music-vol");
    const slideBgVol = document.getElementById("slide-bg-vol");
    const valMusicVol = document.getElementById("val-music-vol");
    const valBgVol = document.getElementById("val-bg-vol");

    // Local state
    let activePollInterval = null;
    let lastSliderValues = {
        rider: 20,
        kite: 30,
        scenery: 50
    };

    // 1. Focus Sliders Logic (Locks sum to 100%)
    function handleSliderChange(changedKey, value) {
        value = parseInt(value);
        const keys = ['rider', 'kite', 'scenery'];
        const otherKeys = keys.filter(k => k !== changedKey);
        
        const delta = value - lastSliderValues[changedKey];
        
        let val1 = lastSliderValues[otherKeys[0]];
        let val2 = lastSliderValues[otherKeys[1]];
        
        // Distribute -delta between the other two values
        // If we decrease changedKey, we increase others. If we increase, we decrease others.
        if (val1 + val2 > 0) {
            // Distribute proportionally
            const ratio1 = val1 / (val1 + val2);
            const r1Change = Math.round(delta * ratio1);
            const r2Change = delta - r1Change;
            
            val1 -= r1Change;
            val2 -= r2Change;
        } else {
            // Split equally if both others are 0
            const halfChange = Math.round(delta / 2);
            val1 -= halfChange;
            val2 -= (delta - halfChange);
        }
        
        // Clamp and fix any rounding errors
        val1 = Math.max(0, Math.min(100, val1));
        val2 = Math.max(0, Math.min(100, val2));
        
        const sum = value + val1 + val2;
        if (sum !== 100) {
            // Adjust val1 to enforce exact 100 sum
            val1 += (100 - sum);
            val1 = Math.max(0, Math.min(100, val1));
        }
        
        // Update slider positions
        lastSliderValues[changedKey] = value;
        lastSliderValues[otherKeys[0]] = val1;
        lastSliderValues[otherKeys[1]] = val2;
        
        // Sync DOM inputs and text
        slideRider.value = lastSliderValues.rider;
        valRider.innerText = lastSliderValues.rider + "%";
        
        slideKite.value = lastSliderValues.kite;
        valKite.innerText = lastSliderValues.kite + "%";
        
        slideScenery.value = lastSliderValues.scenery;
        valScenery.innerText = lastSliderValues.scenery + "%";
    }

    slideRider.addEventListener("input", (e) => handleSliderChange('rider', e.target.value));
    slideKite.addEventListener("input", (e) => handleSliderChange('kite', e.target.value));
    slideScenery.addEventListener("input", (e) => handleSliderChange('scenery', e.target.value));

    // Audio mixers
    slideMusicVol.addEventListener("input", (e) => {
        valMusicVol.innerText = e.target.value + "%";
    });
    slideBgVol.addEventListener("input", (e) => {
        valBgVol.innerText = e.target.value + "%";
    });

    // 2. Scan Media Directories
    async function scanDrives() {
        writeToConsole("[System] Scanning directories for Insta360 footage...");
        btnScan.disabled = true;
        const customPath = customPathInput.value.trim();
        
        let url = "/api/scan-drives";
        if (customPath) {
            url += `?custom_path=${encodeURIComponent(customPath)}`;
        }
        
        try {
            const res = await fetch(url);
            const data = await res.json();
            
            videoSelect.innerHTML = "";
            
            if (data.video_pairs && data.video_pairs.length > 0) {
                data.video_pairs.forEach(pair => {
                    const option = document.createElement("option");
                    option.value = JSON.stringify(pair);
                    option.innerText = `${pair.prefix} (Front: ${pair.front_name})`;
                    videoSelect.appendChild(option);
                });
                writeToConsole(`[System] Found ${data.video_pairs.length} video pairs.`);
            } else {
                const option = document.createElement("option");
                option.value = "";
                option.innerText = "No paired videos found";
                videoSelect.appendChild(option);
                writeToConsole("[System] No matching raw video pairs (e.g. VID_..._00_... and VID_..._10_...) found.");
            }
        } catch (err) {
            writeToConsole(`[System Error] Scanning failed: ${err.message}`);
        } finally {
            btnScan.disabled = false;
        }
    }

    btnScan.addEventListener("click", scanDrives);

    // Helper: Print to terminal console
    function writeToConsole(line) {
        consoleOutput.innerText += line + "\n";
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }

    // 3. Status Polling Loop
    function startPollingStatus() {
        if (activePollInterval) clearInterval(activePollInterval);
        
        activePollInterval = setInterval(async () => {
            try {
                const res = await fetch("/api/job-status");
                const state = await res.json();
                
                // Update badge class and text
                jobBadge.innerText = state.status.toUpperCase();
                jobBadge.className = `badge-status ${state.status}`;
                
                // Update progress
                const pPercent = Math.round(state.progress * 100);
                progressBar.style.width = `${pPercent}%`;
                progressText.innerText = `${pPercent}%`;
                
                // Update console
                consoleOutput.innerText = state.log;
                consoleOutput.scrollTop = consoleOutput.scrollHeight;
                
                if (state.status === "done") {
                    clearInterval(activePollInterval);
                    activePollInterval = null;
                    btnRun.disabled = false;
                    btnRun.innerText = "Generate Video";
                    
                    // Display video player
                    videoPlaceholder.style.display = "none";
                    videoPlayer.style.display = "block";
                    // Add timestamp to prevent browser cache
                    videoPlayer.src = `/api/play-video?t=${Date.now()}`;
                    videoPlayer.load();
                    videoPlayer.play();
                    
                    writeToConsole("\n[System] Job finished! You can view the highlight video above.");
                } else if (state.status === "error") {
                    clearInterval(activePollInterval);
                    activePollInterval = null;
                    btnRun.disabled = false;
                    btnRun.innerText = "Generate Video";
                    writeToConsole(`\n[System Error] Render job failed: ${state.error_message}`);
                }
            } catch (err) {
                console.error("Polling error:", err);
            }
        }, 1000);
    }

    // 4. Generate Video Submit
    btnRun.addEventListener("click", async () => {
        const selectedVal = videoSelect.value;
        if (!selectedVal) {
            writeToConsole("[System Warning] Please select a raw video pair first.");
            alert("Please select a video pair first.");
            return;
        }
        
        const videoPair = JSON.parse(selectedVal);
        const formatType = document.querySelector('input[name="format-type"]:checked').value;
        const duration = durationInput.value;
        
        const formData = new FormData();
        formData.append("front_path", videoPair.front);
        formData.append("rear_path", videoPair.rear);
        formData.append("music_path", musicPathInput.value.trim());
        formData.append("duration", duration);
        formData.append("p_rider", lastSliderValues.rider / 100.0);
        formData.append("p_kite", lastSliderValues.kite / 100.0);
        formData.append("p_scenery", lastSliderValues.scenery / 100.0);
        formData.append("format_type", formatType);
        formData.append("mix_music_ratio", parseInt(slideMusicVol.value) / 100.0);
        formData.append("mix_bg_ratio", parseInt(slideBgVol.value) / 100.0);
        formData.append("is_preview", chkPreview.checked);
        
        btnRun.disabled = true;
        btnRun.innerText = "Processing...";
        writeToConsole("[System] Submitting highlight job to backend...");
        
        try {
            const res = await fetch("/api/generate-highlights", {
                method: "POST",
                body: formData
            });
            
            if (res.ok) {
                writeToConsole("[System] Render job scheduled successfully. Initializing...");
                startPollingStatus();
            } else {
                const errData = await res.json();
                writeToConsole(`[System Error] Could not start job: ${errData.detail}`);
                btnRun.disabled = false;
                btnRun.innerText = "Generate Video";
            }
        } catch (err) {
            writeToConsole(`[System Error] Connection failed: ${err.message}`);
            btnRun.disabled = false;
            btnRun.innerText = "Generate Video";
        }
    });

    // Run initial scan on startup
    scanDrives();
});
