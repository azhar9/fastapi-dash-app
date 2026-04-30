# Finance primer — for a developer joining the Performance Team

A self-contained walkthrough of the finance vocabulary and math you
will hear in your first month on an asset-management Performance
Team. Written for someone fluent in code, new to finance.

Every concept follows the same pattern:

1. **Definition** — plain English.
2. **Why the Performance Team cares** — where it shows up day to day.
3. **Worked example** — real numbers, usually tiny enough to do in
   your head.
4. **Gotcha** — the thing that trips people up.

Where a concept is already implemented in the demo app, there's a
breadcrumb like `→ api/app/sql/risk/risk_metrics.sql`. Open that file
next to this doc and you'll see the abstract term and the concrete
code side by side.

---

## Table of contents

1. [The world of asset management](#part-1--the-world-of-asset-management)
2. [Securities and portfolios — the nouns](#part-2--securities-and-portfolios--the-nouns)
3. [Returns — the single most-used concept](#part-3--returns--the-single-most-used-concept)
4. [Risk — the how-painful-is-it numbers](#part-4--risk--the-how-painful-is-it-numbers)
5. [Risk-adjusted returns — the ratios](#part-5--risk-adjusted-returns--the-ratios)
6. [Attribution — THE job of the Performance Team](#part-6--attribution--the-job-of-the-performance-team)
7. [GIPS — the standard that governs everything you compute](#part-7--gips--the-standard-that-governs-everything-you-compute)
8. [Fixed income basics](#part-8--fixed-income-basics)
9. [Glossary — rapid-fire definitions](#part-9--glossary--rapid-fire-definitions)
10. [Day-1 cheat sheet — decoding hallway conversations](#part-10--day-1-cheat-sheet--decoding-hallway-conversations)

---

# Part 1 — The world of asset management

## What an asset manager does

A bank gives you a savings account and pays you a little interest.
An asset manager does something different: **they take your money,
buy a basket of stocks/bonds/etc. on your behalf, and charge a fee
for managing that basket.** You end up owning a share of the basket.
If the basket goes up, your share goes up. The manager never owns
your money — they're fiduciaries, legally required to invest it for
*your* benefit.

Large asset managers run hundreds of billions, sometimes trillions,
of dollars. The biggest global names (BlackRock, Vanguard, State
Street) run multi-trillion books; a mid-to-large firm typically has
its own portfolio managers, sales teams, compliance, and reporting
teams — all operating semi-independently inside a bigger parent
bank or insurance company.

## The five roles you'll see in meetings

| Role | What they do | How they'll talk to you |
|---|---|---|
| **Portfolio Manager (PM)** | Decides what to buy and sell. Runs one or more portfolios. Takes the P&L hit or glory. | "Why is my YTD active return showing -12 bps when I was up 30 bps yesterday?" |
| **Analyst** | Researches individual securities or sectors to feed the PM ideas. | Quieter, more spreadsheets. |
| **Trader** | Executes the PM's decisions in the market. Cares about best execution. | "Did you see slippage on that block trade?" |
| **Performance Analyst** (your team) | Calculates returns, attribution, risk. Produces client reports. Hunts down data issues. | "The attribution numbers don't reconcile to the total return — can you look at the sector mapping?" |
| **Ops / Middle Office** | Books trades, reconciles positions, handles corporate actions (dividends, splits). | "The holdings file landed 45 minutes late because of a stock split on ABC." |
| **Client-facing / RM** | Relationship managers and salespeople. Talk to the pension fund, the adviser, the adviser's client. | "The client wants a call about last quarter's underperformance." |

You will mostly talk to PMs and analysts. Expect to be asked for
ad-hoc calculations ("what was our performance in healthcare last
quarter, gross of fees?") on short notice.

## Two kinds of clients

- **Retail** — individuals who buy mutual funds or ETFs through an
  adviser or a brokerage. They own *units* of the fund. The fund's
  price (NAV per unit) is published daily.
- **Institutional** — pension plans, endowments, insurance companies,
  corporate treasuries. They hand the manager a big cheque and
  negotiate a custom **mandate** ("manage this $500M of large-cap
  equity against the S&P 500 benchmark, max 5% in any one name, no
  tobacco stocks"). The portfolio is often a **Separately Managed
  Account (SMA)** — the client legally owns the underlying
  securities, not units of a pooled fund.

Different reporting expectations:
- Retail funds → daily NAV, monthly fact sheets, public performance.
- Institutional → custom report packs, quarterly attribution, often
  GIPS-compliant composite returns.

## The three charts that describe the business

If you zoom out, every asset manager's scorecard is three charts:

1. **Inflows/outflows** — did clients give us more money or pull it
   out this quarter?
2. **Performance** — did our funds beat their benchmarks?
3. **Fees and margin** — are we charging enough to cover our costs?

Everything the Performance Team does feeds into chart #2. When chart
#2 looks bad, chart #1 follows (clients redeem), and chart #3
follows (smaller AUM → less fee revenue). That's why performance
reporting is high-stakes.

## What the Performance Team actually does, day by day

- Cut daily, monthly, quarterly returns for every fund and composite.
- Compare to benchmarks, produce active-return numbers.
- Decompose active return into attribution (allocation, selection).
- Calculate risk stats: volatility, tracking error, Sharpe,
  information ratio, beta, VaR, drawdown.
- Feed numbers into fact sheets, client reports, regulatory filings.
- Field one-off questions from PMs, clients, compliance.
- Investigate data issues ("why did the fund's return jump 40 bps
  overnight? Oh — we were missing a dividend accrual for three days").

Your developer role on this team is to build and maintain the tools
that do all of the above. The three existing Dash apps you'll inherit
are those tools.

---

# Part 2 — Securities and portfolios — the nouns

Before we get to returns and risk, nail down the nouns. Imprecise
language here is why people get confused three conversations later.

## Stock (equity, share)

**Definition.** A share of ownership in a company. If you own one
share of Apple and Apple has 15 billion shares outstanding, you own
1/15,000,000,000 of the company.

**Worked example.** You buy 1 share of AAPL at $180. Apple reports
great earnings; the stock moves to $200. You now own a share worth
$200. You made $20 — but only on paper, until you sell.

**Gotcha.** "Owning a stock" doesn't give you much practical power
(one vote at the AGM you'll never attend). The value is the claim on
future cash flows (dividends) and the market's willingness to pay
more later.

## Bond (fixed income, FI)

**Definition.** An IOU. You lend money to a company or government;
they promise to pay you a fixed stream of interest (called the
**coupon**) and return your principal on a fixed date (**maturity**).

**Worked example.** The US Treasury issues a 10-year bond with a 3%
coupon and a $1,000 face value. You buy one at issuance for $1,000.
The Treasury pays you $30/year (a 3% coupon on $1,000) for 10
years, then returns your $1,000 at year 10. Your total cash
received: $300 + $1,000.

**Gotcha.** Bonds *trade* after issuance at prices that aren't
$1,000. If interest rates rise after you buy, new bonds pay more
coupon, and yours looks less attractive — so its market price drops.
This is the single most important thing about bonds: **price and
yield move in opposite directions.**

## Cash / money-market / T-bills

**Definition.** Very short-term, very safe instruments. Three-month
government T-bills, overnight commercial paper, the fund's chequing
account. Nearly zero credit risk, nearly zero price movement.

**Why the team cares.** Most funds hold a small cash buffer (1–3%)
for redemptions and trade settlement. When the PM is uncertain, cash
goes up. Cash drags on performance in rising markets and cushions in
falling markets.

## Alternatives

**Definition.** Anything that isn't listed equity, listed bonds, or
cash. Private equity, real estate, hedge funds, infrastructure,
commodities. Large asset managers usually have an alternatives arm,
but their public mutual funds are typically just equity and fixed
income.

**Gotcha.** Alternatives don't have daily market prices. They get
valued quarterly by committees or appraisers. This makes their
reported volatility artificially low — a well-known phenomenon called
"volatility laundering."

## Asset class vs. sector vs. region

These three dimensions slice the investment universe. A single stock
sits at one point in each:

| Dimension | Values |
|---|---|
| **Asset class** | Equity, Fixed income, Cash, Alternatives |
| **Sector** | Technology, Financials, Health care, Energy, Consumer discretionary, Consumer staples, Utilities, Industrials, Materials, Communication services, Real estate |
| **Region** | US, International developed, Emerging markets |

Apple (AAPL) is Equity / Technology / US.
SAP (SAP) is Equity / Technology / International developed.
A US Treasury 10-year bond is Fixed income / Government / US.

Benchmarks and attribution reports are usually organised along these
dimensions.

"Shopify" and "Apple" are just stand-in examples — swap in whatever
securities are in your actual universe.

## Portfolio, AUM, NAV, position, holding — disambiguated

These five words get used almost interchangeably, but they mean
different things. One example to tie them together:

```
You manage a fund. Today it has:
  - 1,000 shares of AAPL, priced at $200 → $200,000
  -   500 shares of MSFT, priced at $400 → $200,000
  -   cash                              → $100,000
  - total                               → $500,000
```

- **Portfolio** — the whole collection. "The Large-Cap Equity
  portfolio bought 200 more shares of Apple yesterday."
- **Holding** / **position** — one line item in the portfolio. "Our
  AAPL holding is $200,000." "We hold 1,000 shares of AAPL."
  "Position" leans slightly more toward the market-facing framing
  ("we opened a position in NVDA this week").
- **Weight** — the fraction each holding represents of the total.
  AAPL is $200k / $500k = 40% of the portfolio. Weights always sum
  to 100%.
- **AUM** (Assets Under Management) — the total dollar size of the
  portfolio. Here, $500,000. For a firm, AUM is the sum across every
  portfolio they run. Mid-to-large asset managers have AUM measured
  in the hundreds of billions.
- **NAV** (Net Asset Value) — the total dollar value of the
  portfolio, after subtracting any liabilities. For a plain long-only
  mutual fund, NAV ≈ AUM. For a hedge fund with borrowings, NAV = AUM
  − liabilities.
- **NAV per unit** — NAV divided by the number of fund units
  outstanding. This is the price a retail investor sees when they buy
  or sell a unit of the fund. If the fund has NAV $500,000 and 50,000
  units outstanding, NAV per unit = $10.00.

**Gotcha.** People casually say "the NAV went up 50 bps today"
meaning the NAV per unit went up 50 bps. Context usually makes it
obvious, but when it doesn't, ask.

→ In the demo app, `portfolio_nav` (the Postgres matview) computes
daily NAV as `Σ weight × adjusted_close` for each portfolio. Open
`db/init/001_schema.sql` and scroll to the `CREATE MATERIALIZED
VIEW` block.

---

# Part 3 — Returns — the single most-used concept

Returns are how you measure "did we make money, and how much."
Everything else (risk-adjusted metrics, attribution, rankings)
ultimately traces back to a return calculation. Getting returns right
is 80% of what the Performance Team does.

## Simple (arithmetic) return

**Definition.** The percentage change in value over a period.

```
r = (V_end / V_start) - 1
```

**Worked example.**

```
Start of day:  NAV per unit = $10.00
End of day:    NAV per unit = $10.15

Daily return = (10.15 / 10.00) - 1 = 0.015 = 1.5%
```

**Gotcha.** Simple returns don't compose across periods by adding.
+10% then −10% is not 0%, it's −1% (`1.10 × 0.90 = 0.99`).

→ `api/app/sql/performance/rolling_metrics.sql` computes daily
returns as `nav / LAG(nav) OVER (ORDER BY as_of_date) - 1`. That's
this formula, one day at a time, using a window function.

## Price return vs. total return

**Price return** ignores dividends. **Total return** includes them
(reinvested).

**Worked example.** You buy a stock at $100. During the year, it
pays a $2 dividend. At year-end, the price is $108.

```
Price return =  (108 - 100) / 100       = 8%
Total return = ((108 - 100) + 2) / 100  = 10%
```

**Why the team cares.** Mutual funds almost always quote **total
return** (they reinvest dividends automatically). Indexes come in
both flavours. Benchmarks for comparison must match the flavour of
the portfolio return — don't compare a total-return portfolio to a
price-only index, or you'll show a flattering lie.

**Gotcha.** In price-data vendors' terminology, **Close** is the
raw closing price; **Adjusted Close** bakes in dividends and splits
so the series is continuous for return calculation. **Use adjusted
close for return math.** The demo app stores both (`prices.close` and
`prices.adj_close`) and the matview uses `adj_close`.

## Log return

**Definition.**

```
r_log = ln(V_end / V_start)
```

**Why it exists.** Log returns are **additive across time**. If
Monday's log return is 1% and Tuesday's is 2%, the two-day log
return is exactly 3%. Simple returns don't compose that cleanly
(they multiply). That makes log returns friendlier for statistical
work — sums, means, regressions, time-series models.

**Worked example.**

```
V0 = 100, V1 = 110, V2 = 121

Simple returns: r1 = 10%, r2 = 10%; 2-day = (1.10 × 1.10) - 1 = 21%
Log returns:    r1 = ln(1.10) = 9.53%, r2 = 9.53%; 2-day = 19.06% = ln(1.21)
```

Same fact, two encodings.

**Gotcha.** Client reports always use simple/arithmetic returns.
Internal modelling often uses log. Don't mix them in the same table
without labelling.

## Cumulative return

**Definition.** The total growth from the start of a period, usually
expressed as a percentage.

**Worked example.** A portfolio returns (simple) 2%, −1%, 3%, 0.5%
over four days.

```
Cumulative = (1.02 × 0.99 × 1.03 × 1.005) - 1
           = 1.0459... - 1
           = 4.59%
```

Note how it's the product of `(1 + r_t)`, minus 1.

→ `api/app/sql/performance/cum_returns_vs_bench.sql` does this with
`FIRST_VALUE`: it divides every day's NAV by the very first NAV in
the window and subtracts 1. Same result, using prices instead of
returns.

## Geometric mean return (CAGR)

**Definition.** The constant rate that, if compounded every period,
would reproduce the observed ending value.

```
CAGR = (V_end / V_start)^(1 / n) - 1    where n = number of periods
```

**Why geometric instead of arithmetic mean.** A portfolio that
returns +50% then −50% has an arithmetic mean of 0% but is actually
down 25% (`1.5 × 0.5 = 0.75`). The geometric mean captures this
correctly:

```
geometric mean = (0.75)^(1/2) - 1 = -13.4%
```

**Gotcha.** The arithmetic mean always ≥ the geometric mean, with
equality only if every return is identical. When someone says "our
average return was 8% a year," ask: arithmetic or geometric? For
multi-year performance, geometric (CAGR) is the right number.

## Annualisation

**Definition.** Converting a return measured over one period (daily,
monthly) into the equivalent annual rate, so returns are comparable
across different horizons.

```
annualised_return = (1 + r_period)^(periods_per_year) - 1
```

**Standard period counts:**

| Period | Periods per year | Notes |
|---|---|---|
| Daily (business days) | 252 | Trading calendar |
| Weekly | 52 | |
| Monthly | 12 | |
| Quarterly | 4 | |

**Worked example.** Your fund returns 0.5% in a month.

```
annualised = (1.005)^12 - 1 = 6.17%
```

**Gotcha.** Annualising a single month's return is almost always
misleading — it's fine as a back-of-envelope sanity check, never a
client-facing number. For client reports, quote the actual period
("up 0.5% in February") and only annualise multi-year horizons.

## Reporting periods — MTD, QTD, YTD, ITD, 1Y, 3Y, 5Y

The vocabulary of "what span of time are we looking at":

| Acronym | Meaning | Example (as of 17 Apr 2026) |
|---|---|---|
| **MTD** | Month-to-date — from the last day of the previous month. | 1 Apr → 17 Apr |
| **QTD** | Quarter-to-date. | 1 Apr → 17 Apr |
| **YTD** | Year-to-date. | 1 Jan → 17 Apr |
| **ITD** | Inception-to-date — from the fund's launch. | 1 Jun 2018 → 17 Apr 2026 |
| **1Y / 3Y / 5Y / 10Y** | Trailing windows from today back N years. | 17 Apr 2021 → 17 Apr 2026 |
| **Since inception** | Same as ITD. Usually annualised if > 1 year. | |

→ `api/app/sql/portfolios/kpi_summary.sql` computes MTD and YTD
returns using a clever trick: `date_trunc('month', today)` gives the
first of the month; subtract one day to get the last trading day of
the previous month ("the MTD anchor"). Go look at the `anchors` CTE.

**Gotcha.** "1Y return" and "YTD return in January" are not the same
thing. 1Y always looks 365 days back; YTD looks back to Jan 1. In
mid-January, YTD is tiny and 1Y is almost a full year. Clients
confuse these constantly.

## Time-weighted return (TWR) vs. money-weighted return (MWR / IRR)

**This is THE concept for a Performance Team.** It's the one thing
that will separate you from someone who's been on the team six
months, if you know it on day one.

### The problem

Suppose your fund starts January with $1M. It earns +10% in January.
End of January, the client deposits another $9M. February has
terrible returns — the fund loses 5%. End of February, the balance
is:

```
Jan start:  $1,000,000
Jan end:    $1,100,000    (+10%)
Deposit:    +$9,000,000
Feb start:  $10,100,000
Feb end:    $9,595,000    (-5%)
```

**Question: what was the fund's return over the two months?**
Depends on who's asking.

### Time-weighted return (TWR) — measures the manager

Chain-link the return of each sub-period *between cash flows*:

```
Jan period return:  +10%
Feb period return:  -5%
TWR = (1.10 × 0.95) - 1 = +4.5%
```

The deposit is *invisible* in TWR. TWR tells you "if you'd put $1
in at the start and not touched it, what would you have at the end?"
It measures **the manager's skill**, not the client's experience.

### Money-weighted return (MWR) — measures the client

Money-weighted return is the **Internal Rate of Return (IRR)** — the
single discount rate that makes the present value of all cash flows
(including the $9M deposit) equal to the final balance.

Because most of the $10M was in the fund only during February (when
it lost 5%), the client's dollar-weighted experience is close to −4%,
not +4.5%.

```
TWR: +4.5%   (manager's skill, cash-flow-neutral)
MWR: about -3.8%  (client's lived experience)
```

### Why it matters

- **GIPS requires TWR** for composite-level reporting. Because TWR
  neutralises cash flows, it's the fair way to compare one manager to
  another.
- **MWR is the right number to show a client** who wants to know
  "how much money did I actually make?" — because it accounts for
  *when* they put money in.
- Retail fund fact sheets: TWR.
- Pension plan statements: often MWR (because the plan sponsor cares
  about dollar outcomes, not idealised manager skill).

**Gotcha.** A manager whose fund grew well *before* a big deposit
and then did poorly looks great by TWR and terrible by MWR. Neither
is wrong; they answer different questions. When a client asks about
their return, *always* clarify which one you're giving them.

**One more gotcha.** "Daily TWR" just means computing returns
between every close (so every cash flow lands at a day boundary) and
chain-linking them. It's TWR with the sub-periods being single days.
This is what modern systems produce by default.

## Net of fees vs. gross of fees

Two ways to quote the same return:

- **Gross** — before the management fee is deducted. This is what the
  portfolio's raw holdings produced.
- **Net** — after fees. This is what the client actually gets.

```
Gross return: +8%
Annual fee:   -1%
Net return:  ~+7%
```

**Why both exist.** Gross lets you compare one manager to another
without fee noise. Net is the honest number for the client. GIPS
requires both to be reported on client-facing materials.

**Gotcha.** Fees compound. A 1% annual fee over 20 years costs about
22% of ending wealth, not 20%. Fee-aware compounding matters for
long-term projections.

---

# Part 4 — Risk — the how-painful-is-it numbers

Return tells you what you made. Risk tells you how bumpy the ride
was, and how bad the bad days looked. Every risk metric below is
either a *dispersion* measure (how spread out returns were) or a
*tail* measure (how bad were the worst cases).

## Variance and standard deviation

**Definition.** Variance is the average squared deviation of returns
from their mean. Standard deviation is the square root of variance
— same idea, in the same units as returns.

```
variance = (1/(n-1)) × Σ (r_i - mean(r))^2
std dev  = sqrt(variance)
```

**Why the team cares.** Standard deviation of returns *is*
volatility, the headline risk number for almost every fund.

**Worked example.** Three daily returns: `+1%, -2%, +3%`.

```
mean         = (1 - 2 + 3) / 3          = +0.67%
deviations   = +0.33%, -2.67%, +2.33%
squared      = 0.0011, 0.0711, 0.0544
sum          = 0.1266
variance     = 0.1266 / 2               = 0.0633     (sample, dividing by n-1)
std dev      = sqrt(0.0633)             = 25.2% (in "percent" units)
```

**Gotcha.** Sample (n−1) vs. population (n) variance. For returns
from a limited observed window, use **sample** (`n-1`). Postgres's
`STDDEV_SAMP` is sample; `STDDEV_POP` is population. We use
`STDDEV_SAMP` in `rolling_metrics.sql`.

## Volatility and annualisation

**Definition.** Volatility is standard deviation of returns,
typically expressed annualised.

```
annualised_vol = std_dev_of_daily_returns × sqrt(252)
```

**Why `sqrt(252)`?** If daily returns are (roughly) independent,
their variances add over days. After 252 trading days, variance is
252× as big; standard deviation (its square root) is `sqrt(252) ≈
15.87` times as big.

**Typical ranges:**

| Asset | Annualised vol |
|---|---|
| 3-month T-bill | ~0% (effectively riskless) |
| Investment-grade bond fund | 3–6% |
| Balanced fund (60/40) | 8–12% |
| Large-cap equity index (S&P 500) | 14–18% |
| Small-cap / emerging-market equity | 20–30% |
| Individual volatile stock (Tesla) | 40–60% |

**Gotcha.** "Independent returns" is a lie. Real returns are slightly
autocorrelated and have fat tails. The sqrt(252) rule still works as
a convention, but it underestimates crisis-period risk. That's what
VaR and drawdown try to capture separately.

→ `api/app/sql/risk/risk_metrics.sql`:
`STDDEV_SAMP(r) * SQRT(252) * 100` is the annualised volatility.

## Drawdown and max drawdown

**Definition.** Drawdown is the loss from the peak value so far. Max
drawdown is the worst (most negative) drawdown ever observed.

```
drawdown_t = (V_t / running_peak_up_to_t) - 1
max_dd     = min over t of drawdown_t    (most negative value)
```

**Why the team cares.** Volatility treats upside and downside
symmetrically; max drawdown captures only the pain. Clients
viscerally care about "how much did I temporarily lose." A fund with
a −40% max drawdown is a harder sell than one with −15%, even if
both ended up positive.

**Worked example.**

```
Day 1:  NAV = 100 → peak = 100, dd =   0%
Day 2:  NAV = 110 → peak = 110, dd =   0%
Day 3:  NAV =  99 → peak = 110, dd = -10%
Day 4:  NAV = 105 → peak = 110, dd =  -4.5%
Day 5:  NAV =  95 → peak = 110, dd = -13.6%
Day 6:  NAV = 120 → peak = 120, dd =   0%    (new peak, drawdown resets)

Max drawdown over this window = -13.6%.
```

**Gotcha.** Max drawdown is path-dependent. Two portfolios with the
same final NAV can have very different max drawdowns. Also: the
"recovery period" (how long it took to get back to the prior peak)
matters almost as much to clients as the depth.

→ `api/app/sql/risk/risk_metrics.sql`:
```
MAX(nav) OVER (ORDER BY as_of_date
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS peak
```
then `MIN((nav/peak - 1))`. That's the running peak, then the deepest
proportional shortfall from it.

## Value at Risk (VaR)

**Definition.** VaR at the 95% level is "the loss that will be
exceeded only 5% of the time." Typically reported daily.

```
VaR_95% = 5th percentile of daily returns (a negative number)
```

**Worked example.** You have 1,000 days of return history. Sort them
from worst to best. The 50th-worst return is approximately the 5th
percentile.

```
Returns sorted (worst first):
  -4.2%  -3.8%  -3.5%  -3.1%  ...  (positions 1, 2, 3, 4, ...)

50th value from the worst side   → -1.5%
So VaR_95% = -1.5%  ("on 5% of days, we lose at least 1.5%")
```

**Two ways to compute it:**

- **Historical VaR** — just sort actual past returns and pick the
  percentile. Simple, makes no distributional assumption. Our app
  uses this (`PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY r)`).
- **Parametric VaR** — assume returns are normal with mean μ and
  standard deviation σ; then `VaR_95% ≈ μ - 1.645 × σ`. Cleaner, but
  lies in crisis periods because real returns have fat tails.

**Gotcha.** VaR tells you *a threshold*, not *how bad the worst
cases are*. The 5% of days beyond the threshold could be uniformly
−1.5% (benign) or range from −1.5% to −40% (catastrophic). That's
why risk teams also use **Conditional VaR (CVaR / Expected
Shortfall)** — the *average* return on those worst 5% days — which
actually answers "when it's bad, how bad?"

## Downside deviation

**Definition.** Standard deviation but only using returns *below* a
threshold (usually zero or the risk-free rate).

**Why it exists.** If your fund is asymmetric — lots of small losses
and occasional big gains — volatility makes it look risky. But
investors don't actually mind upside volatility. Downside deviation
ignores good days and only measures the bad ones.

**Used in:** the Sortino ratio (Part 5).

**Gotcha.** Downside deviation is sensitive to the threshold you
pick. "Below zero" and "below the risk-free rate" give different
numbers. Agree on the threshold before quoting.

## Beta

**Definition.** How sensitive your portfolio's returns are to the
benchmark's returns.

```
beta = cov(portfolio_returns, benchmark_returns) / var(benchmark_returns)
```

**Interpretation:**

| Beta | Meaning |
|---|---|
| 1.0 | Moves in lockstep with the benchmark |
| 1.3 | Amplifies benchmark moves by 30% (more volatile) |
| 0.7 | Dampens benchmark moves by 30% (more defensive) |
| 0.0 | Uncorrelated — independent of the benchmark |
| Negative | Moves opposite to the benchmark (rare for long-only equity funds) |

**Worked example.** The benchmark returns +2% on a given day. A
fund with beta 1.2 would, on average, return about +2.4% that day
(plus whatever idiosyncratic noise; +2% × 1.2).

**Why the team cares.** Beta tells you how much of your return came
"for free" by taking on market risk vs. from the manager's actual
stock-picking. If the benchmark went up 20% and you went up 20%,
that's expected if your beta is 1.0 — zero evidence of skill.

→ `api/app/sql/risk/risk_metrics.sql`:
`COVAR_POP(r, r_b) / VAR_POP(r_b)` straight out of the definition.

**Gotcha.** Beta is a single number computed over some window. It
changes with the window and over time. "Our beta is 0.9" is a
snapshot, not a fixed property.

## Tracking error (active risk)

**Definition.** The standard deviation of the portfolio's return
minus the benchmark's return, annualised.

```
active_return_t = r_portfolio_t - r_benchmark_t
tracking_error  = stddev(active_return) × sqrt(252)
```

**Interpretation.** Tracking error is how much your day-to-day
returns *wander* around the benchmark's. A plain index fund has TE
near 0 — it barely deviates from the benchmark. An aggressive
active fund might have 5–10% TE.

**Typical ranges:**

| Style | Tracking error |
|---|---|
| Passive index fund | 0.05 – 0.30% |
| Enhanced index (tilted) | 0.5 – 1.5% |
| Active core equity | 2 – 5% |
| Concentrated high-conviction | 5 – 10%+ |

**Why the team cares.** Clients pay active management fees to get
*different* returns than the benchmark. Zero tracking error means
you're a closet indexer — the client is paying active fees for
passive returns. Mandates often have TE constraints ("target
tracking error between 2% and 4%").

**Gotcha.** Low tracking error doesn't mean "low risk." It means
"closely tracks the benchmark." If the benchmark drops 30%, a 0% TE
fund drops 30% too.

---

# Part 5 — Risk-adjusted returns — the ratios

Four main ratios. Each asks: "per unit of [some kind of risk], how
much return did we earn?"

## Sharpe ratio

**Definition.** Excess return (above the risk-free rate) divided by
total volatility.

```
Sharpe = (portfolio_return - risk_free_rate) / volatility
```

All three terms annualised.

**Interpretation.** Higher is better. Sharpe > 1 is respectable, > 2
is excellent, > 3 is suspicious (either a crowded trade about to
reverse, or fraud).

**Worked example.**

```
Portfolio return:     10% annualised
Risk-free rate:        4% annualised
Portfolio vol:        12% annualised

Sharpe = (10 - 4) / 12 = 0.50
```

**Gotcha.** Sharpe penalises upside volatility too, which most
investors don't care about. It also assumes returns are
normally-distributed, which they aren't. It's the most-quoted metric
for a reason (it's simple), and the most-criticised metric for a
reason (it's too simple).

→ `api/app/sql/risk/risk_metrics.sql` computes Sharpe as
`(POWER(1+AVG(r), 252) - 1) / (STDDEV_SAMP(r) * SQRT(252))`.
Risk-free rate is assumed 0 for the demo, which is fine in practice
when rates are low or for relative comparison.

## Sortino ratio

**Definition.** Like Sharpe, but only divides by *downside*
deviation.

```
Sortino = (portfolio_return - risk_free_rate) / downside_deviation
```

**Why it exists.** Fixes the "penalises upside" complaint about
Sharpe. For asymmetric strategies (options, trend-following) Sortino
is fairer.

**Interpretation.** Higher is better. Sortino > Sharpe for the same
portfolio, because the denominator is smaller (only bad days count).

**Gotcha.** Sortino depends on the downside threshold. Compare
Sortinos only when they were computed with the same threshold.

## Information ratio (IR)

**Definition.** Active return (over the benchmark) divided by
tracking error.

```
IR = (portfolio_return - benchmark_return) / tracking_error
```

**This is the single most important ratio for an active PM.** It
says: "for every unit of risk you took by *deviating* from the
benchmark, how much excess return did you earn?" Sharpe rewards
beating the risk-free rate; IR rewards beating the benchmark
*efficiently*.

**Worked example.**

```
Portfolio: +10% annualised
Benchmark:  +8% annualised   → active return = +2%
Tracking error:  4% annualised

IR = 2% / 4% = 0.50
```

**Rules of thumb:**

| IR | Interpretation |
|---|---|
| 0.5 | Good |
| 0.75 | Very good |
| 1.0+ | Exceptional (rare and usually not sustained) |

**Gotcha.** IR can be gamed with a long enough track record of tiny
outperformance. A "closet indexer" with 0.1% active return and 0.05%
TE has IR = 2.0, which looks spectacular but the raw dollars are
trivial. Always look at IR alongside absolute active return.

## Jensen's alpha

**Definition.** The portfolio return *above what its beta would
predict* from the benchmark.

```
alpha = r_portfolio - [r_rf + beta × (r_benchmark - r_rf)]
```

The bracketed term is the Capital Asset Pricing Model (CAPM) return
— what you'd expect given the portfolio's market exposure.

**Interpretation.** Positive alpha = skill (the manager added value
beyond market exposure). Zero alpha = you got market-level returns
for your beta. Negative alpha = underperformance.

**Worked example.**

```
Risk-free:      4%
Benchmark:     10%
Portfolio:     14%
Beta:          1.2

Expected (CAPM) = 4 + 1.2 × (10 - 4) = 4 + 7.2 = 11.2%
Alpha           = 14 - 11.2          = +2.8%
```

The portfolio earned 2.8 percentage points more than its beta alone
would justify.

**Gotcha.** Alpha requires a beta estimate, which requires a
window of data. Different windows give different alphas. Clients
sometimes expect "alpha" to just mean "active return" — which is
`portfolio - benchmark`, ignoring beta. Be precise about which
you're quoting.

---

# Part 6 — Attribution — THE job of the Performance Team

A PM calls you: "We beat the benchmark by 80 basis points last
month. Why?"

"Why" is the attribution question. The answer is almost never "the
PM is just smart." It's usually "we were overweight tech (which
outperformed), and underweight financials (which also outperformed,
so that hurt us), and within healthcare we owned Eli Lilly instead
of Pfizer (which helped)."

Attribution is the mathematical machinery that decomposes an active
return into those effects.

## The basic decomposition

Active return = Portfolio return − Benchmark return.

The dominant framework is **Brinson-Hood-Beebower (BHB)**. It
decomposes active return into three effects *per sector* (or per
country, per factor — any partition):

```
Allocation_i   = (w_p_i - w_b_i) × (r_b_i - r_b_total)
Selection_i    = w_b_i × (r_p_i - r_b_i)
Interaction_i  = (w_p_i - w_b_i) × (r_p_i - r_b_i)

Active_total = Σ over i of (Allocation_i + Selection_i + Interaction_i)
```

Where:
- `w_p_i` = portfolio's weight in sector i
- `w_b_i` = benchmark's weight in sector i
- `r_p_i` = portfolio's return in sector i (return of our stocks in that sector)
- `r_b_i` = benchmark's return in sector i (return of the index's stocks in that sector)
- `r_b_total` = benchmark's total return

**Read each effect in English:**

- **Allocation_i**: "We bet sector i would do well (overweight) or
  poorly (underweight) relative to the benchmark. Was our bet right?"
  Positive if we overweighted a sector that beat the benchmark
  overall, or underweighted one that lagged.
- **Selection_i**: "Within sector i, did we pick better stocks than
  the benchmark's?" Positive if our stocks in sector i beat the
  benchmark's stocks in sector i.
- **Interaction_i**: A cross-term — selection amplified by our
  sector bet. Often small; sometimes bundled into selection.

Everything sums to the total active return. That's the reconciliation
test every attribution report has to pass.

## Worked example — two sectors

Benchmark is the S&P 500 split into Tech and Energy only (toy).

```
                Benchmark              Portfolio
                ---------              ---------
Tech            w=60%, r=+12%         w=80%, r=+15%
Energy          w=40%, r= +2%         w=20%, r= +3%

Benchmark total return = 0.60×12 + 0.40×2 = 8.0%
Portfolio total return = 0.80×15 + 0.20×3 = 12.6%
Active return         = 12.6 - 8.0     = +4.6%
```

Now decompose:

### Allocation effect

"Did we bet on the right sectors?"

```
Tech:    (w_p - w_b) × (r_b_sector - r_b_total)
       = (0.80 - 0.60) × (0.12 - 0.08) = 0.20 × 0.04 = +0.80%
Energy:  (0.20 - 0.40) × (0.02 - 0.08) = -0.20 × -0.06 = +1.20%

Total allocation = +0.80 + 1.20 = +2.00%
```

Both allocation bets paid off. We overweighted tech (which beat the
benchmark total of 8%) and underweighted energy (which lagged the
8%), both correct calls.

### Selection effect

"Within each sector, did we pick better stocks than the index?"

```
Tech:    w_b × (r_p_sector - r_b_sector)
       = 0.60 × (0.15 - 0.12) = +1.80%
Energy:  0.40 × (0.03 - 0.02) = +0.40%

Total selection = +1.80 + 0.40 = +2.20%
```

Our Tech stocks beat the benchmark's by 3 pp, and our Energy stocks
by 1 pp. Good security selection.

### Interaction effect

```
Tech:    (w_p - w_b) × (r_p_sector - r_b_sector)
       = 0.20 × 0.03 = +0.60%
Energy:  -0.20 × 0.01 = -0.20%

Total interaction = +0.60 - 0.20 = +0.40%
```

### Reconciliation

```
Allocation  + Selection + Interaction
    +2.00%      +2.20%       +0.40%    =  +4.60%
```

Matches the active return (+4.6%). If it didn't, something's wrong
with the data — the most common cause is a security mis-mapped to
the wrong sector.

## How attribution is reported

Monthly attribution report for a PM might look like:

```
Sector                 Alloc    Sel     Int    Total
---------------------  ------  ------  ------  ------
Technology             +0.80   +1.80   +0.60   +3.20
Energy                 +1.20   +0.40   -0.20   +1.40
Financials             -0.30   -0.50   -0.05   -0.85
Healthcare             +0.10   +0.80   +0.01   +0.91
...
---------------------  ------  ------  ------  ------
Total                  +2.00   +2.20   +0.40   +4.60
```

The PM reads this top to bottom. The positive and negative numbers
tell the story of *why* the month looked the way it did.

## The practical pitfalls

- **Sector mapping** — every security must have a sector. If an ADR
  for a European bank is tagged "Financials" in your data but the
  benchmark provider tags it "Other," the math doesn't line up.
  Reconciliation breaks. 80% of attribution bugs are mapping bugs.
- **Cash as a sector** — many implementations treat cash as its own
  "sector" with zero return. If your benchmark has 0% cash and you
  hold 2% cash, that's an allocation bet with a known return drag.
- **Currency** — for global portfolios, active return has a currency
  component. Brinson can be extended to include a currency effect,
  or the return can be decomposed into "local currency return" +
  "FX return" before attribution. Ask which your team does.
- **Arithmetic vs. geometric attribution** — over short windows,
  sector effects roughly add. Over long windows they compound, and
  "geometric attribution" (more complex math) is used to reconcile
  cumulative active return.

## Currency attribution (one paragraph)

For global portfolios, your return in CAD is the asset's local
return plus the change in the local-currency-to-CAD exchange rate.
Currency attribution splits active return into:

1. Local-market allocation/selection (the Brinson pieces above),
   calculated in local currency.
2. Currency allocation — were we overweight or underweight certain
   currencies relative to the benchmark?
3. Currency selection — within a currency, did we pick instruments
   with favourable cross-rate exposure?

Most global mandates hedge FX at least partially; the attribution
has to show whether the hedging helped or hurt.

## Factor attribution (one paragraph)

Instead of sectors, decompose returns along **factors** (value,
momentum, size, quality, volatility, growth). Requires a factor-
model provider: **Barra** (MSCI), **Axioma** (Qontigo), **Northfield**.
They publish daily factor returns; the PM's portfolio loadings on
each factor times the factor returns give a factor attribution. Not
likely a day-one requirement; useful to know the vocabulary so you
recognise a "Barra exposure report" when it's emailed to you.

→ Your demo app doesn't implement attribution. This would be an
excellent feature to add — a natural week-2 project after you
understand the team's existing tooling.

---

# Part 7 — GIPS — the standard that governs everything you compute

## What GIPS is, in one paragraph

The **Global Investment Performance Standards (GIPS)** are a set of
ethical and methodological rules published by the **CFA Institute**
for how asset managers calculate and present performance. Claiming
"GIPS compliance" is voluntary but near-universal for institutional
managers — no serious pension fund will hire a manager who doesn't.
Most large asset managers claim GIPS compliance on their
institutional mandates. That means every performance calculation the
team produces that ends up in a client deck, pitch book, or fact
sheet has to be GIPS-defensible.

## Why GIPS exists

In the 1990s, asset managers reported whatever made them look best:
- Cherry-pick a top portfolio and quote *that*.
- Choose the start date that maximised returns (back-testing the
  marketing).
- Report gross of fees without saying so.
- Change benchmarks when the current one made you look bad.

GIPS closed these loopholes by requiring:

1. Returns on **every** fee-paying discretionary portfolio (no
   cherry-picking).
2. **Composites** — grouping portfolios by strategy so you're showing
   the *representative* return, not just your star.
3. **Required disclosures** — gross AND net of fees, benchmark,
   composite creation date, number of portfolios in the composite,
   composite dispersion.
4. **Time-weighted returns** at the composite level.
5. **Verification** — an independent firm checks compliance annually.

## The composite — the key concept

A GIPS composite is "the set of all portfolios run according to
strategy X, joined the composite when they started, left when they
changed strategy or closed."

Example: a firm's "Large-Cap Equity Core" composite contains every
institutional SMA managed to that strategy. Maybe 17 portfolios,
totalling $4.2B. The composite return is a weighted average of all
17 portfolios' returns each period.

**Why composites?** A new prospective client is asking "if I give you
money to run against this benchmark with this strategy, what's your
track record?" The composite answers "here's what we've done on
average for everyone with that mandate." Pulling out a single
flattering portfolio is misleading; the composite is honest.

## What a GIPS-compliant disclosure looks like

A client-facing performance table must show at least:

```
Large-Cap Core Composite

Period    Comp gross   Comp net   Benchmark   # ports   Dispersion   AUM
2020        +14.2%      +13.1%     +12.8%        15        0.8%     $3.2B
2021        +18.6%      +17.5%     +17.9%        16        1.1%     $3.9B
2022         -5.8%       -6.7%      -5.2%        17        1.4%     $3.4B
2023        +11.5%      +10.5%     +11.1%        17        0.9%     $3.7B
2024        +13.1%      +12.0%     +12.5%        17        1.2%     $4.0B

Composite inception: 2015-01-01
Benchmark: S&P 500 Total Return
Fee schedule: 75 bps on first $50M, 50 bps thereafter
```

- **Gross** = before fees
- **Net** = after fees
- **Dispersion** = std dev of the individual portfolios' returns
  within the composite. Low dispersion = consistent execution; high
  dispersion = different clients are getting different experiences
  (usually a red flag).

## What the Performance Team actually worries about

- **Mapping portfolios to composites correctly.** When a new
  institutional account is onboarded, it's classified into a
  composite based on its mandate. Misclassification is a GIPS breach.
- **Handling portfolio churn.** A client leaves? Their portfolio's
  history stays in the composite. A client switches strategies? They
  leave the old composite (all prior periods stay); they enter the
  new one at the switch date.
- **Discretionary vs. non-discretionary.** Only "discretionary"
  portfolios (where the manager has decision-making authority) go
  into a composite. Clients with heavy restrictions ("don't buy
  tobacco, mining, or anything starting with Q") may be classified
  non-discretionary and excluded.
- **Significant cash flows.** A portfolio that has a large client
  deposit/withdrawal mid-period is sometimes removed from the
  composite for that period to avoid distorting the composite return.
  The threshold is firm-policy.
- **Survivorship.** GIPS *forbids* removing a closed portfolio from
  the composite's history. Historical returns must include closed
  portfolios for the periods they were open. This is the opposite of
  what a marketing department might want.

## Verification

Annually, a firm like Deloitte or PwC comes in and audits the
compliance claim: do the composites include all mandates? Are the
returns calculated correctly? Are disclosures complete? If yes, a
**verification letter** is issued, which the firm cites in marketing.

Verification is typically annual. The team's calculations are part of
what gets verified.

---

# Part 8 — Fixed income basics

Fixed income is typically a substantial chunk of a diversified asset
manager's AUM — often 30–50% — mostly via bond mutual funds and
institutional mandates. You don't need to be an FI expert day one,
but you need the vocabulary so you can follow conversations.

## A bond in one paragraph

A bond is a promise: the issuer (government, company, bank) will
pay you **fixed coupons** (interest) at set intervals and return
your **principal** (the face value) on a **maturity date**. You pay
some price up front for that future cash-flow stream.

```
Buy a 5-year, 4% coupon, $1,000 face-value bond at issuance.

Today:  you pay $1,000.
Year 1: receive $40.
Year 2: receive $40.
Year 3: receive $40.
Year 4: receive $40.
Year 5: receive $40 + $1,000 = $1,040.
```

## Yield-to-maturity (YTM)

**Definition.** The single interest rate that, when used to discount
every future cash flow, makes the present value equal to today's
price.

Think of YTM as the bond's "return if you hold it to maturity and
reinvest coupons at the same rate." It's a summary of the whole
cash-flow stream as one number.

**Gotcha.** YTM changes as the bond's market price changes.
Bonds trade continuously after issuance. A bond bought at $1,000
with a 4% coupon might later trade at $950, giving a new buyer a
higher YTM (more bang per dollar paid). Or at $1,050, giving a new
buyer a lower YTM.

**The fundamental relationship: price and yield move in opposite
directions.** If rates rise in the economy, newer bonds pay more
coupon, so existing bonds with lower coupons become less attractive,
and their prices drop (which raises their YTM to match the new
market). If rates fall, existing high-coupon bonds become more
valuable, prices rise.

## Duration

**Definition.** How sensitive a bond's price is to a change in
interest rates. Expressed in years.

Quick intuition:

```
If duration = 5, and rates rise 1%, the bond's price falls ~5%.
If duration = 5, and rates fall 1%, the bond's price rises ~5%.
```

(The formal formula involves weighted average time to cash flows.
The intuition above is close enough for conversation.)

**Typical values:**

| Bond | Duration |
|---|---|
| 3-month T-bill | ~0.25 years |
| 5-year US Treasury | ~4.6 years |
| 10-year US Treasury | ~8.5 years |
| 30-year US Treasury | ~18 years |
| High-yield corporate | varies, often shorter |

**Why the team cares.** A portfolio's duration tells you how hard it
gets hit (or helped) when rates move. A bond fund with duration 7
will outperform cash by ~7% if rates fall 1%, and underperform by
~7% if rates rise 1%. PMs manage duration actively; attribution at
a bond fund often decomposes active return into a "duration effect"
(were we longer or shorter than the benchmark's duration?) and a
"curve effect" / "credit effect" / "selection effect."

**Gotcha.** "Modified duration" and "Macaulay duration" are two
related numbers. Macaulay is the weighted average time; modified is
Macaulay adjusted for the discounting step. For most conversation,
people mean modified duration when they say "duration."

## Convexity

**Definition.** A second-order correction: bonds don't respond to
rate changes exactly linearly. For big rate moves, duration alone
under-predicts the price response. Convexity captures the curvature.

**Rule of thumb.** For small rate changes (≤ 25 bps), duration alone
is fine. For bigger moves, convexity matters, and it's always
positive for plain vanilla bonds — price rises more than duration
predicts when rates fall, and falls less than duration predicts when
rates rise.

You'll see "duration, convexity" reported together on every bond-fund
fact sheet.

## Credit spread

**Definition.** The extra yield a corporate or emerging-markets bond
pays *above* a government bond of the same maturity, to compensate
for credit risk.

```
10-year government bond yield:               3.50%
10-year investment-grade corporate bond yield: 4.10%
Credit spread:                                0.60% = 60 basis points
```

**Why it exists.** A corporation could default; a developed-economy
government (effectively) can't. Investors demand a premium for
taking that risk.

**Investment grade vs. high yield:**

| Rating | Credit spread (approximate) |
|---|---|
| AAA / AA | 20 – 50 bps |
| A | 50 – 80 bps |
| BBB | 80 – 150 bps |
| BB (junk) | 200 – 400 bps |
| B | 400 – 600 bps |
| CCC | 1000+ bps |

**When spreads widen.** Credit spreads balloon during market stress
(2008: investment-grade spreads tripled in weeks). This hurts
corporate-bond-fund performance even if government yields didn't
move.

## Fixed-income performance and attribution

Active return on a bond portfolio typically decomposes into:

1. **Duration effect** — our duration vs. benchmark's × the parallel
   rate move
2. **Curve effect** — we were concentrated in 5-year bonds while the
   benchmark had 10-year; the curve steepened
3. **Sector / credit effect** — we were overweight corporates vs.
   government; spreads tightened, we benefited
4. **Selection effect** — within corporates, we picked one issuer
   over another that had a credit downgrade
5. **Currency effect** — global bond funds only

The team often runs these decompositions monthly for FI PMs.

---

# Part 9 — Glossary — rapid-fire definitions

One-liner reference. Skim once, re-read whenever a term shows up
that you've forgotten.

- **Active return** — portfolio return minus benchmark return.
- **Active share** — fraction of the portfolio that differs from the
  benchmark (sum of `|w_port - w_bench|` / 2). 0% = closet indexer;
  100% = no overlap with benchmark. Typical active fund: 60–85%.
- **Alpha** — return above what CAPM predicts from beta; in casual
  use often synonymous with active return.
- **Alpha generation** — the act of actively trying to beat the
  benchmark.
- **Asset allocation** — the breakdown of a portfolio by asset class
  (e.g., 60% equity, 40% fixed income). Usually the highest-impact
  decision.
- **AUM** — Assets Under Management. Total dollars managed.
- **Basis point (bps)** — 1/100 of 1%, i.e. 0.01%. "We outperformed
  by 80 bps" means +0.80%.
- **Benchmark** — the index against which a portfolio is measured.
  S&P 500 for US large-cap equity; Bloomberg US Aggregate for US
  bonds; MSCI EAFE for international developed equity; MSCI EM for
  emerging markets.
- **Beta** — sensitivity to benchmark / market. Beta 1 = moves with
  market; > 1 amplifies; < 1 dampens.
- **Bid-ask spread** — the gap between the highest price a buyer
  will pay and the lowest a seller accepts. A cost of trading.
- **Carry** — the yield or income earned just from holding an asset,
  before any price changes. A 3% coupon bond has 3% carry.
- **CAPM** — Capital Asset Pricing Model. Relates expected return to
  beta × equity risk premium + risk-free rate.
- **CAGR** — Compound Annual Growth Rate. Geometric mean annual
  return.
- **CIO** — Chief Investment Officer. Head of a firm's investment
  function.
- **Composite** — GIPS term; group of portfolios run to the same
  strategy, reported as one.
- **Convexity** — second-order bond-price sensitivity to yield
  changes. Correction to duration.
- **Coupon** — a bond's periodic interest payment.
- **Covariance** — co-movement of two return series.
- **Credit spread** — extra yield on a corporate bond over a
  government bond of the same maturity.
- **CVaR / Expected Shortfall** — average return on the worst X% of
  days. Fills the gap VaR leaves.
- **Discretionary portfolio** — one where the PM has full
  decision-making authority (eligible for GIPS composites).
- **Dispersion** — spread of returns across portfolios within a
  composite. Low = consistent; high = suspicious.
- **Drawdown** — current shortfall from peak.
- **Duration** — bond price sensitivity to rate changes. In years.
- **ETF** — Exchange-Traded Fund. Like a mutual fund but trades on
  an exchange intraday.
- **Fact sheet** — one- or two-page monthly/quarterly summary of a
  fund's performance, used in marketing.
- **Fixed income (FI)** — bonds.
- **FX** — foreign exchange (currencies).
- **GIPS** — Global Investment Performance Standards.
- **Gross of fees** — return before management fees.
- **High-water mark** — in hedge funds, the prior peak NAV level
  above which performance fees are charged.
- **Holding** — a single security position in a portfolio.
- **Hurdle rate** — the minimum return a fund must earn before
  performance fees kick in.
- **Index** — a passive rule-based basket used as a benchmark
  (S&P 500, Russell 2000, Bloomberg US Aggregate Bond).
- **Information ratio (IR)** — active return / tracking error. The
  active-manager's Sharpe ratio.
- **Institutional** — clients that are organisations (pension plans,
  endowments, insurance companies), not individuals.
- **Jensen's alpha** — return in excess of CAPM's prediction.
- **Long-only** — a fund that only buys securities (never shorts).
  Most mutual funds.
- **Mandate** — a client's written instructions for how the
  portfolio must be managed (benchmark, constraints, objectives).
- **Mark-to-market** — valuing a position at current market price.
- **Maturity** — when a bond's principal is repaid.
- **Modified duration** — the usual meaning when people say
  "duration."
- **MWR / IRR** — money-weighted return. Accounts for cash flows.
- **Mutual fund** — pooled investment vehicle; priced daily at NAV.
- **NAV** — Net Asset Value.
- **Net of fees** — return after management fees.
- **OCIO** — Outsourced Chief Investment Officer. A service where
  an asset manager runs the entire investment function for a
  smaller institution.
- **Passive** — strategy that tries to match, not beat, a benchmark
  (index funds, ETFs).
- **Position** — a single holding, often with a directional flavour
  ("long AAPL," "short NVDA").
- **Principal** — the face value of a bond, repaid at maturity.
- **Rebalancing** — periodically trading to bring weights back to
  target levels as markets move them around.
- **Retail** — individual client (vs. institutional).
- **Risk-free rate** — yield on a short-term government bond; proxy
  for "zero risk."
- **Rolling return** — a return computed over a trailing window, at
  every date.
- **Sector** — industry grouping of a stock (Tech, Financials, ...).
- **Selection effect** — attribution: did we pick better stocks
  within each sector than the benchmark?
- **Sharpe ratio** — excess return over risk-free, divided by
  volatility.
- **SMA** — Separately Managed Account. An institutional account
  where the client owns the underlying securities directly.
- **Sortino ratio** — Sharpe but only downside deviation.
- **Spread** — can mean bid-ask spread OR credit spread; context.
- **Strategy** — the formal label for how a portfolio is managed
  ("US Large-Cap Value," "Global Small-Cap Growth").
- **Style drift** — when a portfolio's actual holdings stop matching
  its stated strategy. A compliance concern.
- **TNA** — Total Net Assets (synonymous with NAV for a fund).
- **Tracking error (TE)** — std dev of active return, annualised.
- **Turnover** — fraction of the portfolio that was bought/sold in
  a period (usually annual). High turnover = active/tactical; low =
  buy-and-hold.
- **TWR** — time-weighted return.
- **UCITS** — European equivalent of a mutual fund. You may see it
  if your firm sells to European clients.
- **Value at Risk (VaR)** — loss threshold at a confidence level.
- **Volatility** — annualised standard deviation of returns.
- **Yield** — the income return of a bond (multiple definitions;
  usually YTM).
- **YTM** — yield-to-maturity.

---

# Part 10 — Day-1 cheat sheet — decoding hallway conversations

You will overhear things in standups, PM reviews, and client calls
that sound cryptic on week one and obvious on week ten. Here are the
most common, translated.

---

> **"We outperformed the benchmark by 80 bps last month, net of fees."**

Our fund, after deducting management fees, returned 0.80 percentage
points more than its benchmark over the calendar month. Small number,
consistently delivered = good active manager.

---

> **"Most of it was allocation — we were overweight energy, which beat
> the broad market. Selection was a wash."**

We held more energy than the index did, and energy outperformed the
overall index, so the overweight bet paid off (positive allocation
effect). Within each sector, our specific stock picks were roughly
in line with the benchmark's stocks (zero net selection effect).

---

> **"We got killed on selection in healthcare — Lilly ripped, we
> didn't own it."**

Within the Healthcare sector, the benchmark's stocks outperformed
ours. Specifically, Eli Lilly had a huge move and we didn't hold
it. Negative selection effect in Healthcare.

---

> **"TE is running hot — we're tripping the 4% constraint."**

Tracking error (the std dev of our active returns) is elevated,
breaching the mandate's 4% limit. Risk committee will ask us to
reduce active bets.

---

> **"What's our Sharpe over the last 3 years?"**

Compute annualised return, subtract the average 3-month T-bill yield
over that window, divide by annualised volatility. One number,
trailing 3-year window.

---

> **"Can you pull the IR on the Tech overweight since we put it on?"**

Information ratio of our active Tech bet: ratio of the annualised
*active* return attributable to the Tech overweight to its tracking
error contribution. Usually a sub-portfolio / factor-attribution
question.

---

> **"Is that gross or net?"**

Are you showing me the return before or after management fees? If
you quote the wrong one in a client meeting, you've created a
potentially embarrassing gap between the PM's number and the
client's statement. Always clarify.

---

> **"What's the dispersion on the LCE composite this year?"**

Standard deviation of individual portfolios' returns within our
Large-Cap Equity composite. Low dispersion (~0.5%) = portfolios are
being managed consistently; high dispersion (~2%+) = something's
off (different clients getting different execution, or different
restrictions).

---

> **"The attribution doesn't reconcile — we're off by 4 bps."**

The sum of allocation + selection + interaction effects across all
sectors doesn't equal the total active return. Usually a data
problem: a security is mapped to the wrong sector, or a corporate
action (split, spinoff) wasn't processed correctly.

---

> **"We took out some duration this morning."**

Sold some longer-maturity bonds. The portfolio's duration (rate
sensitivity) is now lower. This is a tactical call — PM thinks
rates might rise and wants less price sensitivity.

---

> **"We're running 40 bps underweight the bench in financials but
> overweight the banks within it."**

The financials *sector* is 40 bps lower in our portfolio than in
the benchmark. But *within* financials, we've tilted toward banks
(and away from insurance, say). This is a deliberate pair of
decisions the PM can defend separately.

---

> **"What's our up-capture and down-capture vs the benchmark?"**

Up-capture: in months when the benchmark was positive, what % of
its return did we capture on average (>100 = we did better).
Down-capture: in months the benchmark was negative, what % of the
loss did we participate in (<100 = we did better). A strong active
manager often has up-capture > 100 and down-capture < 100.

---

> **"The fund's 1-year is red but YTD is green — what's going on?"**

Two different windows. "1-year" is the trailing 365 days. "YTD" is
from Jan 1. If last April was strong and this April is weak, the
trailing 1-year can look bad while YTD still looks fine.

---

> **"We showed up in GIPS's top quartile for 5-year IR."**

In a peer ranking of information ratios over the trailing 5 years,
our fund was in the best 25%.

---

> **"Can you rerun that with NAVs on a MWR basis? The client's asking."**

The client wants to know their dollar-weighted return — including
the impact of when they deposited and withdrew. TWR doesn't answer
that; compute an IRR on the portfolio's cash-flow stream for that
client.

---

# Closing thoughts

You don't need to memorise this doc. You need to have read it once,
*honestly*, and know where to look when a term comes up.

Print Part 10. Keep it in a drawer for your first month.

If you hit a term this doc doesn't cover, write it down. Ask a
colleague at lunch. It should go in Part 11.

Good luck, and welcome to the Performance Team.
