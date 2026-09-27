# Farmer AI frontend

Deploy this folder as a Vercel static project.

- Vercel Root Directory: `frontend`
- Framework Preset: `Other`
- Build Command: leave empty
- Output Directory: `.`

The frontend calls `https://agrorag-xfrx.onrender.com/ask` by default. To use another backend, add this before `/app.js` in `index.html`:

```html
<script>window.FARMER_API_URL = 'https://your-backend.example.com/ask';</script>
```
