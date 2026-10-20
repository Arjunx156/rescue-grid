import type { Metadata } from "next";
import Link from "next/link";
import { Contact, ProsePage } from "@/components/prose-page";

export const metadata: Metadata = {
  title: "Privacy",
  description: "What Rescue Grid collects when you ask for help, who sees it, and when it is deleted.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <ProsePage title="Privacy" updated="20 October 2026">
      <p>
        When you ask for help, we use what you tell us to get a rescue team to you. We collect only what that needs,
        show it only to the people doing the work, and delete the personal parts after the emergency is over.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>Your message, including anything you say about the people with you, their health and the water level.</li>
        <li>The phone number you write from or give us, and your name if you share it.</li>
        <li>Your location, if you share your phone's location or describe where you are.</li>
        <li>The tracking code we give you, and the updates we send back.</li>
      </ul>

      <h2>Why</h2>
      <p>
        To find where you are, judge how urgent it is, send the nearest team that can reach you, let that team call you,
        and tell you and your family what is happening. We do not use it for anything else and we never sell it.
      </p>

      <h2>Who sees it</h2>
      <ul>
        <li>
          <strong>Coordinators</strong> at the responding agencies see your full request so they can plan the rescue.
        </li>
        <li>
          <strong>The team sent to you</strong> sees your address, your phone number and what you need.
        </li>
        <li>
          <strong>Observers</strong> with view-only access never see phone numbers or health details.
        </li>
        <li>
          <strong>Anyone with your tracking code</strong> sees only the status of your request and the team&apos;s call
          sign, never your number or message.
        </li>
      </ul>

      <h2>How it is protected</h2>
      <p>
        Phone numbers, names and message text are encrypted in our database. Staff sign in to see anything, and every
        change to a request is logged with who made it.
      </p>

      <h2>Services we rely on</h2>
      <ul>
        <li>If you write to us on WhatsApp, Meta carries those messages under its own privacy policy.</li>
        <li>Maps load from OpenFreeMap, using data from OpenStreetMap. They see a map request, not your request.</li>
        <li>
          Messages are read on our own servers. If the agency running this service turns on a hosted AI model to help
          read them, the message text goes to that provider with phone numbers removed.
        </li>
        <li>Error reports, if enabled, are sent without personal details.</li>
      </ul>

      <h2>How long we keep it</h2>
      <p>
        Ninety days after an emergency is declared over, your phone number, name and message are deleted. We keep an
        anonymous record of what happened, such as how many people were reached and how long it took, to make the next
        response better.
      </p>

      <h2>Your choices</h2>
      <p>
        You can ask us to correct or delete your information at any time. Quote your tracking code and <Contact />. This
        notice follows India&apos;s Digital Personal Data Protection Act, 2023.
      </p>

      <p>
        See also the <Link href="/terms">terms of use</Link>.
      </p>
    </ProsePage>
  );
}
