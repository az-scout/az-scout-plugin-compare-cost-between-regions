/* eslint-disable @microsoft/sdl/no-inner-html -- Dynamic values use escapeHtml(). */
// Cost Comparison plugin — 3-step workflow.
// Globals from app.js: apiFetch, apiPost, regions
(function () {
    const PLUGIN = "compare-cost-between-regions";
    const container = document.getElementById("plugin-tab-" + PLUGIN);
    if (!container) return;

    fetch(`/plugins/${PLUGIN}/static/html/compare-cost-between-regions-tab.html`)
        .then(r => r.text())
        .then(html => { container.innerHTML = html; init(); })
        .catch(err => {
            container.innerHTML = `<div class="alert alert-danger">Failed to load UI: ${escapeHtml(err.message)}</div>`;
        });

    // ── Helpers ─────────────────────────────────────────────────────────────
    function escapeHtml(s) {
        const el = document.createElement("span");
        el.textContent = s;
        return el.innerHTML;
    }

    function parseCsvLine(line) {
        const vals = [];
        let cur = "", inQ = false;
        for (let i = 0; i < line.length; i++) {
            const c = line[i];
            if (c === '"') {
                if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
                else inQ = !inQ;
            } else if (c === ',' && !inQ) {
                vals.push(cur); cur = "";
            } else {
                cur += c;
            }
        }
        vals.push(cur);
        return vals;
    }

    function parseCsv(text) {
        const lines = text.replace(/\r\n?/g, "\n").split("\n");
        const headers = parseCsvLine(lines[0]).map(h => h.trim());
        const rows = [];
        for (let i = 1; i < lines.length; i++) {
            if (!lines[i].trim()) continue;
            const vals = parseCsvLine(lines[i]);
            const row = {};
            headers.forEach((h, j) => { row[h] = (vals[j] || "").trim(); });
            rows.push(row);
        }
        return { headers, rows };
    }

    function parseCost(val) {
        let s = (val || "").replace(/[€$£¥\u00a0\s]/g, "");
        if (!s || s === "-") return 0;
        if (/,\d{1,2}$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
        else s = s.replace(/,/g, "");
        return parseFloat(s) || 0;
    }

    function fmtNum(n, decimals = 2) {
        if (n == null) return "–";
        return Number(n).toFixed(decimals);
    }

    const OFFER_NAMES = {
        "MS-AZR-0017P": "Enterprise Agreement",
        "MS-AZR-0148P": "Dev/Test",
    };

    // MeterRegion (PriceSheet) → ARM region name mapping (loaded from backend)
    let METER_REGION_TO_ARM = {};

    function meterRegionDisplayName(meterRegion) {
        const armName = METER_REGION_TO_ARM[meterRegion];
        if (!armName) return meterRegion;
        const regs = (typeof regions !== "undefined" ? regions : []);
        const r = regs.find(r => r.name === armName);
        return r ? r.displayName : meterRegion;
    }

    function fmtPricing(pricingModel, term, offerId) {
        const offer = OFFER_NAMES[offerId] || offerId;
        return [pricingModel, term, offer].filter(Boolean).join(" / ");
    }

    // ── Main init ───────────────────────────────────────────────────────────
    function init() {
        // Load region mapping from backend (single source of truth)
        fetch(`/plugins/${PLUGIN}/region-mapping`)
            .then(r => r.json())
            .then(data => { METER_REGION_TO_ARM = data.meter_to_arm || {}; })
            .catch(() => {}); // fallback: empty mapping, meterRegionDisplayName returns raw value

        // Step panels & indicators
        const stepPanels = [
            document.getElementById("ccbr-step-1"),
            document.getElementById("ccbr-step-2"),
            document.getElementById("ccbr-step-3"),
        ];
        const stepInds = [
            document.getElementById("ccbr-step-ind-1"),
            document.getElementById("ccbr-step-ind-2"),
            document.getElementById("ccbr-step-ind-3"),
        ];

        // Agreement type state (EA or MCA)
        let agreementType = "ea";

        function goToStep(n) {
            // Block step 2+ for MCA
            if (n >= 2 && agreementType === "mca") {
                showError("MCA / MPA billing account type is not yet supported. Please select Enterprise Agreement (EA) in Step 1.");
                return;
            }
            stepPanels.forEach((p, i) => p.classList.toggle("d-none", i !== n - 1));
            stepInds.forEach((ind, i) => {
                ind.classList.toggle("active", i === n - 1);
                ind.classList.toggle("completed", i < n - 1);
            });
            hideError();
            // Sync source region display when entering step 3
            if (n === 3) {
                const psSourceEl = document.getElementById("ccbr-ps-source");
                const regSel = document.getElementById("ccbr-meter-region-select");
                if (psSourceEl && regSel) {
                    psSourceEl.value = meterRegionDisplayName(regSel.value || "");
                }
            }
        }

        // Step navigation buttons
        document.getElementById("ccbr-next-to-step2").addEventListener("click", () => goToStep(2));
        document.getElementById("ccbr-back-to-step1").addEventListener("click", () => goToStep(1));
        document.getElementById("ccbr-next-to-step3").addEventListener("click", () => goToStep(3));
        document.getElementById("ccbr-back-to-step2").addEventListener("click", () => goToStep(2));

        // Clickable step indicators — only allow if step is active or completed
        document.querySelectorAll(".ccbr-step[data-step]").forEach(el => {
            el.addEventListener("click", () => {
                const n = parseInt(el.dataset.step, 10);
                if (el.classList.contains("active") || el.classList.contains("completed")) {
                    goToStep(n);
                }
            });
        });

        // ── Agreement type toggle (EA vs MCA) ───────────────────────────
        const docEa = document.getElementById("ccbr-doc-ea");
        const docMca = document.getElementById("ccbr-doc-mca");
        const docPsEa = document.getElementById("ccbr-doc-ps-ea");
        const docPsMca = document.getElementById("ccbr-doc-ps-mca");
        const mcaWarning = document.getElementById("ccbr-mca-warning");
        const nextToStep2Btn = document.getElementById("ccbr-next-to-step2");

        document.querySelectorAll(".ccbr-mode-card[data-agreement]").forEach(card => {
            card.addEventListener("click", () => {
                agreementType = card.dataset.agreement;
                const isEa = agreementType === "ea";

                // Toggle active card
                document.querySelectorAll(".ccbr-mode-card[data-agreement]").forEach(c =>
                    c.classList.toggle("ccbr-mode-active", c === card)
                );

                // Toggle instruction panels
                docEa.classList.toggle("d-none", !isEa);
                docMca.classList.toggle("d-none", isEa);
                if (docPsEa) docPsEa.classList.toggle("d-none", !isEa);
                if (docPsMca) docPsMca.classList.toggle("d-none", isEa);

                // Show/hide MCA warning and disable Continue button
                mcaWarning.classList.toggle("d-none", isEa);
                nextToStep2Btn.disabled = !isEa;
            });
        });

        // Step 2 elements
        const dropZone        = document.getElementById("ccbr-drop-zone");
        const fileInput       = document.getElementById("ccbr-file-input");
        const uploadSection   = document.getElementById("ccbr-upload-section");
        const fileBar         = document.getElementById("ccbr-file-bar");
        const fileName        = document.getElementById("ccbr-file-name");
        const rowCount        = document.getElementById("ccbr-row-count");
        const fileMonth       = document.getElementById("ccbr-file-month");
        const clearBtn        = document.getElementById("ccbr-clear-btn");
        const filters         = document.getElementById("ccbr-filters");
        const regionSelect    = document.getElementById("ccbr-meter-region-select");
        const filteredCount   = document.getElementById("ccbr-filtered-count");
        const dataPanels      = document.getElementById("ccbr-data-panels");
        const previewTable    = document.getElementById("ccbr-preview-table");
        const nextToStep3     = document.getElementById("ccbr-next-to-step3");
        const errorEl         = document.getElementById("ccbr-error");

        let csvData = null;

        // ── File handling ───────────────────────────────────────────────────
        const dropZoneOriginalHtml = dropZone.innerHTML;

        function showDropZoneLoading(fileName) {
            dropZone.innerHTML = `<div class="d-flex flex-column align-items-center gap-2">
                <div class="spinner-border text-primary" role="status"></div>
                <span class="small text-body-secondary">Processing <strong>${escapeHtml(fileName)}</strong>…</span>
            </div>`;
        }

        function restoreDropZone() {
            dropZone.innerHTML = dropZoneOriginalHtml;
            // Re-bind the file input inside the restored HTML
            const newInput = dropZone.querySelector("input[type=file]");
            if (newInput) {
                newInput.addEventListener("change", () => {
                    if (newInput.files?.[0]) handleFile(newInput.files[0]);
                });
            }
        }

        function handleFile(file) {
            if (!file || !file.name.toLowerCase().endsWith(".csv")) {
                showError("Please select a .csv file");
                return;
            }
            showDropZoneLoading(file.name);
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    csvData = parseCsv(reader.result);
                    onCsvLoaded(file.name);
                } catch (e) {
                    restoreDropZone();
                    showError("Failed to parse CSV: " + e.message);
                }
            };
            reader.onerror = () => {
                restoreDropZone();
                showError("Failed to read file");
            };
            reader.readAsText(file, "utf-8");
        }

        dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("ccbr-drag-over"); });
        dropZone.addEventListener("dragleave", () => dropZone.classList.remove("ccbr-drag-over"));
        dropZone.addEventListener("drop", e => {
            e.preventDefault();
            dropZone.classList.remove("ccbr-drag-over");
            const file = e.dataTransfer?.files?.[0];
            if (file) handleFile(file);
        });
        fileInput.addEventListener("change", () => {
            if (fileInput.files?.[0]) handleFile(fileInput.files[0]);
        });

        clearBtn.addEventListener("click", resetStep2);

        function resetStep2() {
            csvData = null;
            restoreDropZone();
            uploadSection.classList.remove("d-none");
            fileBar.classList.add("d-none");
            filters.classList.add("d-none");
            dataPanels.classList.add("d-none");
            nextToStep3.classList.add("d-none");
            hideError();
        }

        // ── CSV loaded ──────────────────────────────────────────────────────
        function onCsvLoaded(name) {
            hideError();
            uploadSection.classList.add("d-none");
            fileBar.classList.remove("d-none");
            fileName.textContent = name;
            rowCount.textContent = csvData.rows.length + " rows";

            // Detect month
            const months = new Set();
            csvData.rows.forEach(r => {
                const d = r["Date"] || "";
                let m = "";
                if (/^\d{4}-\d{2}/.test(d)) m = d.slice(0, 7);
                else if (/^\d{1,2}\/\d{1,2}\/\d{4}/.test(d)) {
                    const p = d.split("/");
                    m = p[2] + "-" + p[0].padStart(2, "0");
                }
                if (m) months.add(m);
            });
            fileMonth.textContent = months.size === 1
                ? [...months][0]
                : months.size + " months";

            // Populate region dropdown
            const meterRegions = [...new Set(csvData.rows.map(r => r["MeterRegion"]).filter(Boolean))].sort();
            regionSelect.innerHTML = '<option value="">— select region —</option>';
            meterRegions.forEach(r => {
                const opt = document.createElement("option");
                opt.value = r;
                opt.textContent = r;
                regionSelect.appendChild(opt);
            });

            filters.classList.remove("d-none");
        }

        // ── Filtering ───────────────────────────────────────────────────────
        function getFilteredRows() {
            if (!csvData) return [];
            const region = regionSelect.value;
            if (!region) return [];
            return csvData.rows.filter(r => r["MeterRegion"] === region);
        }

        function aggregateRows(rows) {
            const agg = {};
            for (const r of rows) {
                const meterId = (r["MeterId"] || "").trim();
                if (!meterId) continue;
                const key = [meterId, r["PricingModel"] || "", r["Term"] || "", r["OfferId"] || ""].join("|");
                if (!agg[key]) {
                    agg[key] = {
                        meter_id: meterId,
                        pricing_model: r["PricingModel"] || "",
                        term: r["Term"] || "",
                        offer_id: r["OfferId"] || "",
                        meter_name: r["MeterName"] || "",
                        meter_category: r["MeterCategory"] || "",
                        meter_sub_category: r["MeterSubCategory"] || "",
                        part_number: r["PartNumber"] || "",
                        source_cost: 0,
                        quantity: 0,
                    };
                }
                agg[key].source_cost += parseCost(r["Cost"]);
                agg[key].quantity += parseFloat(r["Quantity"]) || 0;
            }
            return Object.values(agg).sort((a, b) => b.source_cost - a.source_cost);
        }

        function onFilterChange() {
            const rows = getFilteredRows();
            const region = regionSelect.value;

            if (region && rows.length) {
                filteredCount.textContent = rows.length + " rows";
                filteredCount.classList.remove("d-none");

                const items = aggregateRows(rows);
                renderAggregatedTable(items);
                renderBillingSummary(rows);
                dataPanels.classList.remove("d-none");
                nextToStep3.classList.remove("d-none");
            } else {
                filteredCount.classList.add("d-none");
                dataPanels.classList.add("d-none");
                nextToStep3.classList.add("d-none");
            }
        }

        regionSelect.addEventListener("change", onFilterChange);

        // ── Aggregated SKU table ────────────────────────────────────────────
        let _previewDT = null;

        function renderAggregatedTable(items) {
            if (_previewDT) {
                try { _previewDT.destroy(); } catch {}
                _previewDT = null;
            }
            // Re-query after potential simpleDatatables DOM changes
            const tbl = document.getElementById("ccbr-preview-table");
            tbl.innerHTML = `<thead><tr>
                <th>Category</th><th>Meter</th><th>Pricing</th>
                <th class="text-end">Cost</th><th class="text-end">Quantity</th>
            </tr></thead><tbody></tbody>`;
            const tbody = tbl.querySelector("tbody");
            let html = "";
            for (const it of items) {
                const pricingInfo = fmtPricing(it.pricing_model, it.term, it.offer_id);
                html += `<tr>
                    <td>${escapeHtml(it.meter_category)}</td>
                    <td>${escapeHtml(it.meter_name)}</td>
                    <td class="small">${escapeHtml(pricingInfo)}</td>
                    <td class="text-end">${fmtNum(it.source_cost)}</td>
                    <td class="text-end">${fmtNum(it.quantity, 4)}</td>
                </tr>`;
            }
            tbody.innerHTML = html;

            if (typeof simpleDatatables !== "undefined") {
                _previewDT = new simpleDatatables.DataTable(tbl, {
                    searchable: false,
                    paging: false,
                    labels: { noRows: "No items", info: "{rows} SKUs" },
                    columns: [
                        { select: 0, sort: "asc" },
                        { select: 1 },
                        { select: 2 },
                        { select: 3, type: "number" },
                        { select: 4, type: "number" },
                    ],
                });
            }
        }

        // ── Billing summary ─────────────────────────────────────────────────
        const CATEGORY_COLORS = [
            "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#dc3545",
            "#fd7e14", "#ffc107", "#198754", "#20c997", "#0dcaf0",
            "#6c757d", "#495057", "#adb5bd", "#5c636a", "#146c43",
        ];

        function renderBillingSummary(rows) {
            const cats = {};
            for (const r of rows) {
                const cat = r["MeterCategory"] || "(unknown)";
                if (!cats[cat]) cats[cat] = { cost: 0, meterIds: new Set() };
                cats[cat].cost += parseCost(r["Cost"]);
                const mid = r["MeterId"] || "";
                if (mid) cats[cat].meterIds.add(mid);
            }

            const sorted = Object.entries(cats)
                .map(([name, d]) => ({ name, cost: d.cost, skus: d.meterIds.size }))
                .sort((a, b) => b.cost - a.cost);

            const grandTotal = sorted.reduce((s, c) => s + c.cost, 0);
            const totalSkus = new Set(rows.map(r => r["MeterId"]).filter(Boolean)).size;

            document.getElementById("ccbr-billing-total").textContent =
                fmtNum(grandTotal) + " (total)";
            document.getElementById("ccbr-billing-sku-count").textContent =
                totalSkus + " unique SKUs";

            const bar = document.getElementById("ccbr-cost-bar");
            let barHtml = "";
            sorted.forEach((c, i) => {
                const pct = grandTotal > 0 ? (c.cost / grandTotal * 100) : 0;
                if (pct < 0.3) return;
                const color = CATEGORY_COLORS[i % CATEGORY_COLORS.length];
                barHtml += `<div class="ccbr-cost-bar-seg" style="width:${pct}%;background:${color}" title="${escapeHtml(c.name)}: ${fmtNum(c.cost)} (${fmtNum(pct, 1)}%)"></div>`;
            });
            bar.innerHTML = barHtml;

            const tbody = document.getElementById("ccbr-billing-table").querySelector("tbody");
            let html = "";
            sorted.forEach((c, i) => {
                const pct = grandTotal > 0 ? (c.cost / grandTotal * 100) : 0;
                const color = CATEGORY_COLORS[i % CATEGORY_COLORS.length];
                html += `<tr>
                    <td><span class="ccbr-color-dot" style="background:${color}"></span></td>
                    <td>${escapeHtml(c.name)}</td>
                    <td class="text-end">${fmtNum(c.cost)}</td>
                    <td class="text-end">${fmtNum(pct, 1)}%</td>
                    <td class="text-end">${c.skus}</td>
                </tr>`;
            });
            tbody.innerHTML = html;
        }

        // ═════════════════════════════════════════════════════════════════════
        // STEP 3 — PriceSheet comparison
        // ═════════════════════════════════════════════════════════════════════
        const psDropZone    = document.getElementById("ccbr-ps-drop-zone");
        const psFileInput   = document.getElementById("ccbr-ps-file-input");
        const psUploadSec   = document.getElementById("ccbr-ps-upload-section");
        const psFileBar     = document.getElementById("ccbr-ps-file-bar");
        const psFileName    = document.getElementById("ccbr-ps-file-name");
        const psFileSize    = document.getElementById("ccbr-ps-file-size");
        const psClearBtn    = document.getElementById("ccbr-ps-clear-btn");
        const psControls    = document.getElementById("ccbr-ps-controls");
        const psSource      = document.getElementById("ccbr-ps-source");
        const psTarget      = document.getElementById("ccbr-ps-target");
        const psCompareBtn  = document.getElementById("ccbr-ps-compare-btn");
        const psProgress    = document.getElementById("ccbr-ps-progress");
        const psResults     = document.getElementById("ccbr-ps-results");

        let psZipFile = null; // raw File object

        const psDropOriginal = psDropZone.innerHTML;

        function showPsLoading(name) {
            psDropZone.innerHTML = `<div class="d-flex flex-column align-items-center gap-2">
                <div class="spinner-border text-primary" role="status"></div>
                <span class="small text-body-secondary">Uploading <strong>${escapeHtml(name)}</strong>…</span>
            </div>`;
        }

        function restorePsDropZone() {
            psDropZone.innerHTML = psDropOriginal;
            const inp = psDropZone.querySelector("input[type=file]");
            if (inp) inp.addEventListener("change", () => { if (inp.files?.[0]) handlePsFile(inp.files[0]); });
        }

        function fmtBytes(b) {
            if (b < 1024) return b + " B";
            if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
            return (b / 1024 / 1024).toFixed(1) + " MB";
        }

        async function handlePsFile(file) {
            if (!file || !file.name.toLowerCase().endsWith(".zip")) {
                showError("Please select a .zip file");
                return;
            }
            psZipFile = file;
            psUploadSec.classList.add("d-none");
            psFileBar.classList.remove("d-none");
            psFileName.textContent = file.name;
            psFileSize.textContent = fmtBytes(file.size);

            // Pre-fill source region display name from step 2
            const srcMeterRegion = regionSelect.value || "";
            psSource.value = meterRegionDisplayName(srcMeterRegion);

            populateTargetRegions();

            psControls.classList.remove("d-none");
            psResults.classList.add("d-none");
        }

        function populateTargetRegions() {
            const regs = (typeof regions !== "undefined" ? regions : []);
            const current = psTarget.value;
            psTarget.innerHTML = '<option value="">— select target region —</option>';
            for (const r of regs) {
                const opt = document.createElement("option");
                opt.value = r.name;
                opt.textContent = r.displayName || r.name;
                if (r.name === current) opt.selected = true;
                psTarget.appendChild(opt);
            }
        }

        // Refresh dropdown if regions are reloaded (tenant change)
        document.addEventListener("azscout:regions-loaded", populateTargetRegions);

        psDropZone.addEventListener("dragover", e => { e.preventDefault(); psDropZone.classList.add("ccbr-drag-over"); });
        psDropZone.addEventListener("dragleave", () => psDropZone.classList.remove("ccbr-drag-over"));
        psDropZone.addEventListener("drop", e => {
            e.preventDefault();
            psDropZone.classList.remove("ccbr-drag-over");
            const f = e.dataTransfer?.files?.[0];
            if (f) handlePsFile(f);
        });
        psFileInput.addEventListener("change", () => {
            if (psFileInput.files?.[0]) handlePsFile(psFileInput.files[0]);
        });

        psClearBtn.addEventListener("click", () => {
            psZipFile = null;
            restorePsDropZone();
            psUploadSec.classList.remove("d-none");
            psFileBar.classList.add("d-none");
            psControls.classList.add("d-none");
            psResults.classList.add("d-none");
        });

        function updatePsCompareBtn() {
            psCompareBtn.disabled = !psTarget.value.trim() || !psZipFile;
        }
        psTarget.addEventListener("change", updatePsCompareBtn);

        // ── Run PriceSheet comparison ────────────────────────────────────────
        psCompareBtn.addEventListener("click", async () => {
            if (!psZipFile || !psTarget.value.trim()) return;
            const rows = getFilteredRows();
            if (!rows.length) { showError("No usage data — go back to step 2"); return; }

            const items = aggregateRows(rows).filter(it => it.source_cost >= 1);
            if (!items.length) { showError("No items above $1 to compare"); return; }

            hideError();
            psResults.classList.add("d-none");
            psProgress.classList.remove("d-none");
            psCompareBtn.disabled = true;

            try {
                const formData = new FormData();
                formData.append("file", psZipFile);
                formData.append("items_json", JSON.stringify(items));
                formData.append("source_region", regionSelect.value);
                formData.append("target_region", psTarget.value.trim());

                const resp = await fetch(`/plugins/${PLUGIN}/compare-pricesheet`, {
                    method: "POST",
                    body: formData,
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.detail || err.message || resp.statusText);
                }
                const data = await resp.json();
                renderPsResults(data);
            } catch (e) {
                showError("Comparison failed: " + e.message);
            } finally {
                psProgress.classList.add("d-none");
                psCompareBtn.disabled = false;
            }
        });

        // ── Render PriceSheet results ────────────────────────────────────────
        let _psDT = null;

        function renderPsResults(data) {
            const psTable = document.getElementById("ccbr-ps-results-table");
            if (_psDT) {
                try { _psDT.destroy(); } catch {}
                _psDT = null;
                psTable.innerHTML = `<thead><tr>
                    <th>Category</th><th>Meter</th><th>Pricing</th>
                    <th class="text-end">Source Cost</th><th class="text-end">Quantity</th>
                    <th class="text-end">Tgt Unit $</th><th class="text-end">Est. Target Cost</th>
                    <th class="text-end">Difference</th><th class="text-end">% Chg</th><th>Status</th>
                </tr></thead><tbody></tbody>`;
            }
            const s = data.summary;

            document.getElementById("ccbr-ps-source-total").textContent = fmtNum(s.total_source_cost);
            document.getElementById("ccbr-ps-target-total").textContent = fmtNum(s.total_estimated_target_cost);

            const diffEl = document.getElementById("ccbr-ps-diff-total");
            diffEl.textContent = (s.total_difference >= 0 ? "+" : "") + fmtNum(s.total_difference);
            diffEl.className = "fw-bold fs-5 " + (s.total_difference > 0 ? "text-danger" : s.total_difference < 0 ? "text-success" : "");

            const pctEl = document.getElementById("ccbr-ps-pct-total");
            pctEl.textContent = (s.percentage_change >= 0 ? "+" : "") + fmtNum(s.percentage_change) + "%";
            pctEl.className = "fw-bold fs-5 " + (s.percentage_change > 0 ? "text-danger" : s.percentage_change < 0 ? "text-success" : "");

            const nfAlert = document.getElementById("ccbr-ps-not-found-alert");
            if (s.items_not_found > 0) {
                nfAlert.textContent = `${s.items_not_found} of ${s.total_items} items could not be found in the target region's PriceSheet.`;
                nfAlert.classList.remove("d-none");
            } else {
                nfAlert.classList.add("d-none");
            }

            const tbody = psTable.querySelector("tbody");
            let html = "";
            for (const item of data.items) {
                const diffClass = item.status === "ok"
                    ? (item.difference > 0 ? "text-danger" : item.difference < 0 ? "text-success" : "")
                    : "text-body-secondary";
                const pctVal = item.price_ratio != null
                    ? ((item.price_ratio - 1) * 100)
                    : null;
                const statusBadge = item.status === "ok"
                    ? '<span class="badge bg-success">OK</span>'
                    : item.status === "zero_cost"
                    ? '<span class="badge bg-secondary">$0</span>'
                    : '<span class="badge bg-warning text-dark">N/A</span>';

                const pricingInfo = fmtPricing(item.pricing_model, item.term, item.offer_id);

                html += `<tr>
                    <td>${escapeHtml(item.meter_category)}</td>
                    <td>${escapeHtml(item.meter_name)}</td>
                    <td class="small">${escapeHtml(pricingInfo)}</td>
                    <td class="text-end">${fmtNum(item.source_cost, 2)}</td>
                    <td class="text-end">${fmtNum(item.quantity, 4)}</td>
                    <td class="text-end">${item.target_unit_price != null ? fmtNum(item.target_unit_price, 6) : '–'}</td>
                    <td class="text-end">${item.estimated_target_cost != null ? fmtNum(item.estimated_target_cost, 2) : '–'}</td>
                    <td class="text-end ${diffClass}">${item.difference != null ? ((item.difference >= 0 ? '+' : '') + fmtNum(item.difference, 2)) : '–'}</td>
                    <td class="text-end ${diffClass}">${pctVal != null ? ((pctVal >= 0 ? '+' : '') + fmtNum(pctVal, 2) + '%') : '–'}</td>
                    <td>${statusBadge}</td>
                </tr>`;
            }
            tbody.innerHTML = html;
            psResults.classList.remove("d-none");

            if (typeof simpleDatatables !== "undefined") {
                _psDT = new simpleDatatables.DataTable(psTable, {
                    searchable: false,
                    paging: false,
                    labels: { noRows: "No items", info: "{rows} items" },
                    columns: [
                        { select: 0 },
                        { select: 1 },
                        { select: 2 },
                        { select: 3, type: "number", sort: "desc" },
                        { select: 4, type: "number" },
                        { select: 5, type: "number" },
                        { select: 6, type: "number" },
                        { select: 7, type: "number" },
                        { select: 8, type: "number" },
                        { select: 9 },
                    ],
                });
            }

            // Initialize Bootstrap tooltips
            psResults.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
                new bootstrap.Tooltip(el);
            });
        }

        // ── CSV download ────────────────────────────────────────────────────
        function downloadCsv(tableEl, filename) {
            const rows = [];
            const headers = [];
            tableEl.querySelectorAll("thead th").forEach(th => {
                headers.push(th.textContent.trim());
            });
            rows.push(headers.join(","));
            tableEl.querySelectorAll("tbody tr").forEach(tr => {
                const cells = [];
                tr.querySelectorAll("td").forEach(td => {
                    let val = td.textContent.trim();
                    if (val.includes(",") || val.includes('"')) {
                        val = '"' + val.replace(/"/g, '""') + '"';
                    }
                    cells.push(val);
                });
                rows.push(cells.join(","));
            });
            const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = filename;
            a.click();
            URL.revokeObjectURL(a.href);
        }

        document.getElementById("ccbr-csv-step2").addEventListener("click", () => {
            const region = meterRegionDisplayName(regionSelect.value || "unknown").replace(/\s+/g, "-");
            downloadCsv(previewTable, `usage-analysis-${region}.csv`);
        });
        document.getElementById("ccbr-csv-step3").addEventListener("click", () => {
            const psTable = document.getElementById("ccbr-ps-results-table");
            const src = (psSource.value || "source").replace(/\s+/g, "-");
            const tgtOpt = psTarget.selectedOptions?.[0];
            const tgt = (tgtOpt?.textContent || psTarget.value || "target").replace(/\s+/g, "-");
            downloadCsv(psTable, `region-comparison-${src}-${tgt}.csv`);
        });

        // ── Error helpers ───────────────────────────────────────────────────
        function showError(msg) {
            errorEl.textContent = msg;
            errorEl.classList.remove("d-none");
        }
        function hideError() {
            errorEl.classList.add("d-none");
        }
    }
})();
