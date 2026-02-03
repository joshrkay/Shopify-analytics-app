#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT_DIR="/home/user/Shopify-analytics-app"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Frontegg Authentication Testing Script${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Navigate to project directory
echo -e "${YELLOW}→ Navigating to project directory...${NC}"
cd "$PROJECT_DIR"
pwd
echo ""

# Step 1: Install Frontegg SDK
echo -e "${YELLOW}→ Step 1/7: Installing @frontegg/react SDK...${NC}"
cd "$PROJECT_DIR/frontend"
npm install @frontegg/react
echo -e "${GREEN}✓ Frontegg SDK installed${NC}\n"

# Return to project root
cd "$PROJECT_DIR"

# Step 2: Stop existing services
echo -e "${YELLOW}→ Step 2/7: Stopping existing Docker services...${NC}"
docker compose down
echo -e "${GREEN}✓ Services stopped${NC}\n"

# Step 3: Start services
echo -e "${YELLOW}→ Step 3/7: Starting Docker services...${NC}"
docker compose up -d
echo -e "${GREEN}✓ Services started${NC}\n"

# Step 4: Wait for services to be healthy
echo -e "${YELLOW}→ Step 4/7: Waiting for services to be healthy (30 seconds)...${NC}"
sleep 30

# Step 5: Check service status
echo -e "${YELLOW}→ Step 5/7: Checking service status...${NC}"
docker compose ps
echo ""

# Step 6: Verify environment configuration
echo -e "${YELLOW}→ Step 6/7: Verifying environment configuration...${NC}"
echo -e "${BLUE}Root .env (Frontegg config):${NC}"
grep -E "FRONTEGG_CLIENT_ID|FRONTEGG_CLIENT_SECRET|CORS_ORIGINS" .env | head -4
echo ""
echo -e "${BLUE}Frontend .env (Vite config):${NC}"
cat frontend/.env
echo ""

# Step 7: Show recent backend logs
echo -e "${YELLOW}→ Step 7/7: Checking backend logs for configuration...${NC}"
docker compose logs backend | tail -30
echo ""

# Final instructions
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Open browser to: ${BLUE}http://localhost:3000${NC}"
echo -e "2. You should be redirected to Frontegg login: ${BLUE}https://markisight.frontegg.com${NC}"
echo -e "3. Login with your Frontegg credentials"
echo -e "4. After login, verify:"
echo -e "   - You're redirected back to http://localhost:3000/analytics"
echo -e "   - Open DevTools (F12) → Application → Local Storage"
echo -e "   - Check for 'jwt_token' key with JWT value"
echo -e "   - Network tab shows 'Authorization: Bearer <token>' in API calls"
echo -e ""
echo -e "${YELLOW}To view live logs:${NC}"
echo -e "  docker compose logs -f backend frontend"
echo -e ""
echo -e "${YELLOW}To check authentication in logs:${NC}"
echo -e "  docker compose logs backend | grep -i 'authenticated\\|tenant'"
echo -e ""

# Open browser (Cowork will handle this)
echo -e "${YELLOW}Opening browser to http://localhost:3000...${NC}"
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3000
elif command -v open &> /dev/null; then
    open http://localhost:3000
else
    echo -e "${RED}Could not auto-open browser. Please manually open: http://localhost:3000${NC}"
fi
