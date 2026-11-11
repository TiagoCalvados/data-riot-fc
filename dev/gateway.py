"""Forward local HTTP ports without giving app/database/mail containers egress."""
import asyncio


async def copy_stream(reader, writer):
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()
    if writer.can_write_eof():
        writer.write_eof()
        await writer.drain()


async def forward(reader, writer, host, port):
    upstream = None
    tasks = []
    try:
        remote, upstream = await asyncio.open_connection(host, port)
        tasks = [asyncio.create_task(copy_stream(reader, upstream)),
                 asyncio.create_task(copy_stream(remote, writer))]
        await asyncio.gather(*tasks)
    except OSError:
        pass  # A disconnected browser or restarting service is an ordinary close.
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writers = [writer] + ([upstream] if upstream is not None else [])
        for stream in writers:
            stream.close()
        await asyncio.gather(*(stream.wait_closed() for stream in writers), return_exceptions=True)


async def main():
    app = await asyncio.start_server(lambda r, w: forward(r, w, 'app', 8000), '0.0.0.0', 8000)
    mail = await asyncio.start_server(lambda r, w: forward(r, w, 'mailpit', 8025), '0.0.0.0', 8025)
    webmail = await asyncio.start_server(lambda r, w: forward(r, w, 'webmail', 80), '0.0.0.0', 8080)
    print('Local gateway ready: app 8000; captured mail 8025; webmail 8080', flush=True)
    async with app, mail, webmail:
        await asyncio.gather(app.serve_forever(), mail.serve_forever(), webmail.serve_forever())


if __name__ == '__main__':
    asyncio.run(main())
