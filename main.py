import feedparser

RSS_FEED = "https://www.thehindu.com/news/national/feeder/default.rss"

CATEGORIES = {
    "Politics & Governance": ["parliament", "bill", "modi", "bjp", "congress", "minister", "election", "assembly"],
    "Sports & Games": ["cricket", "football", "hockey", "tennis", "olympic", "match", "tournament", "cup"],
    "Science & Technology": ["isro", "satellite", "ai", "space", "research", "nasa", "scientist", "technology"],
    "Business & Economy": ["market", "gdp", "inflation", "trade", "stock", "investment", "economy", "budget"],
    "International Affairs": ["china", "us", "pakistan", "war", "united nations", "ukraine", "world"]
}

def fetch_latest_news():
    """Fetch latest headlines from The Hindu RSS"""
    try:
        feed = feedparser.parse(RSS_FEED)
        return [entry.title for entry in feed.entries[:10]]
    except Exception as e:
        print(f"RSS fetch error: {e}")
        return ["Fallback: Parliament passes new education bill",
                "Fallback: India wins cricket test match",
                "Fallback: ISRO launches new satellite"]

def categorize_headline(headline: str) -> str:
    """Simple keyword-based category assignment"""
    h = headline.lower()
    for category, keywords in CATEGORIES.items():
        if any(word in h for word in keywords):
            return category
    return "General Affairs"

def generate_quiz():
    headlines = fetch_latest_news()
    quiz = []
    for i, headline in enumerate(headlines[:10]):
        correct = categorize_headline(headline)
        quiz.append({
            "q": f"Q{i+1}. Which category best fits this news: \"{headline}\"?",
            "options": list(CATEGORIES.keys()) + ["General Affairs"],
            "answer": correct
        })
    with open(QUIZ_JSON, "w", encoding="utf-8") as f:
        json.dump(quiz, f, indent=2)
    return quiz

@app.route('/quiz')
def show_quiz():
    if not os.path.exists(QUIZ_JSON):
        quiz = generate_quiz()
    else:
        with open(QUIZ_JSON, "r", encoding="utf-8") as f:
            quiz = json.load(f)

    html = ""
    for q in quiz:
        html += f'<div class="question"><p><b>{q["q"]}</b></p><div class="options">'
        for opt in q["options"]:
            color = "green" if opt == q["answer"] else "black"
            html += f'<p style="color:{color}">{opt}</p>'
        html += "</div></div>"

    return render_template_string(wrap_grid_page("Current Affairs Quiz", html))
