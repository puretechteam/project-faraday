# Icon Attribution

The Project Faraday GUI references a bundled icon set used by the sidebar, toolbar,
and entry cards.

## Intended Source

- **Feather** (https://feathericons.com) — MIT License
- **Lucide** (https://lucide.dev) — ISC License (MIT-compatible)

Both are permissively licensed and suitable for bundling in a MIT-licensed product.

## Required Icons

PNGs at @1x (~24px) and @2x (~48px) for:

`vault`, `key`, `crypto`, `note`, `card`, `user`, `emergency`, `shield`,
`wifi`, `file`, `threat`, `search`, `lock`, `plus`, `settings`, `menu`,
`copy`, `eye`, `edit`, `trash`, `chevron`, `refresh`

## License

Feather icons are licensed under the MIT License:

> Copyright (c) 2013-2024 Cole Bemis
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction...

Lucide icons are licensed under the ISC License (functionally equivalent to MIT).

## Status

Icon PNGs are not yet bundled in this tree. The widget layer
(`faraday/gui/widgets/_icons.py`) falls back to text/label glyphs when a PNG
is missing, so the interface remains fully functional without them. Drop the
licensed PNGs listed above into this directory to enable icon rendering.
