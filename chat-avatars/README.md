# Support avatar bank (24 portraits)

Faces for the floating chat widget (`blocks/chat-widget.*`). These are deliberately
separate from `people/`: a face that answers the chat must never be the same face
that writes a testimonial two screens below.

- Source: Pexels — https://www.pexels.com/
- License: Pexels License — free for commercial use, attribution not required
  (https://www.pexels.com/license/)
- Every file, its Pexels id and source page are listed in `manifest.json`.
- 12 women (`s-women-*.jpg`) + 12 men (`s-men-*.jpg`), 300×300 centre-cropped.

`gen_plan.pick_chat_agent()` rotates the bank against the last few plans and picks
a first name whose gender matches the portrait. Only the chosen portrait is copied
to `sites/<domain>/img/chat-agent.jpg`; the rest of the bank never ships.

If you replace a file, keep `manifest.json` and the `s-women` / `s-men` prefix in
sync — the name picker reads the prefix.
