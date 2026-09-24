# MachineOpp — Downloadable Content

This repository hosts optional downloadable content (DLC) for the **MachineOpp**
Android app (Pappa Tango Solutions, LLC). The app fetches these files at runtime to
seed a user's local tool and machine libraries.

## What's here
- **Starter tool packs** (`starter_*.json`, indexed in `index.json`) — MachineOpp's
  own generic tooling data (common end mills, drills, taps, and turning inserts) with
  the app's built-in baseline speeds & feeds. No manufacturer part numbers.
- **Machine specifications** (`machines/`) — factual machine specs (model, axis/turret
  configuration, rapids, max spindle RPM, tool-change time) used by the app's G-code
  cycle-time analyzer. Machine and model names are trademarks of their respective
  owners and are referenced only to identify equipment.

## What's NOT here
This repository intentionally contains **no third-party manufacturer tool catalogs** —
no vendor part-number catalogs and no reproductions of any manufacturer's published
speeds/feeds or grade tables.

## License
See `LICENSE`.
