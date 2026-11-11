import asyncio
from dev.gateway import forward


def test_gateway_preserves_large_response_after_client_half_close():
    async def scenario():
        payload = b'local streaming response\n' * 10000

        async def respond(reader, writer):
            try:
                assert await reader.read() == b'request'
                writer.write(payload)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        async with await asyncio.start_server(respond, '127.0.0.1', 0) as upstream:
            port = upstream.sockets[0].getsockname()[1]
            async with await asyncio.start_server(
                    lambda r, w: forward(r, w, '127.0.0.1', port), '127.0.0.1', 0) as gateway:
                reader, writer = await asyncio.open_connection('127.0.0.1', gateway.sockets[0].getsockname()[1])
                try:
                    writer.write(b'request')
                    await writer.drain()
                    writer.write_eof()
                    assert await reader.read() == payload
                finally:
                    writer.close()
                    await writer.wait_closed()

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))
