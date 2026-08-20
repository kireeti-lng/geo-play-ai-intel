import json
import os

# Path
OUTPUT_PATH = r"metric_catalogue\metric_catalogue.json"

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# (metric_id, metric_name, definition)
METRICS = [
    (
        "ad_arpdau",
        "Ad ARPDAU",
        "Ad ARPDAU is the quotient of gross advertising revenue recognized on a given day and the count of "
        "daily active users on that same day, expressed in currency units per user per day. Because the "
        "denominator comprises the entire active base rather than only ad-exposed users, the measure jointly "
        "reflects per-impression yield and the penetration of advertising across that base. It is therefore "
        "not recoverable from eCPM alone without also specifying impressions per DAU.",
    ),
    (
        "ad_arpu",
        "Ad ARPU",
        "Ad ARPU is gross advertising revenue accrued over a stated reporting period divided by the count of "
        "unique active users observed in that same period, most commonly a calendar month measured against "
        "monthly active users. It differs from Ad ARPDAU in the construction of the denominator, "
        "deduplicating users across the entire window rather than normalizing per day, and the two therefore "
        "diverge systematically as window length increases.",
    ),
    (
        "ad_ecpm_usd",
        "Ad eCPM (USD)",
        "Ad eCPM (USD) denotes effective cost per mille: gross advertising revenue divided by the number of "
        "ad impressions served, multiplied by one thousand, and denominated in United States dollars. It "
        "normalizes revenue against delivered inventory and is thus the canonical measure of per-impression "
        "yield, invariant to session volume or the size of the active user base. Comparison across "
        "placements or geographies is valid only when impression-counting conventions and currency "
        "conversion dates are held constant.",
    ),
    (
        "ad_engagement_rate",
        "Ad Engagement Rate",
        "Ad Engagement Rate is the proportion of ad impressions that elicit a qualifying user interaction, "
        "such as a click, a rewarded-video completion, or a playable interaction, divided by total "
        "impressions served over the same interval. The measure is format-sensitive, since rewarded and "
        "interstitial placements carry structurally different interaction propensities; aggregation across "
        "formats consequently requires explicit weighting to remain interpretable.",
    ),
    (
        "ad_impressions",
        "Ad Impressions",
        "Ad Impressions is the count of advertising creatives rendered and confirmed as viewable to players "
        "over a specified interval, attributed at the moment the mediation layer or network signals a "
        "successful display. As an unnormalized volume measure it scales with both audience size and ad "
        "load, and should therefore be interpreted alongside Impressions per DAU rather than in isolation.",
    ),
    (
        "ad_revenue_usd",
        "Ad Revenue (USD)",
        "Ad Revenue (USD) is the gross monetary value earned from advertising inventory over a stated "
        "interval, denominated in United States dollars following conversion from network-reported "
        "currencies. Because networks report first on an estimated and later on a reconciled basis, the "
        "measure is subject to retroactive restatement, and any reported figure should carry the "
        "reconciliation status of its source.",
    ),
    (
        "ad_users",
        "Ad Users",
        "Ad Users is the count of distinct players who received at least one ad impression within a specified "
        "interval. It is a proper subset of the active user population for that interval, and the ratio of "
        "the two quantifies advertising reach. Distinguishing it from Daily Active Users is essential "
        "because it forms the denominator of Impressions per Ad User.",
    ),
    (
        "anr_rate",
        "ANR Rate",
        "ANR Rate is the incidence of Application Not Responding events, in which the main thread remains "
        "unresponsive beyond the platform-defined latency threshold, normalized against a stated exposure "
        "base of sessions or user-days. Unlike Crash Rate, which counts involuntary process termination, ANR "
        "Rate captures liveness failures in which the process survives; the two are disjoint event classes "
        "and must not be summed into a single stability figure.",
    ),
    (
        "arpdau",
        "ARPDAU",
        "ARPDAU is total revenue recognized on a given day, aggregating in-app purchase and advertising "
        "streams, divided by the count of daily active users on that day. It is the standard daily "
        "monetization yardstick in free-to-play analytics because it holds audience size constant and "
        "thereby isolates monetization intensity from growth. Multi-day figures are conventionally computed "
        "as the arithmetic mean of daily values rather than as period revenue over period unique users.",
    ),
    (
        "arppu",
        "ARPPU",
        "ARPPU is total in-app purchase revenue over a stated interval divided by the count of distinct "
        "paying users in that same interval. Because the denominator is restricted to payers, it measures "
        "spend depth within the monetizing population and is invariant to changes in conversion; the "
        "identity that ARPU equals ARPPU multiplied by the payer conversion rate makes this decomposition "
        "explicit.",
    ),
    (
        "arpu",
        "ARPU",
        "ARPU is total revenue over a stated reporting period divided by the count of unique active users in "
        "that period, irrespective of whether a given user transacted. It differs from ARPPU in that "
        "non-payers remain in the denominator, so ARPU responds jointly to spend depth and payer conversion, "
        "whereas ARPPU responds to the former alone.",
    ),
    (
        "avg_fps",
        "Avg FPS",
        "Avg FPS is the mean rendered-frames-per-second observed across gameplay sessions over a stated "
        "interval, computed as total rendered frames divided by total elapsed rendering time. Because "
        "arithmetic means conceal the tail behaviour that players perceive as stutter, the measure should be "
        "reported with percentile companions such as the fifth percentile or the proportion of rendering "
        "time spent below target frame rate.",
    ),
    (
        "avg_session_length",
        "Avg Session Length",
        "Avg Session Length is aggregate playtime over a stated interval divided by the number of sessions in "
        "that interval, yielding mean session duration. Its value depends materially on the "
        "session-termination convention adopted, typically a fixed inactivity timeout, so comparison across "
        "titles or instrumentation versions is invalid unless that timeout is identical.",
    ),
    (
        "avg_transaction_value",
        "Avg Transaction Value",
        "Avg Transaction Value is in-app purchase revenue over a stated interval divided by the number of "
        "completed transactions in that interval, representing mean basket size per purchase event. It is "
        "distinct from ARPPU, which divides by paying users rather than by transactions; the quotient of "
        "ARPPU and Avg Transaction Value recovers transactions per paying user.",
    ),
    (
        "conversion",
        "Conversion",
        "Conversion is the general-form proportion of users who complete a designated target action, divided "
        "by the count of users who entered the qualifying state for that action within a stated observation "
        "window. As an abstract construct it is uninterpretable without explicit declaration of numerator "
        "event, denominator population, and attribution window. It subsumes, but is not synonymous with, "
        "the payer-specific IAP Conversion.",
    ),
    (
        "crash_rate",
        "Crash Rate",
        "Crash Rate is the incidence of involuntary application process terminations normalized against a "
        "stated exposure base, conventionally sessions or user-days, over a specified interval. It is the "
        "primary stability indicator in client telemetry and is reported separately from ANR Rate because "
        "the two describe mutually exclusive failure modes. Interpretation requires the exposure base to be "
        "declared, since per-session and per-user-day rates differ by the sessions-per-user factor.",
    ),
    (
        "d1_retention",
        "D1 Retention",
        "D1 Retention is the proportion of an install cohort that initiates at least one session on the "
        "calendar day immediately following the day of installation, with day boundaries evaluated in a "
        "declared reference timezone. The denominator is fixed at cohort size on the acquisition day, which "
        "renders the measure a survival probability rather than a period-over-period ratio and makes cohorts "
        "comparable only under identical timezone and install-attribution conventions.",
    ),
    (
        "d3_retention",
        "D3 Retention",
        "D3 Retention is the proportion of an install cohort observed to be active on the third day following "
        "installation, measured against the same fixed acquisition-day denominator used throughout the "
        "day-N family. Because it is a point-in-time return probability rather than a cumulative one, it is "
        "not bounded below by D7 Retention through any arithmetic necessity, although monotonic decay is the "
        "empirical norm.",
    ),
    (
        "d7_retention",
        "D7 Retention",
        "D7 Retention is the proportion of an install cohort active on the seventh day after installation, "
        "and it functions as the conventional early indicator of habit formation in free-to-play titles. It "
        "shares the fixed cohort denominator of the day-N family, so its difference from D1 Retention "
        "isolates attrition occurring between the second and seventh days.",
    ),
    (
        "d14_retention",
        "D14 Retention",
        "D14 Retention is the proportion of an install cohort active on the fourteenth day after "
        "installation, situated between the early-habit and long-horizon segments of the retention curve. "
        "Because absolute values at this horizon are typically an order of magnitude below D1 Retention, "
        "statistically reliable estimation requires substantially larger cohorts to attain equivalent "
        "confidence intervals.",
    ),
    (
        "d30_retention",
        "D30 Retention",
        "D30 Retention is the proportion of an install cohort active on the thirtieth day after installation, "
        "serving as the standard proxy for long-run engagement durability and the empirical anchor for "
        "lifetime value extrapolation. Its computation requires a fully matured thirty-day observation "
        "window, so cohorts acquired within the preceding thirty days are structurally incomplete and must "
        "be excluded rather than reported as low.",
    ),
    (
        "daily_active_users",
        "Daily Active Users",
        "Daily Active Users is the count of distinct users who initiate at least one qualifying session "
        "within a single calendar day, evaluated in a declared reference timezone. It is a deduplicated "
        "count and is therefore not additive across days, since summing daily values overstates audience by "
        "counting returning users repeatedly. It serves as the denominator of ARPDAU, Sessions per DAU, and "
        "Impressions per DAU.",
    ),
    (
        "daily_new_users",
        "Daily New Users",
        "Daily New Users is the count of distinct users observed for the first time on a given calendar day, "
        "constituting the acquisition cohort for that day. It is a proper subset of Daily Active Users and "
        "is distinguished from New Installs in that it counts first-observed users rather than installation "
        "events, so device reinstallation and multi-device usage cause the two series to diverge.",
    ),
    (
        "feature_adoption_rate",
        "Feature Adoption Rate",
        "Feature Adoption Rate is the proportion of eligible active users who engage with a specified feature "
        "at least once within a stated observation window, divided by the count of users for whom that "
        "feature was available and unlocked. Restricting the denominator to eligible users is essential, "
        "since gating by progression level, platform, or experiment arm otherwise depresses the measure for "
        "reasons unrelated to the appeal of the feature.",
    ),
    (
        "ftue_drop_off",
        "FTUE Drop-off",
        "FTUE Drop-off is the proportion of users entering the first-time user experience who exit before "
        "reaching a designated terminal step, computed step-wise as one minus the step-to-step continuation "
        "rate. It is the exact complement of Tutorial Completion Rate only when both are defined over an "
        "identical step set and window; because the FTUE typically spans onboarding beyond the tutorial "
        "proper, the two measures are related but not arithmetically reciprocal.",
    ),
    (
        "iap_arpdau",
        "IAP ARPDAU",
        "IAP ARPDAU is in-app purchase revenue recognized on a given day divided by that day's count of "
        "daily active users, isolating the transactional component of daily monetization. Together with Ad "
        "ARPDAU it partitions ARPDAU additively, provided both terms are computed on the identical daily "
        "active denominator and revenue recognition basis.",
    ),
    (
        "iap_arpu",
        "IAP ARPU",
        "IAP ARPU is in-app purchase revenue over a stated reporting period divided by the count of unique "
        "active users in that period. It differs from IAP ARPDAU in the treatment of the denominator, "
        "deduplicating users across the full window rather than normalizing per day, and the two "
        "consequently diverge systematically as the window lengthens.",
    ),
    (
        "iap_conversion",
        "IAP Conversion",
        "IAP Conversion is the proportion of active users in a stated interval who complete at least one "
        "in-app purchase during that interval, divided by the count of active users in the same interval. "
        "It constitutes the payer-penetration term in the decomposition of ARPU into conversion multiplied "
        "by ARPPU, and is distinct from Purchase Funnel Conversion, which measures progression between "
        "individual steps of the checkout flow.",
    ),
    (
        "iap_revenue_usd",
        "IAP Revenue (USD)",
        "IAP Revenue (USD) is the monetary value of completed in-app purchases over a stated interval, "
        "denominated in United States dollars. Reported figures must declare whether they are gross of "
        "platform commission and refunds or net of them, since the two bases differ by approximately thirty "
        "percent on major storefronts and are frequently conflated in practice.",
    ),
    (
        "impressions_per_ad_user",
        "Impressions per Ad User",
        "Impressions per Ad User is total ad impressions served over a stated interval divided by the count "
        "of distinct users who received at least one impression in that interval. By excluding non-exposed "
        "users from the denominator it measures ad load within the exposed population only, and it "
        "consequently exceeds Impressions per DAU by exactly the reciprocal of advertising reach.",
    ),
    (
        "impressions_per_dau",
        "Impressions per DAU",
        "Impressions per DAU is total ad impressions divided by daily active users over the same interval, "
        "expressing advertising exposure intensity across the entire active base. It is the product of "
        "advertising reach and Impressions per Ad User, and together with Ad eCPM it multiplicatively "
        "reconstructs Ad ARPDAU.",
    ),
    (
        "live_event_participation_rate",
        "Live Event Participation Rate",
        "Live Event Participation Rate is the proportion of eligible users who perform at least one "
        "qualifying action within a time-bounded live event, divided by the count of users active during the "
        "event window who satisfied its entry conditions. Because event windows rarely align with calendar "
        "boundaries, both numerator and denominator must be evaluated over the event interval itself rather "
        "than over the enclosing reporting period.",
    ),
    (
        "monthly_active_users",
        "Monthly Active Users",
        "Monthly Active Users is the count of distinct users who initiate at least one qualifying session "
        "within a defined thirty-day or calendar-month window, deduplicated across the entire window. It is "
        "neither the sum nor the mean of the constituent daily active counts. It stands as the denominator "
        "of Stickiness and of period-level ARPU.",
    ),
    (
        "new_installs",
        "New Installs",
        "New Installs is the count of first-time application installation events attributed to a stated "
        "interval, as reported by the storefront or attribution provider. It is conceptually distinct from "
        "Daily New Users because installation does not entail application launch, and the gap between the "
        "two series quantifies install-to-launch loss.",
    ),
    (
        "new_payers",
        "New Payers",
        "New Payers is the count of distinct users who complete their first-ever in-app purchase within a "
        "stated interval, irrespective of install date. It is a proper subset of Paying Users for that "
        "interval, whose complement comprises repeat payers; separating the two is necessary because first "
        "purchase and repeat purchase respond to materially different design levers.",
    ),
    (
        "paying_users",
        "Paying Users",
        "Paying Users is the count of distinct users who complete at least one in-app purchase within a "
        "stated interval. It is deduplicated within the interval and therefore not additive across "
        "intervals, and it serves as the denominator of both ARPPU and Transactions per Paying User.",
    ),
    (
        "purchase_funnel_conversion",
        "Purchase Funnel Conversion",
        "Purchase Funnel Conversion is the proportion of users advancing from one declared step of the "
        "purchase flow to the next, such as store view to item selection to checkout initiation to completed "
        "transaction, each ratio taken against the population entering the prior step. It differs from IAP "
        "Conversion in granularity and denominator, being step-conditional where IAP Conversion is a single "
        "unconditional ratio against the active base. Reporting the full step sequence is required, since a "
        "single aggregate figure obscures which step constrains throughput.",
    ),
    (
        "sessions_per_dau",
        "Sessions per DAU",
        "Sessions per DAU is total sessions initiated over a stated interval divided by the count of daily "
        "active users in that interval, expressing mean daily play frequency. Its magnitude is directly "
        "governed by the inactivity timeout that delimits sessions, so it moves inversely with Avg Session "
        "Length whenever that convention changes and must be interpreted jointly with it.",
    ),
    (
        "stickiness_dau_mau",
        "Stickiness (DAU/MAU)",
        "Stickiness is the ratio of daily active users to monthly active users, conventionally computed as "
        "mean DAU over the period divided by MAU for the same period, and bounded between the reciprocal of "
        "the window length and unity. It estimates the expected fraction of the monthly audience present on "
        "any given day and is thus interpretable as mean days played per user per month, scaled by window "
        "length.",
    ),
    (
        "total_playtime",
        "Total Playtime",
        "Total Playtime is the aggregate duration of active sessions across all users over a stated interval, "
        "conventionally expressed in hours. As an unnormalized volume measure it confounds audience size "
        "with per-user engagement, and its decomposition into Daily Active Users, Sessions per DAU, and Avg "
        "Session Length is required for diagnostic interpretation.",
    ),
    (
        "total_revenue",
        "Total Revenue",
        "Total Revenue is the aggregate monetary value recognized from all monetization streams over a stated "
        "interval, encompassing in-app purchase and advertising revenue together with any subscription, "
        "storefront, or platform-specific streams present in the title. It is the broadest revenue "
        "construct in the catalogue and is deliberately open-ended with respect to stream composition, which "
        "must therefore be declared alongside any reported figure.",
    ),
    (
        "total_revenue_iap_ad",
        "Total Revenue (IAP+Ad)",
        "Total Revenue (IAP+Ad) is the explicit arithmetic sum of in-app purchase revenue and advertising "
        "revenue over a stated interval, restricted to those two streams by construction. It coincides with "
        "Total Revenue only in titles monetizing exclusively through those channels; where additional "
        "streams exist the two measures differ, and the restricted form is preferred for cross-title "
        "benchmarking because its composition is unambiguous.",
    ),
    (
        "total_sessions",
        "Total Sessions",
        "Total Sessions is the count of session instances initiated across all users over a stated interval, "
        "where a session is delimited by application foregrounding and a subsequent inactivity timeout. "
        "Unlike active user counts it is an event volume rather than a deduplicated population, and it is "
        "therefore additive across intervals.",
    ),
    (
        "tournament_completion_rate",
        "Tournament Completion Rate",
        "Tournament Completion Rate is the proportion of tournament entrants who satisfy the terminal "
        "condition of the tournament format, such as playing all scheduled rounds, divided by the count of "
        "users who entered. Its denominator is entrants rather than eligible users, which distinguishes it "
        "from Tournament Participation Rate and renders the two multiplicatively composable into completions "
        "per eligible user.",
    ),
    (
        "tournament_participation_rate",
        "Tournament Participation Rate",
        "Tournament Participation Rate is the proportion of eligible users who enter at least one tournament "
        "within a stated interval, divided by the count of users meeting the entry criteria of that "
        "tournament during the same interval. It measures the appeal and accessibility of the competitive "
        "mode, whereas Tournament Completion Rate measures follow-through conditional on entry; the two must "
        "not be conflated because their denominators differ.",
    ),
    (
        "transactions",
        "Transactions",
        "Transactions is the count of successfully completed in-app purchase events over a stated interval, "
        "excluding failed, cancelled, and refunded orders unless a net basis is explicitly declared. It is "
        "an event volume rather than a user count, and is therefore additive across intervals and greater "
        "than or equal to the corresponding count of paying users.",
    ),
    (
        "transactions_per_paying_user",
        "Transactions / Paying User",
        "Transactions per Paying User is the count of completed transactions over a stated interval divided "
        "by the count of distinct paying users in that interval, measuring purchase frequency within the "
        "monetizing population. It is bounded below by unity by construction, and its product with Avg "
        "Transaction Value recovers ARPPU exactly.",
    ),
    (
        "tutorial_completion_rate",
        "Tutorial Completion Rate",
        "Tutorial Completion Rate is the proportion of users who reach the designated terminal step of the "
        "tutorial sequence, divided by the count of users who initiated that sequence. Because the "
        "denominator is tutorial starters rather than installs, it excludes pre-tutorial loss and is "
        "consequently narrower in scope than FTUE Drop-off, which spans the wider onboarding path.",
    ),
    (
        "weekly_active_users",
        "Weekly Active Users",
        "Weekly Active Users is the count of distinct users initiating at least one qualifying session within "
        "a defined seven-day window, deduplicated across that window. Its value depends on whether the "
        "window is a fixed calendar week or a rolling seven-day span, and the two conventions yield "
        "materially different series that must not be compared directly.",
    ),
]

# Turn each tuple into a dictionary
metrics = [
    {"metric_id": metric_id, "metric_name": metric_name, "definition": definition}
    for metric_id, metric_name, definition in METRICS
]

catalogue = {
    "total_metrics": len(metrics),
    "metrics": metrics,
}

# Write output
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(catalogue, f, indent=2, ensure_ascii=False)

print(f"Generated {OUTPUT_PATH} ({len(metrics)} metrics)")
