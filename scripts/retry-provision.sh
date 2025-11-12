#!/bin/bash
# Auto-retry provisioning script - cycles through all availability domains

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$PROJECT_ROOT/infrastructure"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

MAX_RETRIES=100  # Total number of retry cycles
RETRY_DELAY=300  # 5 minutes between cycles (300 seconds)

echo -e "${BLUE}🔄 Oracle Cloud ARM Instance Auto-Retry${NC}"
echo -e "Will try all 3 availability domains, then wait and retry"
echo -e "Max retries: ${MAX_RETRIES} cycles (Ctrl+C to stop)"
echo ""

# Function to try a specific AD
try_ad() {
    local ad_index=$1
    local ad_name=$2

    echo -e "${YELLOW}Trying Availability Domain ${ad_name}...${NC}"

    # Update main.tf with the AD index
    cd "$INFRA_DIR"
    sed -i "s/availability_domains\[.\]/availability_domains[$ad_index]/" main.tf

    # Run terraform
    terraform plan -out=tfplan > /dev/null 2>&1

    if terraform apply -auto-approve tfplan 2>&1 | tee /tmp/terraform-output.log | grep -q "Out of host capacity"; then
        echo -e "${RED}❌ AD-${ad_name}: No capacity${NC}"

        # Clean up partial resources
        terraform destroy -auto-approve > /dev/null 2>&1 || true

        return 1
    elif grep -q "Creation complete" /tmp/terraform-output.log; then
        echo -e "${GREEN}✅ SUCCESS! Instance created in AD-${ad_name}!${NC}"
        terraform output
        return 0
    else
        echo -e "${RED}❌ AD-${ad_name}: Other error${NC}"
        cat /tmp/terraform-output.log

        # Clean up partial resources
        terraform destroy -auto-approve > /dev/null 2>&1 || true

        return 1
    fi
}

# Initialize Terraform once
cd "$INFRA_DIR"
echo "Initializing Terraform..."
terraform init > /dev/null 2>&1

# Main retry loop
for ((cycle=1; cycle<=MAX_RETRIES; cycle++)); do
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Cycle ${cycle}/${MAX_RETRIES} - $(date)${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Try AD-1
    if try_ad 0 "1"; then
        echo -e "${GREEN}🎉 Instance successfully created!${NC}"
        echo -e "${GREEN}Run the deploy script to finish setup.${NC}"
        exit 0
    fi

    # Try AD-2
    if try_ad 1 "2"; then
        echo -e "${GREEN}🎉 Instance successfully created!${NC}"
        echo -e "${GREEN}Run the deploy script to finish setup.${NC}"
        exit 0
    fi

    # Try AD-3
    if try_ad 2 "3"; then
        echo -e "${GREEN}🎉 Instance successfully created!${NC}"
        echo -e "${GREEN}Run the deploy script to finish setup.${NC}"
        exit 0
    fi

    # All ADs failed, wait before retry
    if [ $cycle -lt $MAX_RETRIES ]; then
        echo -e "${YELLOW}All ADs full. Waiting ${RETRY_DELAY} seconds before retry...${NC}"
        echo -e "${YELLOW}Next attempt: $(date -d "+${RETRY_DELAY} seconds" 2>/dev/null || date -v+${RETRY_DELAY}S)${NC}"
        sleep $RETRY_DELAY
    fi
done

echo -e "${RED}Max retries reached. No capacity found in any AD.${NC}"
echo -e "${YELLOW}Suggestions:${NC}"
echo -e "  1. Try again during off-peak hours (11pm-7am Eastern)"
echo -e "  2. Try the Oracle Cloud web console manually"
echo -e "  3. Wait a day and try again"
exit 1
