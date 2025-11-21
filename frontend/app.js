// app.js
// ------------------------------
// Fetch a job result JSON
// ------------------------------
async function fetchResult(jobId) {
  if (!jobId) return null;

  const res = await fetch(`/jobs/${jobId}/result`, {
    headers: { "X-User-ID": "user-1" },
  });

  if (!res.ok) {
    console.warn("Failed to fetch result for job:", jobId);
    return null;
  }

  const json = await res.json();
  return json.data;
}

// ------------------------------
// Main UI Loader
// ------------------------------
async function loadResults() {
  const segId = document.getElementById("segJobId").value.trim();
  const tissueId = document.getElementById("tissueJobId").value.trim();

  const status = document.getElementById("status");
  status.textContent = "Loading results...";

  // Reset images before new load
  document.getElementById("segOverlay").src = "";
  document.getElementById("segMask").src = "";
  document.getElementById("tissueOverlay").src = "";
  document.getElementById("tissueMask").src = "";

  const seg = await fetchResult(segId);
  const tissue = await fetchResult(tissueId);

  // ------------------------------
  // SEGMENTATION (JSON + PNGs)
  // ------------------------------
  if (seg) {
    // Print JSON
    if (document.getElementById("segJson")) {
      document.getElementById("segJson").textContent =
        JSON.stringify(seg, null, 2);
    }

    if (seg.overlay_png) {
      document.getElementById("segOverlay").src = seg.overlay_png;
      document.getElementById("segOverlay").style.display = "block";
    }

    if (seg.mask_png) {
      document.getElementById("segMask").src = seg.mask_png;
      document.getElementById("segMask").style.display = "block";
    }
  } else {
    if (document.getElementById("segJson")) {
      document.getElementById("segJson").textContent =
        "(Segmentation result not found)";
    }
  }

  // ------------------------------
  // TISSUE MASK (PNG only)
  // ------------------------------
  if (tissue) {
    if (tissue.tissue_overlay_png) {
      document.getElementById("tissueOverlay").src =
        tissue.tissue_overlay_png;
    }

    if (tissue.tissue_mask_png) {
      document.getElementById("tissueMask").src =
        tissue.tissue_mask_png;
    }
  }

  status.textContent = "Loaded (if valid job IDs).";
}
