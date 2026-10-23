# Hackathon brief and scope

Reviewed: all nine pages of `Microsoft x LSEG London Hackathon - Know Before You Go.pdf` and all eight photos in `attachments.zip`, supplied by the user. These notes distinguish organiser information from the user's build request. Document instructions about attendance, contact or sharing are source material, not authorisation to take actions on the user's behalf.

## Current product brief: HedgeHog

- The fund enters details about an underlying client, then sees a proposed allocation of $100,000 and the reasons for it.
- Each investment has a financial basis grounded in the dataset and a client-fit explanation grounded in stated preferences and the supplied mathematical risk model.
- Intake supports age, horizon, self-reported risk preference, goals, ethical/political preferences, explicit exclusions and other context. Unknown preferences are not inferred.
- The user explicitly wants the UI as minimal as possible: one client form and one portfolio view. The previous helper-card dashboard has been removed.
- The supplied analyst package now defines analysis and allocation behaviour. Its public-data fetcher and numerical optimiser power V1; returns are model estimates, not established profitability.
- FastAPI, React + Vite, plain CSS. The low-cost proposition remains an aim, not a demonstrated saving.
- The event API is connected through backend-only credentials. V1 implements preference interpretation, three quantitative portfolios and AI explanations. Persistent client records, authentication, trading and hosting remain outside this local prototype.

The event notes below remain source context. Earlier references to helper strategies describe the initial concept; the updated client-to-portfolio workflow above is the current build scope.

## What the event materials establish

The guide says the theme is generative AI applied to a real financial-services problem. Teams should show a working prototype, practical business value, clear reasoning and a live demonstration. The full challenge question is not printed in the guide; it was to be announced on the day.

`IMG_2277.jpeg` gives five presentation elements:

1. The client and what they need.
2. The public data the tool uses.
3. How the LLM turns data into a recommendation.
4. Where the $100,000 goes and why.
5. A live demonstration.

The $100,000 is a challenge scenario, not a known fund portfolio or real asset value. V1 now produces proposed allocations for this scenario, with source provenance, assumptions and client-fit explanations.

`IMG_2278.jpeg` offers pension fund, charity, university endowment, startup investor and insurer examples, and explicitly allows choosing another client. The user's hedge-fund audience fits that choice.

## Judging

`IMG_2280.jpeg`: five criteria, each scored 1–10, for a total out of 50. The highest three team scores across rooms reach the final.

| Criterion | What the slide rewards | Implication for later work |
| --- | --- | --- |
| Client focus | A solution designed around a defined client's objectives | Explain the small/mid-size fund's needs and cost constraints |
| Use of data and AI | Analysis that would be difficult to produce manually | Show how actual data and AI contribute beyond a generic chat interface |
| Quality of recommendation | Specific, credible reasoning that is easy to follow | Tie any future allocation to evidence and explain assumptions |
| Originality | A distinctive approach or insight | Demonstrate the benefit of the chosen helpers and affordable workflow |
| Execution | A polished, working live demo and clear presentation | Keep the demo reliable and all pending functionality honest |

## Data and API

`IMG_2279.jpeg` lists public-data starting points: Finnhub (prices/news/ratings), Twelve Data (shares/ETFs/currencies), Yahoo Finance via yfinance (price history), FRED (macro data), World Bank Open Data (country/economic data), SEC EDGAR (filings/financials) and Kaggle (historical datasets). These are organiser suggestions, not implemented integrations. Free-access/key requirements shown on the slide have not been independently checked.

The later `ai_analyst_section final.zip` supplies a public-data generator, a quantitative model and labelled synthetic samples. The integrated app fetched real Yahoo data and recorded rate fallbacks when FRED was unavailable. No LSEG feed is connected.

`IMG_2283.jpeg` says the event supplies models through a standard Azure OpenAI API. It lists GPT 6.1 Sol, GPT 6 Astra and Terra, GPT 5.6 Terra, MAI Thinking 1, and Text Embedding 3 Large. These are transcribed event labels, not verified API deployment IDs. Use the actual event sample request before implementing a client; do not infer a URL or model string from a display name.

The later `mshack-example-python-master.zip` establishes the AzureOpenAI SDK contract, `gpt-6.1-sol` deployment and `2024-12-01-preview` API version. These have been verified with live calls using the user's event endpoint. The photos do not establish prices, rate limits or a cost target; V1 reports token usage without claiming a monetary saving.

## Schedule and practical details

The guide places the event on Friday 23 October 2026 at Microsoft, 2 Kingdom Street, Paddington, London W2 6BD. Arrival is 08:30–08:50, with a 09:00 start and full-day attendance until approximately 18:00. Lunch is at 12:00; optional pizza/networking is approximately 18:00–18:30. Travel is self-funded. All times here are London local time.

`IMG_2281.jpeg` supplies the more specific pitch schedule:

| Time | Activity |
| --- | --- |
| 15:30 | Final preparation; everyone ready by 16:00 |
| 16:00 | Round 1 judging in rooms |
| 17:00 | Top three teams present to a senior joint panel in SBF |

Pitch format: eight-minute presentation/demo plus two-minute Q&A. The guide describes this as approximate and subject to on-the-day confirmation; the slide states the same durations.

The guide covers laptop/charger/ID, guest badges, registered-attendee access, preferred coding assistant readiness, familiarity with GitHub, inclusive teamwork, provided food and refreshments, onsite prayer facilities, and optional networking. It also contains pre-event attendance/LinkedIn confirmation requests with a 20 October deadline. No contacts or attendance actions were taken as part of this build.

## Teams and support

The guide says teams of four or five are mixed across disciplines and GenAI experience.

`IMG_2284.jpeg` shows Portobello Team 1 and Camden Team 1 on Level 8. The Portobello list includes Javier Fimia. Its shared-support panel names Benito Villa-Clarke, Alexander Ager, Graham Hogbin, Dhanyal Shahid, Thiviya Thavabalan, Delyn Choong and Matipa Marufu. Self-reported experience scores and the other attendee roster are not reproduced here because they are not needed by the app.

`IMG_2282.jpeg` introduces Microsoft and LSEG hack coaches across cloud, AI, software, data and service-delivery roles. It is a support reference; it adds no application feature requirement.

## V1 boundaries

The model supports a small US universe and horizons of 1–26 weeks. Risk appetite maps to assumed volatility limits. Placeholder token inputs are excluded in the app. Broad ethical/political alignment cannot be verified from this dataset and prompts clarification. No walk-forward backtest or demonstrated cost saving is claimed. See the root README for running, refreshing data and the integration details.
