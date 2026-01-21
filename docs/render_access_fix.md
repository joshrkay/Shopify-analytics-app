# Fixing Render GitHub Access Issue

## Problem
Render shows: "It looks like we don't have access to your repo"

## Solution Steps

### Option 1: Grant Render Access to Private Repository (Recommended)

1. **Go to GitHub Repository Settings**
   - Navigate to: https://github.com/joshrkay/Shopify-analytics-app/settings/access
   - Or: Repository → Settings → Collaborators and teams

2. **Add Render as a Collaborator (if using personal account)**
   - Go to Settings → Collaborators
   - Add `render` or your Render account email
   - Grant "Read" access

3. **OR: Use GitHub App Integration (Recommended)**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click your profile → **Account Settings**
   - Go to **Connected Accounts** or **GitHub**
   - Click **Connect GitHub** or **Reconnect**
   - Authorize Render to access your repositories
   - Select the repository: `joshrkay/Shopify-analytics-app`

### Option 2: Make Repository Public (Temporary)

If you need immediate access:

1. Go to: https://github.com/joshrkay/Shopify-analytics-app/settings
2. Scroll to **Danger Zone**
3. Click **Change visibility** → **Make public**
4. Render will be able to clone
5. **Note**: Make it private again after connecting Render properly

### Option 3: Use Deploy Key (Alternative)

1. **Generate SSH Key**
   ```bash
   ssh-keygen -t ed25519 -C "render-deploy" -f ~/.ssh/render_deploy
   ```

2. **Add Deploy Key to GitHub**
   - Go to: https://github.com/joshrkay/Shopify-analytics-app/settings/keys
   - Click **Add deploy key**
   - Paste public key: `cat ~/.ssh/render_deploy.pub`
   - Check **Allow write access** (if needed)
   - Save

3. **Add to Render**
   - In Render service settings
   - Add SSH key in deployment settings

## Verify Connection

After fixing access:

1. **In Render Dashboard**
   - Go to your service
   - Click **Manual Deploy** → **Clear build cache & deploy**
   - Watch logs for successful clone

2. **Check Logs**
   - Should see: "Successfully cloned repository"
   - Should NOT see: "don't have access to your repo"

## Common Issues

### Issue: "Repository not found"
- **Cause**: Repository name mismatch or doesn't exist
- **Fix**: Verify repository URL in Render settings matches exactly

### Issue: "Permission denied"
- **Cause**: Render doesn't have read access
- **Fix**: Grant access via GitHub settings or reconnect GitHub integration

### Issue: "Branch not found"
- **Cause**: Branch name mismatch
- **Fix**: Verify `branch: main` in render.yaml matches your default branch

## Recommended Setup

1. **Use GitHub App Integration** (most secure)
   - Render → Account Settings → GitHub → Connect
   - Select repository
   - Auto-deploys work seamlessly

2. **Verify render.yaml is in root**
   - File must be at: `/render.yaml`
   - Not in subdirectory

3. **Check Branch Name**
   - Default branch is usually `main` or `master`
   - Update render.yaml if different

## After Fixing

Once access is granted:

1. Render will automatically detect `render.yaml`
2. Services will be created from blueprint
3. Auto-deploy will work on push to main
4. Health checks will monitor `/health` endpoint

## Support

If issues persist:
- Check Render status: https://status.render.com
- Render support: https://render.com/docs/support
- GitHub integration docs: https://render.com/docs/github