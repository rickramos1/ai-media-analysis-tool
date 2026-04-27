# Power BI Build Guide

How to build the misinfo-carrier dashboard from the pipeline outputs. One-time manual setup; data refresh after subsequent pipeline runs is just clicking **Refresh**.

## Prerequisites

- Power BI Desktop installed on Windows (free, [download](https://www.microsoft.com/power-bi/desktop/))
- Both CSV files copied from `data/` on the server to a stable folder on the Windows machine:
  - `data/misinfo_carriers_pbi.csv` (117 rows — the carriers)
  - `data/stage4b_all_verdicts_pbi.csv` (2,147 rows — all candidate verdicts, used for rate measures)

## Step 1 — Import the data

1. Open Power BI Desktop → **Get data** → **Text/CSV**
2. Select `misinfo_carriers_pbi.csv` → **Load**
3. **Get data** again → **Text/CSV** → select `stage4b_all_verdicts_pbi.csv` → **Load**

Both tables now appear in the right-hand **Data** pane.

In the **Model view** (left sidebar), confirm the two tables exist with no relationship needed for the basic dashboard. (Optional: relate them on `article_url + claim_text` for advanced cross-filtering.)

## Step 2 — Verify column types

In the **Data view**, click each table and confirm:

| Column | Type |
|---|---|
| `article_publish_date` | Date |
| `similarity` | Decimal Number |
| `claim_id` | Whole Number (verdicts table only) |
| Everything else | Text |

If `article_publish_date` came in as Text, right-click the column → **Change Type → Date**.

## Step 3 — Add core measures

In the **Modeling** ribbon → **New measure**, paste each:

```dax
Total Carriers = COUNTROWS('misinfo_carriers_pbi')

Unique Articles = DISTINCTCOUNT('misinfo_carriers_pbi'[article_url])

Total Verdicts = COUNTROWS('stage4b_all_verdicts_pbi')

Carrier Rate = DIVIDE(
    CALCULATE(COUNTROWS('stage4b_all_verdicts_pbi'), 'stage4b_all_verdicts_pbi'[verdict] = "carrying"),
    [Total Verdicts]
)

Articles per Outlet = DISTINCTCOUNT('misinfo_carriers_pbi'[article_url])
```

## Step 4 — Build the visuals

Recommended page layout (one report page, four visuals):

### Visual 1 — Carriers by Outlet (top-left, half-width bar chart)
- **Visualization**: Stacked Bar Chart
- **Axis**: `article_outlet`
- **Values**: `Unique Articles`
- **Sort**: descending by Unique Articles
- **Title**: "Articles flagged as carriers, by outlet"

### Visual 2 — Campaigns being amplified (top-right, half-width treemap or bar)
- **Visualization**: Treemap
- **Group**: `claim_source`
- **Values**: `Total Carriers`
- **Title**: "Misinfo campaigns by carrier-verdict count"

### Visual 3 — Carriers over time (middle, full-width line chart)
- **Visualization**: Line Chart
- **Axis**: `article_publish_date` (set to **Month**)
- **Values**: `Total Carriers`
- **Legend**: `claim_source` (optional, shows campaign mix per month)
- **Title**: "Carriers per month by campaign"

### Visual 4 — Detail table with evidence (bottom, full-width table)
- **Visualization**: Table
- **Columns** (in order):
  - `article_publish_date`
  - `article_outlet`
  - `article_outlet_ideology`
  - `article_title`
  - `claim_source`
  - `evidence_quote`
  - `similarity`
  - `article_url` (set "Data category" → Web URL so it renders as link)
- **Sort**: descending by similarity
- **Title**: "Carrier detail (click URL to open article)"

### Slicers (optional, top of page)
Add **Slicer** visuals for cross-filtering:
- `article_outlet_ideology`
- `article_topic`
- `claim_source`

## Step 5 — Save

**File → Save As** → `misinfo_carriers_dashboard.pbix`. Commit it to your team's shared location.

## Refreshing after a new pipeline run

1. Pipeline regenerates `data/misinfo_carriers_pbi.csv` and `data/stage4b_all_verdicts_pbi.csv` on the server
2. Copy them to the same folder on Windows (overwriting the old ones)
3. Open the .pbix → **Home → Refresh**
4. Save

That's it — no rebuild needed. The visuals re-bind to the updated data automatically.

## Notes for the team

- **Article URLs are clickable**. Reviewers can click straight from the detail table to read the original article and verify the LLM's evidence quote.
- **`reasoning` column** is included in the verdicts file but not the dashboard table by default — add it as a column tooltip if reviewers want one-glance LLM justification.
- **`article_outlet_ideology`** is from a hardcoded map (`pipeline/source_ideology_tagger.py:IDEOLOGY_MAP`). Two outlets in the current carriers set show as "Unknown" — extend the map and re-run the post-processing step to retag.
- **Date filtering**: `article_publish_date` is parsed from MediaCloud metadata. Some scraped articles have empty dates; they'll appear in a "(blank)" bucket on the time-series chart.
- **Similarity threshold**: The dashboard shows results from a 0.65 cosine threshold. To see more / fewer, re-run Stage 4b with a different `STAGE4B_SIM` env var and regenerate the CSVs.
