# Tokenlogue Brand Assets

The Tokenlogue mark brings together dialogue, local history, and controlled
tokens. Its speech-bubble silhouette represents conversation, the three rows
suggest a locally retained message history, and the square details represent
individual tokens under deliberate control.

## Colors

- Graphite: `#151A1F`
- Turquoise: `#27D3C2`
- Pale mint: `#8AF1E5`

## SVG sources

- `source/tokenlogue-icon.svg` is the full-color master application icon.
- `source/tokenlogue-icon-foreground.svg` is the transparent Android adaptive
  foreground.
- `source/tokenlogue-icon-background.svg` is the solid adaptive background.
- `source/tokenlogue-icon-monochrome.svg` is the single-color source for
  Android themed icons.

The master icon uses flat fills only, without gradients or filters. The
Android foreground is reduced to the central safe zone so that platform masks
do not crop the mark. The separate Android layers are retained under
`packaging/icons/android/` and will be connected only when a real Android build
is verified.

This artwork is the original visual identity of Tokenlogue.
