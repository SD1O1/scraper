const initialTargets = [
  { source: "X", title: "Product design roles", query: "product designer OR ux designer", count: "1,248", tone: "x" },
  { source: "Reddit", title: "Freelance pain points", query: "freelance tools OR client management", count: "856", tone: "reddit" },
  { source: "Upwork", title: "Research & strategy work", query: "market research, strategy, insights", count: "730", tone: "upwork" }
];
let targets = JSON.parse(localStorage.getItem("signal-targets") || "null") || initialTargets;
const grid = document.querySelector("#targets-grid");
const dialog = document.querySelector("#target-dialog");

function sourceClass(source) { return source === "X" ? "x" : source === "Reddit" ? "reddit" : "upwork"; }
function renderTargets() {
  grid.innerHTML = targets.map((target, index) => `<article class="target-card ${sourceClass(target.source)}"><div class="target-top"><span class="platform ${sourceClass(target.source)}">${target.source === "X" ? "𝕏" : target.source === "Reddit" ? "r/" : "up"}</span><button class="dots" data-delete="${index}" aria-label="Delete ${target.title}">•••</button></div><h3>${target.title}</h3><p>${target.query}</p><footer><span><b>${target.count || "0"}</b> items</span><span class="running"><i></i> Watching</span></footer></article>`).join("");
  document.querySelector("#target-count").textContent = targets.length;
  document.querySelector("#metric-targets").textContent = targets.length;
  localStorage.setItem("signal-targets", JSON.stringify(targets));
}
document.querySelector("#new-target").addEventListener("click", () => dialog.showModal());
document.querySelector("#manage-targets").addEventListener("click", () => document.querySelector("#targets").scrollIntoView({ behavior: "smooth" }));
document.querySelector("#save-target").addEventListener("click", event => {
  const name = document.querySelector("#target-name").value.trim(); const query = document.querySelector("#target-query").value.trim(); const source = document.querySelector("#target-source").value;
  if (!name || !query) { event.preventDefault(); return; }
  targets.unshift({ source, title: name, query, count: "0" }); renderTargets(); document.querySelector("form").reset();
});
grid.addEventListener("click", event => { const button = event.target.closest("[data-delete]"); if (button) { targets.splice(Number(button.dataset.delete), 1); renderTargets(); } });
renderTargets();
