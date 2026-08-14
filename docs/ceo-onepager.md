# One Front Door for Every Patient — Without Giving Away the Client List

*A non-technical summary of the technical exercise submission.*

## The two problems

**Patients can't find their portal.** Every clinic we serve has its own web
address (`riverside-clinic.brydonhealth.com`). Patients don't know it and
shouldn't have to — they just want "the portal." Today there is no single
address we can print in a reminder text, an email campaign, or on a fridge
magnet.

**Our website can't offer a Log In button.** To send a provider to the right
place we'd have to show a list of every customer we have — which hands our
client roster to every competitor with a web browser, and sits badly with our
healthcare confidentiality obligations.

## What I built

A working demonstration — five simulated clinics, each with genuinely
separate, walled-off data, exactly like production — plus **one front door**
that solves both problems with the same idea:

- **A patient** goes to one address, `portal.brydonhealth.com`, and types
  their email. Whatever they type, the screen says the same thing: *"If we
  have an account matching that address, a link is on its way."* The actual
  answer — which clinic they belong to — arrives **in their own inbox** as a
  one-click link to their clinic's sign-in page.
- **A provider** clicks one Log In button on our marketing site, types their
  work email, and lands directly on their clinic's staff sign-in page.
- **Appointment reminders** get even simpler: since the clinic sending the
  reminder already knows who you are, the email contains a link that goes
  straight to the right place. One click, no questions asked.

## Why it's safe — the three rules

1. **The screen never confirms anything.** Type your own email or a
   stranger's — the response is identical. The only place the system ever
   names a clinic is inside an inbox that person already controls. Nobody
   can use the front door to fish for whose children attend which practice,
   and nobody can reconstruct our client list from it.
2. **Passwords never touch the shared system.** The front door is a routing
   desk, not a security checkpoint. Signing in always happens on the
   clinic's own site, exactly as today. If the front door were ever
   compromised, the attacker would hold a list of scrambled codes — no
   names, no health information, no passwords, and no way to unscramble the
   codes without a key kept elsewhere.
3. **Each clinic's data stays in its own locked room.** Nothing about
   today's separation changes: separate databases, separate credentials,
   separate networks. The submission includes an automated test that proves
   one clinic's systems cannot even *locate* another clinic's database, let
   alone open it.

## What this unlocks

- Marketing can print **one URL** everywhere — campaigns, reminders,
  clinic waiting rooms — instead of maintaining per-clinic links.
- The client list stays confidential, by architecture rather than by policy.
- A bonus tool keeps all clinic deployments provably in sync — the first
  concrete step toward consolidating our per-customer infrastructure costs,
  with a written phase-by-phase plan (and, importantly, a tested way to back
  out of each phase) included in the submission.

*Everything above is running code, not slides: five clinics, the portal, the
marketing button, and the reminder emails can all be demonstrated live in
about five minutes.*
