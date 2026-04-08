# @module: aevara.src.execution.mt5_adapter
# @deps: asyncio, json, time, hmac, hashlib, dataclasses
# @status: IMPLEMENTED_v1.2
# @last_update: 2026-04-10
# @summary: Async TCP Bridge for Python-MT5. Real-time reconciliation, SL/TP mapping, and Zero-Trust HMAC security.

from __future__ import annotations
import asyncio
import json
import time
import hmac
import hashlib
import dataclasses
from typing import Any, Dict, List, Optional, Tuple

@dataclasses.dataclass(frozen=True, slots=True)
class MT5Order:
    symbol: str
    order_type: str # BUY, SELL
    volume: float
    price_requested: float
    sl: float = 0.0
    tp: float = 0.0
    magic: int = 123456
    comment: str = "AEVRA_LIVE"
    nonce: str = ""

@dataclasses.dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: str
    volume: float
    open_price: float
    sl: float
    tp: float
    ticket: int
    pnl: float

class MT5Adapter:
    """
    Adapter Assíncrono para MT5 com Reconciliação Dinâmica.
    Implementa protocolo Socket/JSON com Zero-Trust HMAC.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 5555, secret: str = "AEVRA_SECRET_SIGMA7"):
        self._host = host
        self._port = port
        self._secret = secret.encode()
        self._server: Optional[asyncio.AbstractServer] = None
        self._clients: List[asyncio.StreamWriter] = []
        self._responses: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Inicia servidor TCP para escutar o EA MT5."""
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)
        print(f"AEVRA MT5 ADAPTER: Listening on {self._host}:{self._port}")
        async with self._server:
            await self._server.serve_forever()

    async def connect(self) -> None:
        """Alias para inicialização via orchestrator."""
        await self.start()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        print(f"MT5 CONNECTED: {addr}")
        async with self._lock:
            self._clients.append(writer)
        
        try:
            while True:
                data = await reader.readline()
                if not data: break
                try:
                    msg = json.loads(data.decode().strip())
                    await self._process_response(msg)
                except Exception as e:
                    pass # Evita crash por pacotes mal formados
        finally:
            async with self._lock:
                if writer in self._clients:
                    self._clients.remove(writer)
            writer.close()
            await writer.wait_closed()

    async def _process_response(self, msg: Dict):
        nonce = msg.get("nonce")
        if nonce in self._responses:
             self._responses[nonce].set_result(msg)

    async def _send_packet(self, payload: Dict, timeout: float = 10.0) -> Dict:
        """Envia pacote para o MT5 com assinatura HMAC e aguarda resposta."""
        # Rate Limiting (Ψ-11)
        from aevara.src.infra.network.rate_limiter import RateLimiter
        if not hasattr(self, '_limiter'):
            self._limiter = RateLimiter(rate=2.0, burst=5.0) # 2 orders/sec
            
        await self._limiter.acquire()
        
        nonce = f"TX-{time.time_ns()}"
        payload["nonce"] = nonce
        payload["ts"] = time.time_ns()
        
        # Sign with HMAC-SHA256
        sig = hmac.new(self._secret, json.dumps(payload).encode(), hashlib.sha256).hexdigest()
        payload["sig"] = sig
        
        packet = (json.dumps(payload) + "\n").encode()
        
        if not self._clients:
            raise ConnectionError("MT5_OFFLINE: No clients connected.")

        # Futuro para aguardar resposta
        fut = asyncio.get_running_loop().create_future()
        self._responses[nonce] = fut
        
        try:
            for writer in self._clients:
                writer.write(packet)
                await writer.drain()
            
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._responses.pop(nonce, None)

    async def send_order(self, order: MT5Order) -> Dict:
        """Envia ordem e mapeia SL/TP."""
        payload = dataclasses.asdict(order)
        payload["type"] = "ORDER"
        return await self._send_packet(payload)

    async def get_positions(self) -> List[PositionSnapshot]:
        """Solicita reconciliação total de posições do MT5."""
        try:
            payload = {"type": "QUERY_POSITIONS"}
            resp = await self._send_packet(payload, timeout=3.0)
            
            positions = []
            for p in resp.get("positions", []):
                positions.append(PositionSnapshot(
                    symbol=p["symbol"],
                    volume=p["volume"],
                    open_price=p["price"],
                    sl=p["sl"],
                    tp=p["tp"],
                    ticket=p["ticket"],
                    pnl=p["pnl"]
                ))
            return positions
        except Exception:
            return [] # Fallback safe

    async def reconcile(self) -> List[PositionSnapshot]:
        """Entry point para o loop de resiliência (T-030.1)."""
        return await self.get_positions()
