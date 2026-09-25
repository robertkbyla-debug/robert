# Cabinet of Inspiration

A personal site for the artists I follow, the winemakers I love, and the quotes I keep.

No build step. It's just `index.html`, `styles.css`, `app.js` and **`data.js`**.

## Adding things

**The permanent way:** edit `data.js`. It has three lists (`artists`, `winemakers`, `quotes`), and each entry is a small block you can copy and change. Commit, and the site updates.

**The quick way:** on the live site, click **+ add artist / winemaker / quote**. The entry is saved in your browser right away and marked "draft". When you're ready, click **export my additions** in the footer and paste the blocks into `data.js`.

## Design

The design takes its cues from contemporary art magazines (*Flash Art*, *Spike*, *Mousse*): a stark white page, huge condensed **Archivo** headlines, **Instrument Serif** for quotes and prose, hard black rules, and one signal red.

- **Cover:** a wordmark sized to fill the page width, a table of contents, and a generated artwork. Click the artwork to redraw it.
- **Artists:** a numbered list. Hover over a name to see its artwork follow your cursor, and click to open the full entry.
- **Winemakers:** a grid of cards headed by the region in big type. Each card turns red on hover.
- **Words:** an inverted black section that shows one quote at a time. Your quotes also scroll in a red ticker at the top of the page.

Every artist gets their own artwork, generated from their name in one of four styles: halftone dots, bars, a giant initial, or a sliced disc. To change the accent color, edit `--signal` at the top of `styles.css`.

## Viewing it

- Locally: open `index.html` in a browser.
- Online (free): push to GitHub → repo **Settings → Pages** → Source: *Deploy from a branch* → pick your branch and `/ (root)`.
