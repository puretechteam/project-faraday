# Credits

## Desktop app (PySide6)

The Qt GUI bundles SVG icons from **Lucide** v0.460.0 (https://lucide.dev), ISC License.
They live in `faraday/qt/resources/icons/lucide/` with the license text in
`LICENSE-lucide.txt`. Icons are recoloured at runtime to match the theme.

The app icon is drawn in code (`faraday/qt/icons.py`, `brand_pixmap`): the Lucide
`vault` glyph on a blue to violet tile.

## Passphrase wordlist

`faraday/generator/eff_large_wordlist.txt` is the EFF Large Wordlist, CC BY 3.0 US
(see `faraday/generator/WORDLIST_ATTRIBUTION.md`).
