---
description: Max's travel preferences and booking guidelines for flights, hotels, and trip planning
---

# Travel Preferences

## Sleep is the #1 priority

- **NEVER book redeye flights.** Overnight flights where you'd be sleeping on the plane are redeyes, including transatlantic eastbound flights that depart evening and arrive morning.
- For transatlantic eastbound (US → Europe): fly during the day with a stopover to sleep at the destination. E.g., DC → London (daytime), sleep in London, then short hop to final destination the next morning.
- For transatlantic westbound (Europe → US): daytime departures are fine — you gain time zones and arrive same day afternoon/evening.
- Domestic: prefer daytime flights. No departures after 8 PM or arrivals before 7 AM.

## Booking preferences

- **Home airport**: Washington, D.C. area (DCA, IAD, BWI)
- **Class**: Economy unless otherwise specified
- **Stops**: Prefer nonstop or 1-stop. Avoid 2+ stops unless significant savings.
- **Airlines**: No strong preference, but value convenience and schedule over loyalty programs.
- **Internet and power** (Max 2026-10-21: "consider internet and power for the flights"): when comparing flights, report Wi-Fi and seat power for each leg, especially the long one. Read them from Google Flights' expanded flight details ("Wi-Fi for a fee" / "Free Wi-Fi", "In-seat power & USB outlets" vs "In-seat USB outlet" only), then confirm with the airline where possible, because Google's listings can be missing or out of date. USB-only seats may not charge a laptop.
- **Good wifi is a top priority on flights** (Max 2026-10-20: "note i prioritize wifi... good wifi"). Rank flight options by expected wifi quality, then price. As of Oct 2026, United Starlink is the fast option: 100–250 Mbps versus 10–20 Mbps on legacy Viasat/Gogo systems, and free for MileagePlus members (travelerstoday.com, 2026-10-16). Starlink coverage depends on the aircraft type. On 2026-10-15 it covered 87% of United A321neos, 56% of United 737s (NG) and 11% of United 737 MAXes, plus all CRJ-550s and E175s. Per-flight confirmation is at StarlinkTracker.United.com, and it only shows flights within 3 days of departure, so book a changeable fare and re-check then. Google Flights labels American, Delta and JetBlue as "Free Wi-Fi" and United as "Wi-Fi for a fee"; those labels say nothing about speed.

## Hotels (confirmed by Max 2026-07-11)

Sleep quality is the primary filter, same as flights:

1. **Bed quality, full blackout, quiet** — these three decide the hotel. Request high floor, away from elevator, rear-facing when booking.
2. **Air conditioning — required** (added 2026-08-14, Brussels trip). Confirm in-room AC before booking, especially in Europe where it's not standard; check recent reviews that it actually works, not just that it's listed. Max sleeps temperature-controlled at home (Eight Sleep), so a hot room defeats the whole sleep-first filter.
3. **Good fitness center** — secondary, and matters less in gym-dense cities (NYC etc.) where day passes are everywhere.
- **Bed size doesn't matter solo.** Twin, single, full are all fine (Max 2026-09-27: "i dont mind a twin"; 2026-07-11: full is fine). Never pay for width. Bed *quality*, quiet, blackout and AC still decide, and twin-only rooms widen the cheap end a lot.
- **Price-sensitive right now** (Sep 2026: no salary until grant funding lands; he balked at a ~$1,110 three-night NYC plan with "yiiikes"). Lead with the cheapest shape that keeps the trip's purpose. Hotel nights are usually the biggest line item.
- **Location means transit math.** Before recommending a hotel, list every leg of the actual itinerary (arrival station, work base, dates, departure point), get weekday door-to-door times from Google Maps for each candidate, sum them per hotel, and state the dollars-versus-minutes trade. Example 2026-09-27: LIC Plaza $187/nt vs NU Hotel $307/nt meant +$240 to save ~85 minutes over two days.
- Past citizenM/Motel One stays were about price + blackout, NOT a bed endorsement — Max finds citizenM's firm foam beds mediocre. Vet bed quality through recent guest reviews every time: look for "pillowtop", "plush", "down comforter" mentions; firm foam-platform beds (citizenM, Moxy, pod-style) don't clear the bar.
- Brand loyalty irrelevant; Max books through deal channels (Super.com, booking.com, Agoda, Dayuse.com for layover day rooms).
- **Always price hotels via Google Hotels/Maps OTA comparison, never a single OTA** (added 2026-08-17: quoted booking.com only; Agoda had the same Brussels room ~$250 / 22% cheaper). booking.com is a convenient scriptable baseline — treat it as the ceiling, then check the Google Hotels price grid (Agoda and Trip.com often undercut it in Europe/Asia). When quoting a cheaper OTA rate, note its cancellation tier — the discounts are often non-refundable or pay-now.
  - **Missed again 2026-09-27** (NYC, booking.com only until Max asked "did you look at google hotels?"). For the same LIC Plaza room Google showed Super.com $187/nt vs booking.com $231; booking.com was the most expensive channel. Super.com was the cheapest channel for every NYC hotel checked that day. Open each shortlisted hotel's "View prices" list, not just the search grid.
  - Google Hotels dates can be set in the URL `ts` parameter (protobuf, base64url). Sep 30–Oct 2 2026, 2 nights: hex `0801120a0a0208030a02080310001a1c121a12140a0708ea0f1009181e120708ea0f100a18021802320208012a090a053a035553441a00`; the two 7-byte blocks are year/month/day for check-in and check-out and `1802` is the night count. The date picker also works but needs a visible pane.
  - Google Maps weekday transit times: `https://www.google.com/maps/dir/<A>/<B>/data=!4m6!4m5!2m3!6e0!7e2!8j<epoch of local time treated as UTC>!3e3`. The header lists driving, transit, walking and cycling minutes in that order.
- **Google's default "Nightly price with fees" EXCLUDES tax** (verified 2026-09-29: DoubleTree LIC $242 → $281 "with taxes + fees"; New Yorker $250 → $291). Always quote the all-in number. Each OTA row carries a hidden "$X with taxes + fees" element; scrape it with JS (leaf text matching `^\$[\d,]+ with taxes \+ fees$`, then climb to the row containing "Visit site") or switch the "Price displayed" dropdown to "Nightly price with taxes + fees". Super.com's lower base price often ends up at the same all-in total as official/Agoda (DoubleTree LIC: $299 base vs $305, both $354 all-in).
- **NYC specifics:** booking.com US prices also exclude NYC's 14.75% tax + $4/night. Friday nights run far above midweek (2 Oct 2026: Pointe Plaza sold out everywhere; the cheapest acceptable Penn-area room was Hotel Stanford at $313 all-in on Super.com). Late Sep 2026 midweek: Downtown Brooklyn and Williamsburg ran $450–500/nt, while Long Island City and the Williamsburg/Bed-Stuy edge (Pointe Plaza, 2 Franklin Ave) ran ~$185/nt with breakfast. Event and weekend nights (UNGA, CultureCon, Comic Con) spike prices, and a multi-night weekday package can cost less than one weekend night.

## Trains (Amtrak, DC–NYC)

- **Acela NextGen only** (Max 2026-09-28: "i only take acela nextgen now - wifi makes it worth it"). Default to NextGen Acela business; don't offer Northeast Regional or legacy Acela unless no NextGen train fits. The fleet is mixed until ~2027 (13 NextGen trainsets, 32 weekday trips as of July 2026), so check each train. On amtrak.com search results NextGen trains carry a "NextGen" tag (an element with alt/aria-label "NextGen Acela"; the visible "Premium" label is on every Acela and is not the tell). Examples 2026-09-28: Wed 9/30 WAS→NYP NextGen = 2102, 2104, 2108, 2156, 2158, 2116, 2160, 2118, 2162 (legacy: 2150, 2152, 2154, 2112); Sat 10/3 NYP→WAS NextGen = 2203, 2207, 2211, 2255, 2259, 2219, 2263, 2265 (legacy: 2267, 2271).
- **Connectivity on anything but NextGen is unusable, phone hotspot included** (Max 2026-10-19: "basically unusable on non-nextgen... incl hotspot"). The preference is about connectivity, not comfort or speed. Never offer a Regional or legacy Acela as the "cheap alternative" when Max has calls or work on board; mention it only for trips with no work at all, and say so.
- Because of the WiFi, NextGen beats flying DC–NYC even when the flight is cheaper (Sep 2026: $270 Acela business vs $198 DCA–LGA): the train is door-to-door comparable and gives ~3 h of real work time.
- Fares climb fast. On 9/22→9/27/2026 the Wed 10:35 WAS→NYP Regional went $58→$116 and the 10:55 Acela $173→$270. Book as soon as dates are firm.
- When the return might move (a date could extend the trip), buy a Flex fare: fully refundable, no cancellation fee before departure (Amtrak homepage).
- **Fare rules (amtrak.com/refund-and-cancellation-policy, read 2026-09-28):** Flex = full refund to original payment if cancelled before departure, changes free (fare difference applies). Value = 30% forfeited on cancellation (70% back to card), no changes. Sale = 50% forfeited, no changes. Any fare: full refund if cancelled within 24 h of purchase and before departure. No-shows forfeit everything.
- **Flex premium is small:** 2026-09-28, Wed 10:35 Regional coach Value $116 / Flex $126 (+$10); Acela 2156 business Value $270 / Flex $294 (+$24).
- **Max's "Flex and watch" play** (buy Flex, cancel and rebook the same train if a cheaper fare appears near departure): pays off only if P(cheaper fare) > premium ÷ (Flex − lower fare), about 15–23% for a +$10 premium against the $58–82 buckets. It also covers plan changes (Value loses 30%). Fares mostly rose in the week before departure: across ~20 DC–NY trains tracked 9/22→9/28/2026, none fell (e.g., Sat Acela $139→$270, most Sat Regionals $116→$155).
- **Train vs flying DC–NYC:** the train wins unless the trip is time-critical. 950 3rd St NW is a 14-minute walk from Union Station vs 12 min drive / 27 min transit to DCA. LGA→Fort Greene is 40 min by car / 67 min transit. Flights were $198 each way late Sep 2026 vs $116 Regional, and the train gives ~3.5 h of seated work time and calls.
- The last real NYP→WAS train on weekdays is the ~8pm Acela (2131). Later options are the 11:23pm overnight or a 3am arrival, which the no-redeye rule excludes.

## Trip planning

- Build in buffer days for jet lag when crossing 5+ time zones
- London is a good stopover city for European trips (familiar, English-speaking, good connections)
