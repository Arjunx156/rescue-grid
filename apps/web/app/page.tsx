import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { LandingReplay } from "@/components/landing/landing-replay";
import { Story } from "@/components/landing/story";
import { Logo } from "@/components/logo";
import { CONTACT_EMAIL } from "@/components/prose-page";
import { ButtonLink } from "@/components/ui/button";
import evals from "@/public/evals/latest.json";
import replay from "@/public/replay/chennai-2015.json";

export const metadata: Metadata = {
  title: {
    absolute: "Rescue Grid: a water clock for every family in a flood",
  },
  description:
    "Rescue Grid reads flood SOS messages in five languages, uses each one as a water gauge, forecasts when the water will reach every family's roof, and plans the boats around it.",
  alternates: { canonical: "/" },
};

const rg = replay.policies.rescue_grid.metrics;
const fc = replay.policies.fcfs.metrics;
const pct = (v: number) => `${Math.round(v * 100)}%`;
const pct1 = (v: number) => `${Math.round(v * 1000) / 10}%`;

function Beat({ when, title, children }: { when?: string; title: string; children: ReactNode }) {
  return (
    <>
      {when ? <p className="font-mono text-[13px] text-water tnum">{when}</p> : null}
      <h2 className="mt-3 text-[32px] leading-[1.08] font-semibold tracking-[-0.02em] text-balance sm:text-[44px]">
        {title}
      </h2>
      <div className="mt-5 space-y-4 text-[17px] leading-relaxed text-muted">{children}</div>
    </>
  );
}

function Stat({ value, label, versus }: { value: string; label: string; versus?: string }) {
  return (
    <div className="border-t border-line pt-4">
      <dd className="text-[40px] leading-none font-semibold tracking-[-0.02em] tnum">
        {value}
        {versus ? <span className="ml-2 text-[17px] font-normal text-muted">vs {versus}</span> : null}
      </dd>
      <dt className="mt-2 text-[14px] text-muted">{label}</dt>
    </div>
  );
}

const STEPS = [
  {
    title: "Hear every channel",
    body: "WhatsApp, the public SOS form, helpline calls and volunteer spreadsheets land in one queue. Every reporter gets a tracking code in their own language.",
  },
  {
    title: "Read five languages, offline",
    body: `English, Tamil, Hindi, Malayalam and Telugu, in script or typed in Latin letters. Headcount right ${pct(evals.headcount_accuracy)} of the time, vulnerable people at ${pct(evals.vulnerability_f1)} F1, with no model and nothing sent off the machine.`,
  },
  {
    title: "Pin it to a street",
    body: `"Behind the Pillaiyar kovil near Velachery bus depot" becomes a point with a confidence. ${pct(evals.geocode_within_300m)} of confident pins land within 300 m; the rest wait for a person.`,
  },
  {
    title: "Merge the family, never the neighbours",
    body: `Five relatives reporting one family become one case. Merges are right ${pct1(evals.dedup_precision)} of the time, because hiding a family is the worst mistake a merge can make.`,
  },
  {
    title: "Measure the water with the crowd",
    body: "Each reported depth corrects a flood model running on 30 m Copernicus terrain. Eight versions of the forecast disagree about the rain and the releases; the reports decide which to trust.",
  },
  {
    title: "Start every family's water clock",
    body: "Minutes until the water reaches the family's danger line, with an early and a late estimate, added to an urgency score where every point is explained.",
  },
  {
    title: "Plan the boats against the water",
    body: "OR-Tools assigns boats, trucks and medical teams with deadlines from the clocks, and sends a truck only where the road will still be passable when it arrives. A coordinator approves every move.",
  },
];

const PRINCIPLES = [
  ["People decide", "The system proposes; a coordinator approves every dispatch, and undo is one click."],
  [
    "Every decision explained",
    "Scores list their factors, plans list their reasons, merges list their evidence, clocks show their range.",
  ],
  [
    "A model can only add what it can quote",
    "If a language model reads a message, every person or condition it adds must come with the words that say so. Anything else is dropped before it can move a boat.",
  ],
  [
    "Private by default",
    "Messages are read on the server with no outside AI unless you choose one. Phones and medical details are encrypted, hidden from viewers, and purged 90 days after the event.",
  ],
  [
    "A log nobody can edit",
    "Every change is chained to the one before it with SHA-256 inside the database. An edit is refused; a deletion shows exactly where.",
  ],
  [
    "Free to run",
    "Open-source parts on one small server: PostgreSQL, Redis, OpenStreetMap, Copernicus terrain, OR-Tools.",
  ],
];

export default function Home() {
  return (
    <div className="theme-dark bg-bg text-text">
      <header className="fixed inset-x-0 top-3 z-30 px-4">
        <nav
          aria-label="Main"
          className="glass mx-auto flex h-14 max-w-5xl items-center gap-6 rounded-full border border-line px-5 shadow-float"
        >
          <Link href="/" className="inline-flex items-center gap-2 text-[15px] font-semibold">
            <Logo className="size-5 text-accent-text" />
            Rescue Grid
          </Link>
          <div className="hidden items-center gap-6 text-[14px] text-muted md:flex">
            <a href="#story" className="hover:text-text">
              The flood
            </a>
            <a href="#replay" className="hover:text-text">
              Two ways
            </a>
            <a href="#how" className="hover:text-text">
              How it works
            </a>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {/* the smallest phones keep room for the emergency action; sign-in lives further down too */}
            <ButtonLink href="/login" variant="ghost" size="sm" className="max-[399px]:hidden">
              Sign in
            </ButtonLink>
            <ButtonLink href="/sos" size="sm">
              Report an emergency
            </ButtonLink>
          </div>
        </nav>
      </header>

      <main>
        <Story
          beats={[
            <div key="hero" className="pt-16">
              <p className="text-[15px] text-muted">The Chennai flood of December 2015, replayed</p>
              <h1 className="mt-4 text-[48px] leading-[1.02] font-semibold tracking-[-0.03em] text-balance sm:text-[76px]">
                Every family gets a water clock.
              </h1>
              <p className="mt-6 max-w-lg text-[18px] leading-relaxed text-muted sm:text-[20px]">
                Rescue Grid reads flood SOS messages in five languages and treats each one as a water gauge. A flood
                model on real terrain listens to them, forecasts when the water will reach every family's roof, and the
                boats go in that order.
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <ButtonLink href="/sos" size="lg">
                  Report an emergency
                </ButtonLink>
                <ButtonLink href="#replay" size="lg" variant="outline">
                  See the result
                </ButtonLink>
              </div>
              <p className="mt-14 text-[13px] text-faint">Scroll to run the flood.</p>
            </div>,
            <Beat key="gates" when="1 December, 6 pm" title="The gates open.">
              <p>
                Chembarambakkam lake releases up to 850 cubic metres a second into the Adyar. The river leaves its banks
                at Mudichur, then Saidapet, then Kotturpuram, while 40 mm of rain an hour falls on everything else.
              </p>
              <p className="text-[15px] text-faint">
                This is Rescue Grid's own flood model on Copernicus terrain, driven by the published rainfall and
                releases. An illustration of how that night moved, not an official hindcast.
              </p>
            </Beat>,
            <Beat key="gauges" when="Late that night" title="Every message is a water gauge.">
              <p>
                "Waist-deep near the Murugan temple" is a depth, a place and a time. Rescue Grid pins it to a street and
                feeds it to the model, which corrects itself the way a weather service corrects its forecast with
                sensors.
              </p>
              <dl className="grid grid-cols-2 gap-6 pt-2">
                <Stat
                  value={pct(evals.water_detected)}
                  versus={pct(evals.water_detected_forecast_alone)}
                  label="of families' danger seen three hours ahead, with the reports vs without"
                />
                <Stat
                  value={`${Math.round(evals.water_depth_error_m * 100)} cm`}
                  versus={`${Math.round(evals.water_depth_error_forecast_alone_m * 100)} cm`}
                  label="typical error in the depth at a family's door"
                />
              </dl>
            </Beat>,
            <Beat key="clocks" when="2 December, 2 am" title="How long until the roof goes under?">
              <p>
                Each family gets a clock: minutes until the water crosses their danger line. A family on the first floor
                has hours. A grandmother who cannot climb has far less. The clock carries an early and a late estimate,
                ranks the queue, and the coordinator sees why.
              </p>
              <p className="text-[15px] text-faint">
                The rings tighten as the water closes in. Red means under an hour.
              </p>
            </Beat>,
            <Beat key="boats" when="2 December, evening" title="Boats go where the water will be.">
              <p>
                The optimiser plans against the forecast: a deadline from every clock, and trucks only where the road
                will still be passable when they get there. Same 28 teams, same night.
              </p>
              <dl className="grid grid-cols-2 gap-6 pt-2">
                <Stat
                  value={`${rg.reached_before_water}`}
                  versus={`${fc.reached_before_water}`}
                  label={`of ${rg.at_risk} families reached before the water, Rescue Grid vs first come, first served`}
                />
                <Stat
                  value={(rg.people_rescued ?? 0).toLocaleString("en-IN")}
                  versus={(fc.people_rescued ?? 0).toLocaleString("en-IN")}
                  label="people rescued in the 60 hours"
                />
              </dl>
            </Beat>,
          ]}
        />

        <section id="replay" className="scroll-mt-20 border-t border-line">
          <div className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
            <div className="max-w-3xl">
              <h2 className="text-[34px] leading-tight font-semibold tracking-[-0.02em] sm:text-[48px]">
                The same 60 hours, two ways.
              </h2>
              <p className="mt-5 text-[17px] leading-relaxed text-muted">
                {replay.houses.length} families stranded in the simulated flood, reported by relatives in five
                languages. The same 28 teams answer them. On the left, Rescue Grid. On the right, the usual way: each
                message in the order it arrived, with the nearest free team.
              </p>
            </div>
            <div className="mt-14">
              <LandingReplay />
            </div>
            <dl className="mt-20 grid gap-x-10 gap-y-10 border-t border-line pt-12 sm:grid-cols-3">
              <div>
                <dt className="text-[14px] text-muted">Families reached before the water reached their danger line</dt>
                <dd className="mt-2 text-[44px] leading-none font-semibold tnum">
                  {rg.reached_before_water}
                  <span className="text-[20px] text-muted"> vs {fc.reached_before_water}</span>
                </dd>
              </div>
              <div>
                <dt className="text-[14px] text-muted">Median wait for a team, critical cases</dt>
                <dd className="mt-2 text-[44px] leading-none font-semibold tnum">
                  {Math.round(rg.median_minutes_to_assign_critical ?? 0)} min
                  <span className="text-[20px] text-muted">
                    {" "}
                    vs {Math.round((fc.median_minutes_to_assign_critical ?? 0) / 60)} h
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-[14px] text-muted">Wasted trips: already rescued, wrong place, too deep</dt>
                <dd className="mt-2 text-[44px] leading-none font-semibold tnum">
                  {rg.wasted_trips}
                  <span className="text-[20px] text-muted"> vs {fc.wasted_trips}</span>
                </dd>
              </div>
            </dl>
            <p className="mt-10 max-w-3xl text-[13px] leading-relaxed text-faint">
              A simulation, not a claim about 2015. Messages are synthetic and contain no real person's details; the
              localities, landmarks and terrain are real. Both sides get the same teams, speeds, flood and ground truth,
              with a coordinator in the loop, and a truck that drives into water past its axles turns back on both. The
              benchmark is one command in the repository.
            </p>
          </div>
        </section>

        <section id="how" className="mx-auto max-w-5xl scroll-mt-20 px-6 py-24 sm:py-36">
          <h2 className="max-w-2xl text-[34px] leading-tight font-semibold tracking-[-0.02em] sm:text-[44px]">
            From a forwarded message to a boat at the door.
          </h2>
          <p className="mt-5 max-w-2xl text-[17px] leading-relaxed text-muted">
            Seven steps, each one measured on {evals.raw_messages.toLocaleString("en-IN")} labelled messages and the
            simulated flood.
          </p>
          <ol className="mt-16 grid gap-x-16 gap-y-12 md:grid-cols-2">
            {STEPS.map((s, i) => (
              <li key={s.title} className="grid grid-cols-[2.25rem_1fr] gap-x-3">
                <span className="font-mono text-[14px] text-faint tnum">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <h3 className="text-[19px] font-semibold">{s.title}</h3>
                  <p className="mt-2 text-[16px] leading-relaxed text-muted">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-y border-line bg-panel">
          <div className="mx-auto grid max-w-5xl gap-12 px-6 py-24 md:grid-cols-3">
            {[
              [
                "For the control room",
                "A live map with the water on it and a queue that never jumps under your cursor. The most urgent case is first and red. Drag a wrong pin, approve a plan in one click, scrub the forecast three hours ahead.",
              ],
              [
                "For the crew",
                "One job at a time, the route, the family's number, when the water reaches them, and four big buttons. It works with wet hands, in sunlight, and with no signal.",
              ],
              [
                "For the family",
                "Report once, in your own language, on WhatsApp or the web. Get a code, and a message when help is on the way and when your people are safe.",
              ],
            ].map(([title, body]) => (
              <div key={title}>
                <h3 className="text-[19px] font-semibold">{title}</h3>
                <p className="mt-3 text-[16px] leading-relaxed text-muted">{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="principles" className="mx-auto max-w-5xl scroll-mt-20 px-6 py-24 sm:py-36">
          <h2 className="max-w-2xl text-[34px] leading-tight font-semibold tracking-[-0.02em] sm:text-[44px]">
            Built for the room it runs in.
          </h2>
          <dl className="mt-14 grid gap-x-16 gap-y-10 sm:grid-cols-2">
            {PRINCIPLES.map(([title, body]) => (
              <div key={title} className="border-t border-line pt-5">
                <dt className="text-[17px] font-semibold">{title}</dt>
                <dd className="mt-2 text-[16px] leading-relaxed text-muted">{body}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mx-auto max-w-5xl px-6 pb-28">
          <div className="rounded-2xl border border-line bg-panel px-8 py-14 sm:px-14">
            <h2 className="max-w-2xl text-[30px] leading-tight font-semibold tracking-[-0.02em] sm:text-[40px]">
              Run a drill with your teams.
            </h2>
            <p className="mt-4 max-w-xl text-[17px] leading-relaxed text-muted">
              Explore the command centre, the crew app and a full replay with seeded demo accounts. Nothing you do there
              reaches a real person.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href="/login" size="lg">
                Open the live demo
              </ButtonLink>
              <ButtonLink href="/sos" size="lg" variant="outline">
                Report an emergency
              </ButtonLink>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-8 gap-y-3 px-6 py-10 text-[14px] text-muted">
          <span className="inline-flex items-center gap-2 font-medium text-text">
            <Logo className="size-4 text-accent-text" /> Rescue Grid
          </span>
          <span>Engineered by Arjun Krishnan</span>
          <a href="https://github.com/Arjunx156" className="hover:text-text">
            GitHub
          </a>
          {CONTACT_EMAIL ? (
            <a href={`mailto:${CONTACT_EMAIL}`} className="hover:text-text">
              {CONTACT_EMAIL}
            </a>
          ) : null}
          <Link href="/privacy" className="hover:text-text">
            Privacy
          </Link>
          <Link href="/terms" className="hover:text-text">
            Terms
          </Link>
          <span className="sm:ml-auto">
            Map data ©{" "}
            <a href="https://www.openstreetmap.org/copyright" className="underline-offset-2 hover:underline">
              OpenStreetMap
            </a>{" "}
            contributors · Terrain: Copernicus DEM GLO-30, © DLR and Airbus, provided under COPERNICUS by the EU and ESA
          </span>
        </div>
      </footer>
    </div>
  );
}
