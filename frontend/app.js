// frontend/app.js

async function fetchResult(jobId) {
  if (!jobId) return null;

  const res = await fetch(`/jobs/${jobId}/result`, {
    headers: { "X-User-ID": "user-1" }
  });

  if (!res.ok) return null;

  const json = await res.json();
  return json.data;
}

async function loadResults() {
  const segId = document.getElementById("segJobId").value.trim();
  const tissueId = document.getElementById("tissueJobId").value.trim();

  document.getElementById("status").textContent = "Loading...";

  const seg = await fetchResult(segId);
  const tissue = await fetchResult(tissueId);

  if (seg) {
    document.getElementById("segJson").textContent =
      JSON.stringify(seg, null, 2);

    if (seg.overlay_png) {
      document.getElementById("segOverlay").src = seg.overlay_png;
      document.getElementById("segOverlay").style.display = "block";
    }

    if (seg.mask_png) {
      document.getElementById("segMask").src = seg.mask_png;
      document.getElementById("segMask").style.display = "block";
    }
  }

  if (tissue) {
    document.getElementById("tissueOverlay").src =
      tissue.tissue_overlay_png || "";
    document.getElementById("tissueMask").src =
      tissue.tissue_mask_png || "";
  }

  document.getElementById("status").textContent = "Loaded.";
}

function testButton() {
  alert("JS working!");
}

