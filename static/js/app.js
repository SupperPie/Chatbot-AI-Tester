const API_BASE = "/api";

// State
let allCases = [];
let selectedCases = new Set();
let history = [];

// Init
document.addEventListener("DOMContentLoaded", () => {
    loadCases();
    loadHistory();
});

// Tabs
function showTab(tabId, btn) {
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach(el => el.classList.remove("active"));

    document.getElementById(tabId).classList.add("active");
    btn.classList.add("active");

    if (tabId === 'history-tab') loadHistory();
}

// Cases CRUD
async function loadCases() {
    try {
        const res = await fetch(`${API_BASE}/cases`);
        allCases = await res.json();
        if (!Array.isArray(allCases)) {
            console.error("Expected array from API, got:", allCases);
            allCases = [];
        }
    } catch (e) {
        console.error("Failed to load cases:", e);
        allCases = [];
    }
    renderCases();
}

function renderCases() {
    const tbody = document.getElementById("cases-body");
    tbody.innerHTML = "";

    if (allCases && Array.isArray(allCases)) {
        allCases.forEach(c => {
            const tr = document.createElement("tr");
            const isChecked = selectedCases.has(c.id);

            tr.innerHTML = `
                <td class="col-select">
                    <input type="checkbox" onchange="toggleSelect('${c.id}')" ${isChecked ? 'checked' : ''}>
                </td>
                <td>
                    <textarea class="editable-cell" 
                        onblur="autoSave('${c.id}', 'input', this.value)"
                        placeholder="Enter input question...">${c.input || ''}</textarea>
                </td>
                <td>
                    <textarea class="editable-cell" 
                        onblur="autoSave('${c.id}', 'expected_output', this.value)"
                        placeholder="Enter expected output...">${c.expected_output || ''}</textarea>
                </td>
                <td>
                    <input type="text" class="editable-cell" 
                        onblur="autoSave('${c.id}', 'tags', this.value)" 
                        value="${c.tags ? c.tags.join(', ') : ''}"
                        placeholder="tag1, tag2">
                </td>
                <td class="col-actions">
                    <button class="btn-icon delete" onclick='deleteCase("${c.id}")' title="Delete Case">🗑</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Append an empty "New Row" at the bottom for quick addition
    const newRow = document.createElement("tr");
    newRow.id = "new-case-row";
    newRow.innerHTML = `
        <td class="col-select"></td>
        <td>
            <textarea id="new-input" class="editable-cell" 
                placeholder="+ Add New Case (Type here...)" 
                onblur="checkCreateNew()"></textarea>
        </td>
        <td>
            <textarea id="new-expected" class="editable-cell" 
                placeholder="Expected output..."
                onblur="checkCreateNew()"></textarea>
        </td>
        <td>
            <input id="new-tags" type="text" class="editable-cell" 
                placeholder="tags..."
                onblur="checkCreateNew()">
        </td>
        <td class="col-actions">
            <span style="color:#9ca3af; font-size:12px;">(Auto-save)</span>
        </td>
    `;
    tbody.appendChild(newRow);

    // Update count display to show total
    const countSpan = document.getElementById("selected-count");
    if (countSpan) countSpan.innerText = selectedCases.size;
}

function toggleSelect(id) {
    if (selectedCases.has(id)) {
        selectedCases.delete(id);
    } else {
        selectedCases.add(id);
    }
    updateRunStats(); // Assuming this function exists elsewhere to update UI
}

function toggleSelectAll(checkbox) {
    if (checkbox.checked) {
        allCases.forEach(c => selectedCases.add(c.id));
    } else {
        selectedCases.clear();
    }
    renderCases(); // Re-render to update all checkboxes
    updateRunStats(); // Assuming this function exists elsewhere to update UI
}

async function deleteSelected() {
    if (selectedCases.size === 0) {
        alert("No cases selected to delete.");
        return;
    }

    if (!confirm(`Are you sure you want to delete ${selectedCases.size} selected cases?`)) {
        return;
    }

    const idsToDelete = Array.from(selectedCases);

    // Process deletes (could be batch API but loop for now if API doesn't support batch)
    // Assuming API supports single delete, we loop in parallel
    await Promise.all(idsToDelete.map(id =>
        fetch(`${API_BASE}/cases/${id}`, { method: "DELETE" })
    ));

    selectedCases.clear();
    loadCases();
}

// Auto Save Existing
async function autoSave(id, field, value) {
    const caseItem = allCases.find(c => c.id === id);
    if (!caseItem) return;

    let newValue = value;
    if (field === 'tags') {
        newValue = value.split(',').map(t => t.trim()).filter(t => t);
    }

    if (JSON.stringify(caseItem[field]) === JSON.stringify(newValue)) return; // No change

    // Optimistic UI Update
    caseItem[field] = newValue;

    // Save to backend
    await saveToServer(caseItem);
}

// Create New on Blur
async function checkCreateNew() {
    // Only create if we have at least an Input
    const inputVal = document.getElementById("new-input").value.trim();
    const expectedVal = document.getElementById("new-expected").value.trim();
    const tagsVal = document.getElementById("new-tags").value.trim();

    if (!inputVal) return; // Don't create empty cases just by clicking

    const newCase = {
        input: inputVal,
        expected_output: expectedVal,
        retrieval_context: [],
        tags: tagsVal ? tagsVal.split(',').map(t => t.trim()) : []
    };

    // Clear inputs immediately to prevent double submission if user clicks around
    document.getElementById("new-input").value = "";
    document.getElementById("new-expected").value = "";
    document.getElementById("new-tags").value = "";

    await saveToServer(newCase);
    loadCases(); // Reload to show it in the main list
}

async function saveToServer(caseData) {
    try {
        const res = await fetch(`${API_BASE}/cases`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(caseData)
        });
        return await res.json();
    } catch (e) {
        console.error("Save failed", e);
    }
}

// Modal Form (Legacy - kept for deep edits or removed? User asked for direct edit)
// Kept "New Case" button in UI, let's redirect it to addNewRow or keep modal.
// User said: "directly add in the form".
function openModal(caseId = null) {
    if (caseId) {
        // Edit logic via modal if clicking edit button (which we removed from row actions)
        // We can maybe remove this logic if strictly table editing.
        // Let's keep it but maybe unused for now.
    } else {
        addNewRow(); // Redirect add button to table row
    }
}

function closeModal() {
    document.getElementById("case-modal").style.display = "none";
}

// Edit Case wrapper - functionality moved to inline
window.editCase = function (id) {
    // No-op or open detail view
}

window.deleteCase = async function (id) {
    if (!confirm("Are you sure?")) return;
    await fetch(`${API_BASE}/cases/${id}`, { method: "DELETE" });
    loadCases();
}

// Removed saveCase since we use autoSave and saveToServer now.


// Running Tests
async function runTests() {
    console.log("Running tests...");
    console.log(selectedCases);
    return;
    if (selectedCases.size === 0) {
        alert("Please select cases to run first!");
        return;
    }

    const consoleBox = document.getElementById("run-console");
    const status = document.getElementById("run-status");
    const progress = document.getElementById("run-progress");
    const resultContainer = document.getElementById("latest-result-container");

    consoleBox.style.display = "block";
    resultContainer.style.display = "none";
    status.innerText = "Running tests... Please wait.";
    progress.style.width = "50%"; // Fake progress for now

    const payload = { case_ids: Array.from(selectedCases) };

    try {
        const res = await fetch(`${API_BASE}/run`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        progress.style.width = "100%";
        status.innerText = `Completed! Passed: ${data.passed}/${data.total}`;

        renderResults(data.results);
        resultContainer.style.display = "block";
        loadHistory(); // Refresh history tab
    } catch (e) {
        status.innerText = "Error: " + e;
    }
}

function renderResults(results) {
    const tbody = document.getElementById("latest-result-body");
    tbody.innerHTML = "";
    results.forEach(r => {
        const tr = document.createElement("tr");
        tr.className = r.passed ? "row-pass" : "row-fail";
        tr.innerHTML = `
            <td>${r.input}</td>
            <td>${r.score}</td>
            <td>${r.passed ? "✅" : "❌"}</td>
            <td>${r.reason || "-"}</td>
        `;
        tbody.appendChild(tr);
    });
}

// History
async function loadHistory() {
    const res = await fetch(`${API_BASE}/run/history`);
    history = await res.json();
    const container = document.getElementById("history-container");
    container.innerHTML = "";

    history.forEach(h => {
        const div = document.createElement("div");
        div.className = "history-item";
        div.innerHTML = `
            <div class="history-meta">
                <strong>${new Date(h.timestamp).toLocaleString()}</strong>
                <span>Total: ${h.total} | Passed: ${h.passed} | Failed: ${h.failed}</span>
            </div>
            <div class="history-actions">
                 <button class="btn-icon delete" onclick="deleteHistory('${h.id}')">🗑</button>
            </div>
        `;
        container.appendChild(div);
    });
}

window.deleteHistory = async function (id) {
    if (!confirm("Delete this history record?")) return;
    await fetch(`${API_BASE}/run/history/${id}`, { method: "DELETE" });
    loadHistory();
}
