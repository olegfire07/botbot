#!/bin/bash
# Script to deploy Web App to GitHub Pages repository

REPO_URL="https://github.com/olegfire07/BestBOT.git"
TEMP_DIR="temp_deploy_bestbot"
SOURCE_DIR="modern_bot/web_app"

echo "🚀 Starting deployment to $REPO_URL..."

# 1. Clean previous temp dir
if [ -d "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
fi

# 2. Clone repository
echo "📥 Cloning repository..."
git clone "$REPO_URL" "$TEMP_DIR"

if [ ! -d "$TEMP_DIR" ]; then
    echo "❌ Failed to clone repository. Check your internet connection."
    exit 1
fi

# 3. Copy files
echo "cw Copying Web App files..."
cp "$SOURCE_DIR/index.html" "$TEMP_DIR/"
cp "$SOURCE_DIR/super_admin.html" "$TEMP_DIR/"
cp "$SOURCE_DIR/app.js" "$TEMP_DIR/"
cp "$SOURCE_DIR/styles.css" "$TEMP_DIR/"
cp "$SOURCE_DIR/service-worker.js" "$TEMP_DIR/"
cp "$SOURCE_DIR/ux-improvements.js" "$TEMP_DIR/"
cp "$SOURCE_DIR/quiz_questions.json" "$TEMP_DIR/"
cp "$SOURCE_DIR/fianit-logo.jpg" "$TEMP_DIR/"

# 4. Commit and Push
cd "$TEMP_DIR" || exit

# Check if there are changes
if [ -z "$(git status --porcelain)" ]; then 
    echo "✨ No changes to deploy."
else
    git add .
    git commit -m "Update Web App: $(date '+%Y-%m-%d %H:%M:%S')"
    
    echo "KX Pushing changes to GitHub..."
    git push origin main
    
    if [ $? -eq 0 ]; then
        echo "✅ Deployment successful!"
        echo "🌍 Pages should be available at https://olegfire07.github.io/BestBOT/"
    else
        echo "❌ Failed to push. You might need to authenticate."
        echo "Try running 'git push' manually in $TEMP_DIR"
    fi
fi

# Cleanup
cd ..
# rm -rf "$TEMP_DIR" # Keep it for manual debug if needed
