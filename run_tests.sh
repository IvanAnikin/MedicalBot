#!/bin/bash
# MedicalBot Test Suite - Quick Reference

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     MedicalBot Automated Testing - Quick Reference        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${YELLOW}SETUP${NC}"
echo -e "  ${BLUE}1. Install test dependencies:${NC}"
echo "     pip install -r requirements.txt"
echo ""

echo -e "${YELLOW}RUN TESTS${NC}"
echo -e "  ${BLUE}2a. Run all tests:${NC}"
echo "     pytest tests/"
echo ""
echo -e "  ${BLUE}2b. Run with verbose output:${NC}"
echo "     pytest -v tests/"
echo ""
echo -e "  ${BLUE}2c. Run with coverage report:${NC}"
echo "     pytest --cov=app --cov-report=html tests/"
echo ""

echo -e "${YELLOW}TEST SELECTION${NC}"
echo -e "  ${BLUE}3a. Run unit tests only:${NC}"
echo "     pytest -m unit tests/"
echo ""
echo -e "  ${BLUE}3b. Run integration tests:${NC}"
echo "     pytest -m integration tests/"
echo ""
echo -e "  ${BLUE}3c. Skip slow tests:${NC}"
echo "     pytest -m 'not slow' tests/"
echo ""
echo -e "  ${BLUE}3d. Run specific test file:${NC}"
echo "     pytest tests/test_state.py"
echo ""
echo -e "  ${BLUE}3e. Run specific test class:${NC}"
echo "     pytest tests/test_state.py::TestAppStateBasics"
echo ""
echo -e "  ${BLUE}3f. Run specific test:${NC}"
echo "     pytest tests/test_state.py::TestAppStateBasics::test_state_initialization"
echo ""

echo -e "${YELLOW}TEST OUTPUT OPTIONS${NC}"
echo -e "  ${BLUE}4a. Short traceback:${NC}"
echo "     pytest --tb=short tests/"
echo ""
echo -e "  ${BLUE}4b. Show print statements:${NC}"
echo "     pytest -s tests/"
echo ""
echo -e "  ${BLUE}4c. Stop on first failure:${NC}"
echo "     pytest -x tests/"
echo ""
echo -e "  ${BLUE}4d. Show local variables:${NC}"
echo "     pytest -l tests/"
echo ""

echo -e "${YELLOW}COVERAGE REPORTS${NC}"
echo -e "  ${BLUE}5a. Terminal coverage report:${NC}"
echo "     pytest --cov=app --cov-report=term-missing tests/"
echo ""
echo -e "  ${BLUE}5b. HTML coverage report:${NC}"
echo "     pytest --cov=app --cov-report=html tests/"
echo "     # Then open: htmlcov/index.html"
echo ""

echo -e "${YELLOW}TEST STATISTICS${NC}"
echo -e "  ${BLUE}6. Count tests:${NC}"
echo "     pytest --collect-only tests/ | grep 'test session starts' -A 1"
echo ""

echo -e "${YELLOW}PARALLEL EXECUTION${NC}"
echo -e "  ${BLUE}7. Run tests in parallel (faster):${NC}"
echo "     pip install pytest-xdist"
echo "     pytest -n auto tests/"
echo ""

echo -e "${YELLOW}QUICK START${NC}"
echo -e "  ${BLUE}Complete test flow:${NC}"
echo "     1. cd /Users/ivananikin/Documents/MedicalBot"
echo "     2. source venv/bin/activate"
echo "     3. pip install -r requirements.txt"
echo "     4. pytest tests/ -v --cov=app --cov-report=html"
echo ""

echo -e "${YELLOW}TEST FILES${NC}"
echo -e "  ${GREEN}✓ tests/test_state.py${NC}        - State management (35+ tests)"
echo -e "  ${GREEN}✓ tests/test_audio_manager.py${NC} - Audio recording (25+ tests)"
echo -e "  ${GREEN}✓ tests/test_openai_client.py${NC} - OpenAI integration (30+ tests)"
echo -e "  ${GREEN}✓ tests/test_endpoints.py${NC}    - FastAPI endpoints (40+ tests)"
echo -e "  ${GREEN}✓ tests/test_edge_cases.py${NC}   - Edge cases (25+ tests)"
echo ""

echo -e "${YELLOW}TOTAL: 155+ automated tests${NC}"
echo ""

echo -e "${YELLOW}EXPECTED RESULTS${NC}"
echo -e "  ${GREEN}✓ All 155+ tests should pass${NC}"
echo -e "  ${GREEN}✓ Coverage should be 90%+${NC}"
echo -e "  ${GREEN}✓ Execution time <5 seconds${NC}"
echo ""

echo -e "${BLUE}For detailed documentation, see: TESTING_GUIDE_AUTOMATED.md${NC}"
