# pyapp

A small greeting service.

- `greetings.py`: one greeter function per language, all with the same shape,
  registered in `GREETERS`.
- `store.py`: an in-memory item store, seeded from `data/items.json`.
- `server.py`: an HTTP handler that serves greetings and items and counts requests.
- `static.py`: reads files from `static/` for a planned `/static` endpoint.
- `logs/`: old request logs that nothing reads any more.

There is no test suite.
