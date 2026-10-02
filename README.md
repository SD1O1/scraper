# Signal Harvest

A local Reddit research tool. Create targets made from one or more subreddits plus include/exclude keywords, collect posts through the official Reddit API, and filter/export what has been stored in SQLite. X and Upwork are deliberately shown as **coming soon** and are not collected.

## Windows setup

1. Install [Python 3.11+](https://www.python.org/downloads/windows/) and tick **Add Python to PATH** during installation.
2. In PowerShell, open this project and make a virtual environment:
   ```powershell
   cd C:\path\to\scraper
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   ```
3. Create a Reddit **script** app at <https://www.reddit.com/prefs/apps>. Copy `.env.example` to `.env` and fill in its three values:
   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```
   Keep `.env` private; it is ignored by Git.
4. Run the tool:
   ```powershell
   py -m uvicorn backend:app --host 127.0.0.1 --port 4173
   ```
   Or, after activating the environment, run `npm start` if Node.js is installed.
5. Browse to <http://127.0.0.1:4173>.

## Using it

1. Create a Reddit target. Add comma-separated subreddit names (for example `python, learnpython`), include words, optional exclude words, and a listing sort/time filter.
2. Use **Fetch active targets** to read new posts from Reddit. Existing Reddit post IDs are ignored, so repeating collection does not duplicate saved posts.
3. Pause a target to leave its definition saved while omitting it from fetches. Edit and delete are available from each target card.
4. The Library filters saved posts by target, keyword, published date, and minimum Reddit score. **Export CSV** downloads the current filtered result.

## Data and API behaviour

- SQLite data is stored locally in `signal_harvest.db`.
- The app uses PRAW, an official Reddit API client; Reddit credentials are required before collection.
- No data is sent to X or Upwork. Their labels are informational only.
