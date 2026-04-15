import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "rickramos1"
REPO_NAME = "ai-media-analysis-tool"

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

issues = [
    {
        "title": "Set Up Media Source Groups by Region and Ideology",
        "body": """Create grouped media source lists using MediaCloud's Directory API.

**Checklist:**
- [ ] Define 4 media groups: US Left, US Right, EU General, Asia General
- [ ] Include at least 5 sources per group
- [ ] Verify each source has active stories in the last 90 days
- [ ] Save source groups as JSON in `/groups/` folder"""
    },
    {
        "title": "Define and Test Topic Search Queries",
        "body": """Build and test keyword queries related to AI policy and job automation.

**Checklist:**
- [ ] Define 5+ queries like: "AI regulation", "job automation", etc.
- [ ] Ensure 100+ results in U.S., EU, and Asia (last 6 months)
- [ ] Save in CSV or JSON"""
    },
    {
        "title": "Generate Topic Timeseries Across All Source Groups",
        "body": """Use MediaCloud’s `timeseries` endpoint to track topic volume by group.

**Checklist:**
- [ ] Output: Date, Media Group, Story Count
- [ ] Timespan: at least 6 months
- [ ] Normalize by group size
- [ ] Export as CSV or JSON"""
    },
    {
        "title": "Extract Framing Terms per Group via Word Count & Word2Vec",
        "body": """Use MediaCloud’s `wordCount` and `word2vec` endpoints to extract associated framing language.

**Checklist:**
- [ ] 20 frequent + 20 similar terms per query
- [ ] Remove stop words
- [ ] Include frequency or similarity score
- [ ] Save structured output"""
    },
    {
        "title": "Extract Sample Sentences and Quotes for LLM Processing",
        "body": """Use `sentenceList` to gather sentences for narrative analysis.

**Checklist:**
- [ ] 100+ sentences per media group per query
- [ ] Include metadata: source, date, media name
- [ ] Save as CSV or JSON"""
    },
    {
        "title": "Classify Sentence Frames Using LLM",
        "body": """Classify framing using an LLM into 5 categories: Optimistic tech future, Job loss panic, etc.

**Checklist:**
- [ ] Use example-rich prompt
- [ ] Manually validate 50 sentences
- [ ] Achieve >80% agreement
- [ ] Store output with sentence ID + classification"""
    },
    {
        "title": "Visualize Trends and Narrative Breakdowns",
        "body": """Build dashboard or static report for narrative visualization.

**Checklist:**
- [ ] 2 time-based charts
- [ ] Table of framing classifications
- [ ] Section with quote highlights
- [ ] Exportable as HTML or PDF"""
    },
    {
        "title": "Track Mentions of Key Policies and Organizations",
        "body": """Track mentions of key AI policy terms (e.g. EU AI Act, FTC, OpenAI).

**Checklist:**
- [ ] Define 5+ policy terms
- [ ] Frequency chart by group over time
- [ ] List of co-mentioned people/orgs"""
    }
]

for issue in issues:
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
    response = requests.post(url, headers=headers, json=issue)
    if response.status_code == 201:
        print(f"Issue created: {issue['title']}")
    else:
        print(f"Failed to create: {issue['title']}")
        print(response.json())
