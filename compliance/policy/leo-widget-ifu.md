# LEO widget - Instructions For Use (Embedding Hosts)

Version: v1.0.0
Status: published
Owner: LEO Clinical Safety Officer (CSO)
Audience: Mizaic-portfolio products embedding the LEO widget
Atlas trace: DI-2FBDAC7D, DO-5A298ABC

## 1. Purpose

The LEO widget is a UKCA Class I medical device that renders an
AI-generated SBAR for human review. The host product owns the
clinical workflow that surrounds that SBAR. This Instructions For
Use document tells you what the widget does, what it does not do,
and what your product MUST do for the widget to operate safely in
your environment.

## 2. Intended use and intended users

- The widget is a clinical decision support surface. Every AI
proposal MUST be accepted or rejected by a clinician before any
clinical action is taken.
- Intended users are clinical staff working a 2-week-wait or
equivalent secondary-care referral pathway. The widget is not
intended for direct patient use.

## 3. Scope of the widget (what LEO ships)

- Shadow-DOM web component and hardened iframe variant.
- Source-record disclosure rendered inside the LEO trust boundary.
- Locked LEO-by-Mizaic branding with reactive light/dark mode.
- Required (non-disable-able) telemetry on disclosure engagement.
- Auto-update within a pinned major version under LEO QMS, with
CSO-controlled rollback.
- Non-dismissible CSO clinical safety advisory channel.

## 4. Host obligations (mandatory)

A Mizaic-portfolio product embedding the LEO widget SHALL:

1. Maintain its own DCB0129 deployment safety case and DCB0160 clinical
  safety assessment covering the workflow in which the LEO widget appears.
  LEO's DCB0129 covers the widget itself; the host's DCB0129 covers the
  host workflow and the integration boundary.
2. Allowlist the LEO widget CDN origin and the LEO analytics
  endpoint in the host's Content Security Policy. The widget
   cannot operate behind a CSP that blocks either origin.
3. Preserve widget telemetry without proxy-stripping. If the host
  proxies network calls between the browser and LEO, it MUST
   forward every POST /sdk/telemetry payload unchanged.
4. Surface widget error states to the user without modification.
  When the widget renders a degraded-state indicator or a CSO
   advisory banner, the host SHALL NOT hide it, restyle it out of
   visibility, or programmatically dismiss it.
5. Respond to LEO clinical safety advisories within the documented
  response window (target: 24 hours for safety-class advisories;
   1 hour for critical-class advisories).

## 5. Onboarding artefacts (mandatory before production)

LEO MUST hold all four of the following before issuing production
widget tokens to a host:

- (a) LEO SaaS Embedding Agreement (signed)
- (b) Data Processing Agreement (signed)
- (c) Reference to the LEO DCB0129 supplier safety case the host
has accepted
- (d) Acknowledgement of this Instructions For Use document, with
the version string recorded against the host

The widget-token exchange endpoint refuses to mint tokens for any
host whose register record is incomplete. See
`services/api/app/routers/sdk_auth.py`.

## 6. Versioning and change control

- This IFU is versioned. The version string above is the canonical
identifier; every host's onboarding record stores the version it
acknowledged.
- Material changes (changes to host obligations, scope of intended
use, or onboarding artefacts) require a new version, re-issue to
every host, and a fresh acknowledgement before the next
production widget token is minted under the new version.
- Editorial changes (typos, formatting, clarifications that do not
change obligations) increment the patch number and do not
require re-acknowledgement.

## 7. Reporting

Hosts SHALL report any of the following to LEO within the
documented response window:

- A reviewer accepts or rejects an AI proposal that the reviewer
believes was clinically incorrect.
- The widget renders an SBAR that the reviewer believes contains a
patient-safety-relevant error not flagged by the disclosure.
- A widget release introduces a regression visible to the
reviewer.

Channel: [clinical-safety@leo.mizaic.io](mailto:clinical-safety@leo.mizaic.io)