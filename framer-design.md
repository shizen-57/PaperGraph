---
version: "superdesign-alpha"
name: "Void-canvas agent noir"
description: "Near-black IDE-like dark mode carrying a rationed electric-blue accent, rounded display sans headlines, and monospace/serif accent faces borrowed from a live design-tool interface."
colors:
  background: "#000000"
  surface: "#111111"
  surface-alt: "#1E1E1E"
  text-primary: "#FFFFFF"
  text-secondary: "#999999"
  text-muted: "#666666"
  accent: "#0099FF"
  accent-secondary: "#00BB88"
  link: "#0000EE"
  border: "#767676"
typography:
  display-lg:
    fontFamily: "GT Walsheim Medium"
    fontSize: "54px"
    fontWeight: 500
    lineHeight: "1"
    letterSpacing: "-2.2px"
  headline-md:
    fontFamily: "GT Walsheim Medium"
    fontSize: "44px"
    fontWeight: 500
    lineHeight: "1.1"
    letterSpacing: "-1.8px"
  body-md:
    fontFamily: "Inter Variable"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "1"
  label-md:
    fontFamily: "GT Walsheim Medium"
    fontSize: "54px"
    fontWeight: 500
    lineHeight: "0.8"
    letterSpacing: "-2.2px"
  accent-mono:
    fontFamily: "Input Mono Regular"
    fontWeight: 400
    role: "chat/agent-console text, metric labels"
  accent-mono-bold:
    fontFamily: "Input Mono Bold"
    fontWeight: 700
    role: "emphasized console/data values"
  accent-serif:
    fontFamily: "Times New Roman"
    role: "rare editorial interruption inside media cards"
spacing:
  base: "5px"
  gap: "20px"
  section-padding: "120px"
rounded:
  control: "8px"
  control-lg: "10px"
  card: "15px"
  card-lg: "20px"
  chip: "6px"
  pill: "100px"
components:
  button-hero-primary:
    background: "#DEDEDE"
    text-color: "#000000"
    radius: "10px"
    height: "34px"
    padding: "10px"
    hover-opacity: "0.6386"
    note: "observed near-white solid pill-corner button, hero row, left of secondary"
  button-hero-secondary:
    background: "#000000"
    text-color: "#FFFFFF"
    radius: "10px"
    height: "34px"
    padding: "10px"
    shadow-resting: "rgba(0, 0, 0, 0.25) 0px 0px 0px 0px"
    hover-opacity: "0.6355"
  button-nav-cta:
    background: "#FFFFFF"
    text-color: "#0000EE"
    radius: "8px"
    height: "30px"
  button-utility:
    background: "#FFFFFF"
    text-color: "#000000"
    radius: "8px"
    height: "30px"
    padding: "0px 10px"
    note: "used for repeated end-of-page action chips (Read story, Browse, See sites)"
  card-media-bottom:
    background: "transparent"
    radius: "0px"
    padding: "0px"
    anatomy: "heading/label block above, media fills lower portion"
  card-media-top-bleed:
    background: "transparent"
    radius: "0px"
    padding: "0px"
    anatomy: "full-bleed media at top, label/meta below"
  card-glass-tile:
    background: "rgba(0, 153, 255, 0.22)"
    radius: "0px"
    padding: "0px"
    anatomy: "translucent tinted panel containing two inner tiles"
    backdrop-filter: "blur(3px)"
  card-glass-plain:
    background: "rgba(0, 153, 255, 0.22)"
    radius: "0px"
    padding: "0px"
    anatomy: "translucent tinted panel, single content block"
    backdrop-filter: "blur(5px)"
---
# Void-canvas agent noir
Source: https://framer.com/

## Overview
This is a dark-mode-default system built around a working software canvas, not a marketing illustration — the product itself (an agent chat panel, a layer/property inspector, a CMS table) is the hero imagery. The palette is almost pure black (~83% of rendered pixels is `#000000`, another ~10% a near-black `#111111` panel tone), so the aesthetic reads as void-canvas: content floats on emptiness with no gradient wash behind it. A single electric blue (`#0099FF`) is the only saturated hue in the system, rationed to thin rules, glass tiles, and one accent gradient. Typography is a rounded geometric sans (GT Walsheim Medium) at very tight negative tracking for display type, paired with a technical Inter/monospace body register that mimics IDE and console text — this is what makes the system feel like a design tool's own interface rather than a conventional landing page.

## Composition
The first screen is text-led: a two-line rounded-sans headline sits top-left, immediately followed by a primary/secondary button pair and a small right-aligned stat line, then a large bordered canvas mockup (a simulated design-tool viewport with an agent chat panel docked right) fills the remaining fold. Below the fold the rhythm alternates: a logo strip (dense, small, grayscale marks), a two-line headline + agent-panel demo band, a stat/dashboard bento of tool previews, a masonry of shipped-site screenshots at mixed aspect ratios, a uniform card row of partner logos, and a link-dense footer. Density is high mid-page (many small panels, tables, chips) and sparse at the very top and bottom — the deliberate choice is to let the product screenshots carry visual complexity while headlines stay short and heavily whitespaced; the rejected alternative would be a conventional hero illustration/gradient carrying the emotional weight instead of live UI chrome.

## Colors
`#000000` is the background role at ~83% of the pixel field — true black, not a near-black gray, confirmed by the pixel field and by eye. `#111111` (~10.7%) is the panel/surface role: chat panels, canvas frames, footer-adjacent zones. `#0099FF` is the sole accent, used at ~0.3% declared area but concentrated visually in border rules on the canvas mockup, translucent glass tiles (`rgba(0,153,255,0.22)`), and one corner gradient wash — never as a full background fill. `#00BB88` appears as a rare status-good tag fill (a small pill on a performance metric). `#FFFFFF` text is primary ink; `#999999` is secondary/muted metadata; `#666666` sits between for tertiary labels. `#0000EE` is reserved specifically for the nav CTA's text-on-white, an old-web "visited link blue" used deliberately as a brand wink. Borders are `#767676` (neutral hairlines) or `#0099FF` (accent hairlines on the featured canvas panel). Everything else — the vast surrounding black — is deliberately left uncolored so the one accent hue and the white product screenshots do all the work.

## Typography
Display and headline type is GT Walsheim Medium exclusively — a rounded geometric sans at 54px/1/-2.2px (display) and 44px/1.1/-1.8px (headline), always tight and left-aligned, never centered. Body and UI copy switches families entirely to Inter Variable at 14px/1/400 for readable paragraph and label text, with secondary copy dropped to the `#999999` tone. Input Mono Regular/Bold appear inside the simulated agent-console and code-like UI chrome (chat bubbles, plan steps, field values) — this monospace layer is a signature accent that signals "live tool," not marketing copy. A single Times New Roman instance surfaces inside one media card as an editorial/serif interruption, contrasting against the otherwise all-geometric-sans system. Hierarchy is purely size + family, not color: headlines are large rounded sans, everything functional is small Inter or mono.

## Layout
Content is capped at a 1200px max-width container with 120px section padding, giving generous vertical breathing room between dense bands. Three distinct grid types recur: an 8-item asymmetric grid (3 columns, 0px gap, row heights running 33/100/67 then 33/33/33 then 67/33 as a percentage of container — a bento composition of uneven tool-preview tiles, tall middle card flanked by shorter stacked ones); a 6-column, 6-item grid with a 40px horizontal gap and uniform ~13% row bands (a dense settings/list-style module); and a 4-column, 9-item grid with 40px/20px gaps and two near-even rows (~17-21% each) — a bento-style feature grid of near-equal tool cards. The shipped-sites masonry breaks this rhythm entirely with mixed aspect-ratio image cards (0px radius, 0px gap) sized by content, not a fixed track — true masonry, not bento. Spacing throughout snaps to a tight scale (5, 10, 15, 20px) rather than a loose 8pt system, giving the UI its compact, tool-like density.

## Components
- **Navbar**: 64px tall, sticky, transparent background, 10 items (logo + ~6 nav links/dropdowns + Log in + Sign up CTA, roughly). Logo is a small geometric mark + wordmark, left-aligned. CTA is solid `#FFFFFF` fill, `#0000EE` text, 8px radius, 30px height — a small, sharp-cornered pill-adjacent rectangle, not a full pill. A plain-text "Log in" link sits beside it with no fill.
- **Hero primary button**: an observed near-white solid (~`#DEDEDE`), black text, ~10px radius (slightly-rounded), 34px height, 10px padding, sitting immediately left of a black secondary button under the headline — this is the single most emphasized control on the first screen.
- **Hero secondary button**: solid `#000000` fill, `#FFFFFF` text, same 10px radius and 34px height, flat resting shadow, hover fades to ~64% opacity — a paired utility action, not the primary.
- **Utility/end-of-section buttons**: solid `#FFFFFF` fill, `#000000` text, sharper 8px radius, 30px height, tight 0/10px padding — used repeatedly as small labeled actions ("Read story"-style, "Browse"-style) attached to section headers throughout the mid-page.
- **Bento tool-preview card family** (8-up grid): transparent background, 0px radius, 0px padding, media-bottom anatomy — a short label/heading sits above, a screenshot of a tool panel (performance meter, CMS table, hosting stat) fills the remainder; asymmetric spans per the 33/100/67 row map.
- **Masonry shipped-site card family** (media-top-bleed, ×6 and ×6): transparent, 0px radius/padding, full-bleed photographic or UI screenshot fills nearly the entire card with a short caption/name overlaid near the bottom edge in white text on a dark scrim.
- **Glass accent tile family** (×3 sets of 3): `rgba(0, 153, 255, 0.22)` translucent fill, 0px radius, `blur(3px)`/`blur(5px)` backdrop-filter, containing two inner sub-tiles or a single content block — the only visibly "glassmorphic" surface in the system, used for small stat/branch/locale modules.
- **Logo strip cards**: uniform bordered rectangles (visible `#767676`-toned hairline), transparent fill, each holding one centered grayscale wordmark/logomark and a small text-link with arrow beneath — evenly spaced in a single row, horizontally scrollable.
- **Footer**: `#000000` background, 105 links organized into ~7 labeled columns (Product, Resources, Business, Company, Solutions, Compare, Community, Tools), small Inter labels in `#999999`/`#FFFFFF`, a trust-badge row and live status dot near the very bottom.

## Graphics & Effects
Gradients are used only as small compositional aids, never as full-screen washes: a vertical `linear-gradient(rgba(0,0,0,0) 0%, rgb(0,0,0) 100%)` fades a media element into the black page at its base (1.8% of page area); a horizontal twin `linear-gradient(90deg, rgba(0,0,0,0) 0%, rgb(0,0,0) 100%)` and its 96.77%-stop variant fade a strip edge into black (masonry row edges); a small `linear-gradient(90deg, rgba(0,153,255,0.1) 0%, rgba(28,28,28,0.5) 61%)` washes one accent panel corner; and a near-white-to-transparent `linear-gradient(173deg, rgb(255,255,255) 32%, rgba(0,0,0,0.1) 74%)` sits behind a single oversized numeral for emphasis. Six live video surfaces are embedded (product/tool demos) — rebuild these as static dark UI screenshots or the accent-tinted gradient stand-in. Shadows are soft and low-opacity (`rgba(0,0,0,0.25) 0 4px 8px`, `rgba(0,0,0,0.2) 0 2px 6px`, `rgba(0,0,0,0.1) 0 1px 2px`) — used under floating panels, not under flat cards. Backdrop blur (`blur(3px)`, `blur(5px)`) is reserved for the blue glass tiles only.

## Motion
Transitions are uniform and unhurried: `all 0.3s ease-in-out` governs hover and state changes system-wide (button opacity fades, panel reveals). Framer Motion drives scroll-triggered reveals of sections and staggered card entrances in the bento/masonry grids. Named keyframe animations include a blinking text-cursor effect for chat/console text, a shimmer sweep, a loading spinner, sprite-based micro-interactions, and a grain/film-noise animation looping subtly over dark surfaces — this last one is the texture layer that keeps flat black areas from feeling static.

## Guardrails
- Never fill more than a small rationed region with the `#0099FF` accent — the background stays black; blue lives in hairlines, glass tiles, and one corner gradient only.
- Do not round the utility/nav buttons past 8-10px — this system's corners are consistently slight, never a full pill except where explicitly 100px is used for tag-like chips.
- Keep card grids at 0px radius and 0px padding for the bento/masonry families — rounding these breaks the flush, tool-panel character.
- Do not substitute a glass/utility button's spec for the hero primary — the hero pair is the near-white/black 34px-height set, not the 30px white nav utility button.
- Preserve the Inter-vs-GT-Walsheim split: display headlines never use the body font and vice versa.
- Keep the grain/noise motion layer subtle — it textures black fields, it does not brighten them.