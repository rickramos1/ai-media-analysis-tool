import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

INPUT_FILE = "data/womens_health_articles_text.csv"
OUTPUT_PLOT = "data/keyword_trends.png"
OUTPUT_CSV = "data/keyword_trends.csv"

# Define keywords to track
KEYWORDS = [
    "abortion", "plan b", "emergency contraception", "fertility",
    "mifepristone", "misoprostol", "heartbeat bill", "pregnancy crisis center"
]

# Load and clean data
df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=False)
df['publish_date'] = pd.to_datetime(df['publish_date'], errors='coerce')
df = df.dropna(subset=['publish_date'])
df['year_week'] = df['publish_date'].dt.to_period('W').apply(lambda r: r.start_time)

# Initialize results
results = []

# Count keyword frequency per week
for keyword in KEYWORDS:
    keyword_lower = keyword.lower()
    for week, group in df.groupby('year_week'):
        count = group['full_text'].str.lower().str.contains(keyword_lower, na=False).sum()
        total = len(group)
        results.append({
            'week': week,
            'keyword': keyword,
            'mentions': count,
            'articles': total,
            'frequency': count / total if total else 0
        })

# Convert to DataFrame and save
trend_df = pd.DataFrame(results)
trend_df.to_csv(OUTPUT_CSV, index=False)

# Plot keyword frequency trends
plt.figure(figsize=(14, 7))
sns.lineplot(data=trend_df, x='week', y='frequency', hue='keyword')
plt.title('Keyword Frequency Over Time')
plt.ylabel('Mentions per Article')
plt.xlabel('Week')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(OUTPUT_PLOT)
plt.show()
