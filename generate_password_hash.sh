#!/bin/bash
# Generate password hash inside Docker container
# Usage: docker exec -it notediscovery /app/generate_password_hash.sh

echo "=========================================="
echo "  NoteDiscovery Password Hash Generator"
echo "=========================================="
echo ""
echo "This will generate a bcrypt hash for your password."
echo ""

# Prompt for password
read -s -p "Enter your password: " PASSWORD
echo ""
read -s -p "Confirm password: " PASSWORD2
echo ""

# Check if passwords match
if [ "$PASSWORD" != "$PASSWORD2" ]; then
    echo ""
    echo "❌ Passwords do not match!"
    exit 1
fi

# Check if password is empty
if [ -z "$PASSWORD" ]; then
    echo ""
    echo "❌ Password cannot be empty!"
    exit 1
fi

echo ""
echo "Generating hash..."
echo ""

# Generate hash using Python
HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw(b'$PASSWORD', bcrypt.gensalt()).decode())")

if [ $? -eq 0 ]; then
    echo "=========================================="
    echo "  ✅ Password hash generated!"
    echo "=========================================="
    echo ""
    echo "Copy this hash to your config.yaml:"
    echo ""
    echo "password_hash: \"$HASH\""
    echo ""
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Update config.yaml with the hash above"
    echo "2. Set enabled: true in the security section"
    echo "3. Restart the container: docker-compose restart"
    echo "=========================================="
else
    echo "❌ Failed to generate hash"
    exit 1
fi

