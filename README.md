# UK Days

A one-page site listing today's "days of the year" in the UK: Walk Your Dog Day, National Badger Day, that sort of thing. It is rebuilt every morning from the [Days Of The Year](https://www.daysoftheyear.com) API and served from GitHub Pages.

Live at <https://days.lucasw.uk>.

## How it works

Everything is in `uk_days.py`:

1. Collects today's events from the API, using the UK's current UTC offset so "today" is right during BST.
2. Selects up to ten days, UK-tagged ones prioritised.
3. Writes one self-contained HTML file with the CSS and a few lines of JavaScript inline.

The page offers a large and a compact layout and a light or dark theme.

## Running it

You need Python 3.9 or newer and an API key from [daysoftheyear.com/api](https://www.daysoftheyear.com/api/).

```sh
pip install -r requirements.txt
echo "DOTY_API_KEY=your-key" > .env
python uk_days.py # writes uk-days.html
python uk_days.py -o public/index.html
```

To work on the page without calling the API, save a response once and reuse it:

```sh
python uk_days.py --from-file response.json
```

## Deployment

`.github/workflows/build.yml` builds the page and deploys it to GitHub Pages. It needs a repository secret called `DOTY_API_KEY`.

The workflow has no schedule of its own. GitHub's scheduled runs were often late or skipped, so a cron job elsewhere starts it each morning through the `workflow_dispatch` API. You can also run it by hand from the Actions tab.

If the API is unavailable then the build fails and the previous day's page stays up.
