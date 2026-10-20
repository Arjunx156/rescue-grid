/** Labels and time formats. Times show in IST because the people reading them are in Chennai. */

export type Level = "critical" | "high" | "medium" | "low";

export const LEVELS: Level[] = ["critical", "high", "medium", "low"];

export const LEVEL_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const STATUS_LABEL: Record<string, string> = {
  new: "New",
  needs_review: "Needs review",
  queued: "Queued",
  assigned: "Assigned",
  en_route: "En route",
  on_scene: "On scene",
  rescued: "Rescued",
  unreachable: "Couldn't reach",
  duplicate: "Merged",
  false_alarm: "False alarm",
  closed: "Closed",
};

export const WATER_LABEL: Record<string, string> = {
  none: "No water",
  ankle: "Ankle-deep",
  knee: "Knee-deep",
  waist: "Waist-deep",
  chest: "Chest-deep",
  neck: "Neck-deep",
  first_floor: "Ground floor flooded",
  second_floor: "On 2nd floor",
  roof: "On the roof",
  unknown: "Water level unknown",
};

export const NEED_LABEL: Record<string, string> = {
  rescue: "Rescue",
  medical: "Medical",
  evacuation: "Evacuation",
  food: "Food",
  water: "Drinking water",
  boat: "Boat",
  power: "Power",
  information: "Information",
};

export const CHANNEL_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  web_form: "Web form",
  csv_import: "Spreadsheet",
  helpline: "Helpline",
  twitter: "X post",
  replay: "Replay",
};

export const ASSET_LABEL: Record<string, string> = {
  boat: "Boat",
  truck: "Truck",
  medical: "Medical team",
  foot: "Foot team",
  helicopter: "Helicopter",
};

export const TEAM_STATUS_LABEL: Record<string, string> = {
  off_duty: "Off duty",
  available: "Available",
  assigned: "Assigned",
  en_route: "En route",
  on_scene: "On scene",
  returning: "Returning",
};

export const REASON_LABEL: Record<string, string> = {
  location_unknown: "Location unknown",
  low_confidence_location: "Location uncertain",
  possible_duplicate: "Possible duplicate",
  manual_reading: "Needs manual reading",
  reported_rescued: "Reported rescued",
  reported_false: "Reported false",
  reported_after_rescue: "Reported again after rescue",
  possibly_rescued: "Maybe already rescued",
  team_could_not_reach: "A team couldn't reach it",
  instructions_in_message: "Message tries to instruct the system",
};

export const MEDICAL_LABEL: Record<string, string> = {
  dialysis: "Dialysis",
  oxygen: "Oxygen",
  labour: "In labour",
  cardiac: "Cardiac",
  unconscious: "Unconscious",
  injury: "Injured",
  diabetes: "Insulin",
  cancer: "Cancer care",
  fever: "Fever",
  post_surgery: "Post-surgery",
  medication: "Medicines",
  restricted: "Restricted",
};

const IST_OFFSET_MIN = 330;

export function toDate(v: string | Date | null | undefined): Date | null {
  if (!v) return null;
  const d = typeof v === "string" ? new Date(v) : v;
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 14:32, in IST. */
export function clock(v: string | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return "--:--";
  const ist = new Date(d.getTime() + IST_OFFSET_MIN * 60_000);
  return `${String(ist.getUTCHours()).padStart(2, "0")}:${String(ist.getUTCMinutes()).padStart(2, "0")}`;
}

/** 2 Dec, 14:32 IST */
export function stamp(v: string | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return "";
  const ist = new Date(d.getTime() + IST_OFFSET_MIN * 60_000);
  const month = ist.toLocaleString("en-IN", {
    month: "short",
    timeZone: "UTC",
  });
  return `${ist.getUTCDate()} ${month}, ${clock(d)}`;
}

/** "12m", "2h 05m", "3d" since `v`, measured against `now` (the disaster's clock). */
export function ago(v: string | Date | null | undefined, now: number): string {
  const d = toDate(v);
  if (!d) return "";
  const mins = Math.max(0, Math.floor((now - d.getTime()) / 60_000));
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  if (h < 48) return `${h}h ${String(mins % 60).padStart(2, "0")}m`;
  return `${Math.floor(h / 24)}d`;
}

export function minutes(seconds: number | null | undefined): string {
  if (seconds == null) return "";
  const m = Math.max(1, Math.round(seconds / 60));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function km(meters: number | null | undefined): string {
  if (meters == null) return "";
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function levelColor(level: string): string {
  return `var(--${["critical", "high", "medium", "low"].includes(level) ? level : "closed"})`;
}
