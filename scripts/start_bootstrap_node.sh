#!/bin/bash

# Запуск узла как bootstrap для P2P сети

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

source venv/bin/activate

# Параметры bootstrap узла
BOOTSTRAP_PORT=${1:-8888}
BOOTSTRAP_HOST=${2:-"0.0.0.0"}

echo "🌐 Запуск bootstrap узла на $BOOTSTRAP_HOST:$BOOTSTRAP_PORT"

# Создание специального конфига для bootstrap узла
if [ ! -f "config.bootstrap.yaml" ]; then
    cat > config.bootstrap.yaml << EOF
network:
  listen_port: $BOOTSTRAP_PORT
  bootstrap_nodes: []
  is_bootstrap_node: true
  
database:
  path: "./data/bootstrap_node.db"
  
logging:
  level: "INFO"
  file: "./logs/bootstrap.log"
EOF
fi

# Запуск специального скрипта для bootstrap узла
python -c "
import asyncio
import logging
from src.network.p2p_bootstrap import P2PBootstrapNode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('bootstrap')

async def run_bootstrap():
    node = P2PBootstrapNode('$BOOTSTRAP_HOST', $BOOTSTRAP_PORT)
    await node.start()
    logger.info(f'Bootstrap node started on {$BOOTSTRAP_HOST}:{$BOOTSTRAP_PORT}')
    
    try:
        # Бесконечная работа
        while True:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        logger.info('Shutting down bootstrap node...')
        await node.stop()

asyncio.run(run_bootstrap())
"

echo "✅ Bootstrap узел остановлен"