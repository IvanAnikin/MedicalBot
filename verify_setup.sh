#!/bin/bash
# MedicalBot Setup Verification Script

echo "🏥 MedicalBot - Setup Verification"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check virtual environment
if [ -d "venv" ]; then
    echo -e "${GREEN}✓${NC} Virtual environment exists"
else
    echo -e "${RED}✗${NC} Virtual environment missing"
    exit 1
fi

# Check main files
files=("main.py" "requirements.txt" ".env.example" "SETUP.md")
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file exists"
    else
        echo -e "${RED}✗${NC} $file missing"
        exit 1
    fi
done

# Check app package
app_files=("app/__init__.py" "app/state.py" "app/audio_manager.py" "app/openai_client.py")
for file in "${app_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file exists"
    else
        echo -e "${RED}✗${NC} $file missing"
        exit 1
    fi
done

# Check templates
if [ -f "templates/index.html" ]; then
    echo -e "${GREEN}✓${NC} templates/index.html exists"
else
    echo -e "${RED}✗${NC} templates/index.html missing"
    exit 1
fi

# Check static folder
if [ -d "static" ]; then
    echo -e "${GREEN}✓${NC} static/ directory exists"
else
    echo -e "${RED}✗${NC} static/ directory missing"
    exit 1
fi

# Check .env file
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} .env file exists"
    if grep -q "your_api_key_here" .env; then
        echo -e "${YELLOW}⚠${NC}  .env still has placeholder - update OPENAI_API_KEY"
    fi
else
    echo -e "${RED}✗${NC} .env file missing"
    exit 1
fi

# Activate venv and check dependencies
source venv/bin/activate

echo ""
echo "Checking dependencies..."
required_packages=("fastapi" "uvicorn" "openai" "sounddevice" "numpy" "jinja2")

for package in "${required_packages[@]}"; do
    if python -c "import $package" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $package installed"
    else
        echo -e "${RED}✗${NC} $package missing"
        exit 1
    fi
done

# Check Python syntax
echo ""
echo "Checking Python syntax..."
if python -m py_compile main.py app/*.py 2>/dev/null; then
    echo -e "${GREEN}✓${NC} All Python files compile successfully"
else
    echo -e "${RED}✗${NC} Python syntax errors found"
    exit 1
fi

echo ""
echo -e "${GREEN}=================================="
echo "✓ All checks passed!"
echo -e "==================================${NC}"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your OPENAI_API_KEY"
echo "2. Run: python main.py"
echo "3. Open: http://localhost:8000/"
echo ""
