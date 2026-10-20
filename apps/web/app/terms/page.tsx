import type { Metadata } from "next";
import Link from "next/link";
import { Contact, ProsePage } from "@/components/prose-page";

export const metadata: Metadata = {
  title: "Terms of use",
  description: "What Rescue Grid can and cannot promise, and how to use it responsibly.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <ProsePage title="Terms of use" updated="20 October 2026">
      <p>
        Rescue Grid helps rescue agencies find and reach people during floods. Using it means agreeing to the following.
      </p>

      <h2>Call 112 as well</h2>
      <p>
        This service adds to the national emergency number; it does not replace it. If you can reach 112, call it. A
        request sent here is not a promise that a team will arrive by a certain time. Teams go where they can safely
        reach, most urgent first.
      </p>

      <h2>Tell the truth</h2>
      <p>
        Send real requests only, and only for people who need help. A false alarm takes a boat away from someone in
        danger, and making one is an offence under section 54 of the Disaster Management Act, 2005. If someone you
        reported is now safe, tell us so the team can go elsewhere.
      </p>

      <h2>For responders</h2>
      <p>
        The command centre and field app are for people authorised by a responding agency. Use what you see only for the
        rescue, keep your sign-in to yourself, and do not copy personal details out of the system.
      </p>

      <h2>The service</h2>
      <p>
        We work to keep Rescue Grid running and accurate, but networks fail during disasters and automated reading of
        messages can be wrong. Coordinators check uncertain locations and possible duplicates by hand, and they make the
        final call on every dispatch.
      </p>

      <h2>Questions</h2>
      <p>
        To ask about these terms, <Contact />. How we handle your information is described in the{" "}
        <Link href="/privacy">privacy notice</Link>.
      </p>
    </ProsePage>
  );
}
