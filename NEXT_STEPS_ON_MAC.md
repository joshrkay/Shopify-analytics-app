# What to Do Next on Your Mac

## Current Situation

You just ran `docker compose down -v` and `docker compose up -d`. The containers are starting, but we need to:
1. Wait for `npm install` to finish in the frontend container
2. Open browser to see the diagnostic screen
3. Share what the diagnostic screen shows

## Commands to Run (Copy-Paste These Into Your Mac Terminal)

### Step 1: Check if frontend is ready (run this in your terminal)

```bash
docker compose logs -f frontend
```

**What to look for:**
- Wait until you see: `VITE v5.x.x ready in XXX ms`
- Or: `Local: http://localhost:3000/`
- This means npm install finished and Vite dev server is running

**Press CTRL+C** to stop viewing logs once you see it's ready.

---

### Step 2: Open browser to diagnostic screen

```bash
open http://localhost:3000
```

This should open your default browser to the diagnostic screen.

---

## What the Diagnostic Screen Shows

You should see a page titled **"🔍 Frontegg Authentication Diagnostics"** with:

### 1. Authentication State (JSON block)
Look for these fields:
- `"isAuthenticated"`: Should say `"NO ❌"` or `"YES ✅"`
- `"isLoading"`: Should say `"YES"` or `"NO"`
- `"envVars"`: Should show URLs (not "MISSING ❌")
- `"hookError"`: Should say `"NONE"` (if there's an error, that's the problem)

### 2. Environment Configuration
Should show:
- **Base URL**: `https://markisight.frontegg.com` ✅
- **Client ID**: `9b77c0fb-2532-489b-a31c-3ac4ebe7b9d7` ✅
- **API URL**: `http://localhost:8000` ✅

If any of these show "MISSING ❌", that's the problem.

### 3. Three Buttons
- **"🔄 Try to Show Login Form"** - Click this if you don't see a login form
- **"🔄 Reload Page"** - Refreshes the page
- **"🗑️ Clear Storage & Reload"** - Clears browser localStorage and reloads

---

## What to Share With Me

**Take a screenshot** or copy-paste the JSON from the "Authentication State" section and share it.

Specifically, I need to see:
- The value of `isAuthenticated`
- The value of `envVars` (all three URLs)
- The value of `hookError`
- The value of `localStorage.jwt_token`

---

## If You See a White Screen Instead

If the page is completely blank/white:
1. Try opening in **incognito mode**: `open -a "Google Chrome" http://localhost:3000 --args --incognito`
2. Check frontend logs: `docker compose logs frontend | tail -50`
3. Share the last 50 lines of logs with me

---

## If You're Stuck

Just run these two commands and share the output:

```bash
# Command 1: Check container status
docker compose ps

# Command 2: Check frontend logs
docker compose logs frontend | tail -30
```

Copy-paste the output and I'll diagnose from there.

---

## Quick Troubleshooting

### Frontend container keeps restarting?
```bash
docker compose logs frontend
```
Look for error messages about missing packages or build failures.

### Can't access localhost:3000?
```bash
# Check if port is in use
lsof -i :3000
```

### Want to start completely fresh?
```bash
docker compose down -v
docker compose up -d
# Wait 60 seconds for npm install
sleep 60
open http://localhost:3000
```

---

**Ready?** Run Step 1 and Step 2 above, then share the diagnostic screen with me! 🚀
