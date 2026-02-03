#!/bin/bash
# Quick script to view Frontegg authentication diagnostics
# Run this on your Mac

echo "🔍 Starting Frontegg Authentication Diagnostic..."
echo ""

# Step 1: Start containers if not running
echo "Step 1: Ensuring containers are running..."
docker compose up -d

# Step 2: Wait for frontend to be ready
echo "Step 2: Waiting for frontend container to start..."
sleep 10

# Step 3: Check if frontend is running
echo "Step 3: Checking frontend status..."
docker compose ps frontend

# Step 4: Open browser
echo "Step 4: Opening browser to diagnostic screen..."
echo ""
echo "✅ Browser should open at http://localhost:3000"
echo ""
echo "📋 What to look for in the diagnostic screen:"
echo "   - Environment Variables section (should show Frontegg URLs)"
echo "   - Authentication State (isAuthenticated, isLoading)"
echo "   - localStorage contents (jwt_token status)"
echo ""
echo "⚠️  If you see a white screen, take a screenshot and share it."
echo ""

# Open browser (works on Mac)
open http://localhost:3000
