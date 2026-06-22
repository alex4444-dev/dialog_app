import miniupnpc

def open_port(port, protocol='TCP'):
    """
    Пытается открыть порт на роутере через UPnP.
    Возвращает внешний IP и порт или None при ошибке.
    """
    upnp = miniupnpc.UPnP()
    upnp.discover()                  # Ищем UPnP-устройства в сети[reference:5]
    upnp.selectigd()                 # Выбираем интернет-шлюз (роутер)
    
    # Узнаём наш локальный IP
    local_ip = upnp.lanaddr
    
    # Пытаемся добавить правило проброса порта
    # (внешний_порт, протокол, внутренний_порт, локальный_IP, описание)
    result = upnp.addportmapping(port, protocol, local_ip, port, f'DialogApp-{port}', '')
    
    if result:
        external_ip = upnp.externalipaddress()
        print(f"✅ Порт {port} ({protocol}) успешно открыт! Внешний IP: {external_ip}")
        return external_ip, port
    else:
        print(f"❌ Не удалось открыть порт {port}")
        return None

if __name__ == "__main__":
    open_port(9000)      # Открыть TCP порт 9000 для P2P
    open_port(9891, 'UDP')  # Открыть UDP порт 9891 для DHT
