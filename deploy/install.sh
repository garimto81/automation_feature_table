#!/bin/bash
# Synology NAS 설치 스크립트
# 사용법: chmod +x install.sh && ./install.sh

set -e

INSTALL_DIR="/volume1/docker/poker-capture"
DATA_DIR="/volume1/docker/poker-capture/data"
PG_DATA_DIR="/volume1/docker/postgresql/data"
POKERGFX_DIR="/volume1/docker/pokergfx/hands"

echo "=== Poker Hand Capture System Installer ==="
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. 시스템 확인
echo -e "${YELLOW}[1/6] Checking system requirements...${NC}"

# Docker 확인
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker not found. Please install Container Manager from Package Center.${NC}"
    exit 1
fi

# docker-compose 확인
if ! command -v docker-compose &> /dev/null; then
    # Synology에서 docker-compose 경로
    if [ -f "/usr/local/bin/docker-compose" ]; then
        alias docker-compose="/usr/local/bin/docker-compose"
    else
        echo -e "${RED}Error: docker-compose not found.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}  Docker: $(docker --version)${NC}"

# 2. 디렉토리 생성
echo -e "${YELLOW}[2/6] Creating directories...${NC}"
mkdir -p "$INSTALL_DIR/app"
mkdir -p "$DATA_DIR"
mkdir -p "$PG_DATA_DIR"
mkdir -p "$POKERGFX_DIR"

echo -e "${GREEN}  Created: $INSTALL_DIR${NC}"
echo -e "${GREEN}  Created: $POKERGFX_DIR${NC}"

# 3. 환경변수 설정
echo -e "${YELLOW}[3/6] Configuring environment...${NC}"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo -n "Enter PostgreSQL password: "
    read -s DB_PASSWORD
    echo ""

    cat > "$INSTALL_DIR/.env" << EOF
# Poker Hand Capture System Configuration
DB_PASSWORD=${DB_PASSWORD}
PGADMIN_PASSWORD=${DB_PASSWORD}
LOG_LEVEL=INFO
VMIX_AUTO_RECORD=false
POKERGFX_MODE=json
POKERGFX_JSON_PATH=/watch
POKERGFX_POLLING_INTERVAL=2.0
EOF

    chmod 600 "$INSTALL_DIR/.env"
    echo -e "${GREEN}  Created .env file${NC}"
else
    echo -e "${GREEN}  Using existing .env file${NC}"
fi

# 4. 설치 파일 확인
echo -e "${YELLOW}[4/6] Checking installation files...${NC}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 파일 복사 (현재 디렉토리에서 실행 시)
if [ -d "$SCRIPT_DIR/app" ]; then
    cp -r "$SCRIPT_DIR/app/"* "$INSTALL_DIR/app/"
    echo -e "${GREEN}  Copied application files${NC}"
fi

if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    cp "$SCRIPT_DIR/docker-compose.yml" "$INSTALL_DIR/"
    echo -e "${GREEN}  Copied docker-compose.yml${NC}"
fi

# 필수 파일 확인
if [ ! -f "$INSTALL_DIR/docker-compose.yml" ]; then
    echo -e "${RED}Error: docker-compose.yml not found in $INSTALL_DIR${NC}"
    exit 1
fi

if [ ! -f "$INSTALL_DIR/app/Dockerfile" ]; then
    echo -e "${RED}Error: Dockerfile not found in $INSTALL_DIR/app${NC}"
    exit 1
fi

# 5. 빌드 및 실행
echo -e "${YELLOW}[5/6] Building and starting containers...${NC}"

cd "$INSTALL_DIR"

# 기존 컨테이너 중지
docker-compose down 2>/dev/null || true

# 빌드 및 실행
docker-compose up -d --build

# 6. 상태 확인
echo -e "${YELLOW}[6/6] Verifying installation...${NC}"
sleep 5

echo ""
echo "=== Container Status ==="
docker-compose ps

echo ""
echo -e "${GREEN}=== Installation Complete ===${NC}"
echo ""
echo "Configuration:"
echo "  - PokerGFX JSON Path: $POKERGFX_DIR"
echo "  - Windows Network Path: \\\\$(hostname)\\docker\\pokergfx\\hands\\"
echo ""
echo "Commands:"
echo "  - View logs: docker-compose logs -f poker-capture"
echo "  - Stop: docker-compose down"
echo "  - Restart: docker-compose restart"
echo ""
echo "Database:"
echo "  - Host: localhost:5432"
echo "  - Database: poker_hands"
echo "  - User: poker"
