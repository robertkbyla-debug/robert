# Cabinet of Inspiration

A personal site for the artists I follow, the winemakers I love, and the quotes I keep.

No build step. It's just `index.html`, `styles.css`, `app.js` and **`data.js`**.

## Adding things

**The permanent way:** edit `data.js`. It has three lists (`artists`, `winemakers`, `quotes`), and each entry is a small block you can copy and change. Commit, and the site updates.

**The quick way:** on the live site, click **+ add artist / winemaker / quote**. The entry is saved in your browser right away and marked "draft". When you're ready, click **export my additions** in the footer and paste the blocks into `data.js`.

Each artist gets their own generated artwork, based on their name. Click the big circle at the top to redraw it.

## Viewing it

- Locally: open `index.html` in a browser.
- Online (free): push to GitHub → repo **Settings → Pages** → Source: *Deploy from a branch* → pick your branch and `/ (root)`.
