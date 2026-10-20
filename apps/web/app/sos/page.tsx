import type { Metadata } from "next";
import { SosForm } from "./sos-form";

export const metadata: Metadata = {
  title: "Report an emergency",
  description: "Send a flood SOS to the rescue teams. Works in English, Tamil, Hindi, Malayalam and Telugu.",
  alternates: { canonical: "/sos" },
};

export default function SosPage() {
  return <SosForm />;
}
