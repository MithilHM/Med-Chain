"""MLLP listener for real-time HL7 v2 feeds from a hospital interface engine.

Run alongside the API (same database and configuration):

    python -m src.integration.mllp_server

Each framed message (<VT> payload <FS><CR>) is stored, processed, and acknowledged on the same
connection with an HL7 ACK, exactly like the HTTPS endpoint. Configure MLLP_TLS_CERT_FILE and
MLLP_TLS_KEY_FILE for TLS, and MLLP_TLS_CLIENT_CA_FILE to require client certificates (mutual TLS).
Plain MLLP must only be exposed on a private interface network or VPN.
"""
import asyncio
import logging
import signal
import ssl
from typing import Optional

from src import database
from src.config import settings
from src.integration.hl7_processor import process_hl7_message
from src.integration.hl7v2 import END_BLOCK, START_BLOCK, build_ack, frame_mllp
from src.services.events import EventRelay

logger = logging.getLogger("medchain.integration.mllp")
MAX_FRAME_BYTES = 1_000_000


def _ssl_context() -> Optional[ssl.SSLContext]:
    if not settings.MLLP_TLS_CERT_FILE:
        return None
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(settings.MLLP_TLS_CERT_FILE, settings.MLLP_TLS_KEY_FILE)
    if settings.MLLP_TLS_CLIENT_CA_FILE:
        context.load_verify_locations(settings.MLLP_TLS_CLIENT_CA_FILE)
        context.verify_mode = ssl.CERT_REQUIRED
    return context


async def _handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    logger.info("MLLP connection from %s", peer)
    buffer = b""
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > MAX_FRAME_BYTES:
                writer.write(frame_mllp(build_ack(None, "AR", "Message exceeds maximum size.")))
                await writer.drain()
                break
            while True:
                start = buffer.find(START_BLOCK)
                end = buffer.find(END_BLOCK, start + 1 if start >= 0 else 0)
                if start < 0 or end < 0:
                    break
                payload, buffer = buffer[start + 1:end], buffer[end + len(END_BLOCK):]
                try:
                    raw = payload.decode("utf-8")
                except UnicodeDecodeError:
                    raw = payload.decode("latin-1")
                outcome = await process_hl7_message(raw, settings.MLLP_SOURCE_NAME)
                logger.info("MLLP message %s -> %s (%s)", outcome.message_id, outcome.ack_code, outcome.status)
                writer.write(frame_mllp(outcome.ack))
                await writer.drain()
    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def serve() -> None:
    if not await database.check_connection():
        raise RuntimeError("Database is unavailable; the MLLP listener will not start.")
    server = await asyncio.start_server(
        _handle_connection, settings.MLLP_HOST, settings.MLLP_PORT, ssl=_ssl_context()
    )
    logger.info("MLLP listener on %s:%s (TLS=%s)", settings.MLLP_HOST, settings.MLLP_PORT, bool(settings.MLLP_TLS_CERT_FILE))
    # Without the relay, events from this process would never reach dashboards on the API processes.
    if not EventRelay.start(database.async_engine):
        logger.warning("Real-time events from this listener are not shared with the API (PostgreSQL relay unavailable).")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows event loops
            pass
    async with server:
        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(serve())
