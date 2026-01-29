#!/bin/bash
# =============================================================================
# Local Development Startup Script
# =============================================================================
# This script starts the full Shopify Analytics stack locally
#
# Usage:
#   ./scripts/start-local.sh          # Start all services
#   ./scripts/start-local.sh --stop   # Stop all services
#   ./scripts/start-local.sh --logs   # View logs
#   ./scripts/start-local.sh --reset  # Reset database and restart

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Shopify Analytics - Local Development             ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    exit 1
fi

# Determine docker-compose command
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Handle arguments
case "$1" in
    --stop)
        echo -e "${YELLOW}Stopping all services...${NC}"
        $COMPOSE_CMD down
        echo -e "${GREEN}✓ All services stopped${NC}"
        exit 0
        ;;
    --logs)
        $COMPOSE_CMD logs -f
        exit 0
        ;;
    --reset)
        echo -e "${YELLOW}Resetting database and restarting...${NC}"
        $COMPOSE_CMD down -v
        $COMPOSE_CMD up -d
        echo -e "${GREEN}✓ Database reset complete${NC}"
        ;;
    *)
        # Default: start services
        ;;
esac

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from .env.example...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created${NC}"
fi

# Start services
echo -e "${YELLOW}Starting services...${NC}"
$COMPOSE_CMD up -d

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to be ready...${NC}"
sleep 5

# Check service health
echo ""
echo -e "${BLUE}Service Status:${NC}"
echo "─────────────────────────────────────────"

# Check PostgreSQL
if $COMPOSE_CMD exec -T postgres pg_isready -U shopify_analytics_user -d shopify_analytics &> /dev/null; then
    echo -e "  PostgreSQL:  ${GREEN}✓ Running${NC} (localhost:5432)"
else
    echo -e "  PostgreSQL:  ${RED}✗ Not ready${NC}"
fi

# Check Redis
if $COMPOSE_CMD exec -T redis redis-cli ping &> /dev/null; then
    echo -e "  Redis:       ${GREEN}✓ Running${NC} (localhost:6379)"
else
    echo -e "  Redis:       ${RED}✗ Not ready${NC}"
fi

# Check Backend
sleep 3
if curl -s http://localhost:8000/health &> /dev/null; then
    echo -e "  Backend API: ${GREEN}✓ Running${NC} (http://localhost:8000)"
else
    echo -e "  Backend API: ${YELLOW}⏳ Starting...${NC} (http://localhost:8000)"
fi

# Check Frontend
if curl -s http://localhost:3000 &> /dev/null; then
    echo -e "  Frontend:    ${GREEN}✓ Running${NC} (http://localhost:3000)"
else
    echo -e "  Frontend:    ${YELLOW}⏳ Starting...${NC} (http://localhost:3000)"
fi

echo "─────────────────────────────────────────"
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    🚀 Ready to Use!                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}Frontend:${NC}  http://localhost:3000"
echo -e "  ${BLUE}API:${NC}       http://localhost:8000"
echo -e "  ${BLUE}API Docs:${NC}  http://localhost:8000/docs"
echo -e "  ${BLUE}Health:${NC}    http://localhost:8000/health"
echo ""
echo -e "${YELLOW}Commands:${NC}"
echo "  ./scripts/start-local.sh --logs   # View logs"
echo "  ./scripts/start-local.sh --stop   # Stop services"
echo "  ./scripts/start-local.sh --reset  # Reset database"
echo ""
echo -e "${YELLOW}Note:${NC} First startup may take a few minutes to download images"
echo "      and install dependencies. Check logs if services don't start."
echo ""
