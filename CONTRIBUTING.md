# Contributing

Thanks for your interest in improving **claude-token-tray**! Contributions are
welcome via pull request.

## Ground rules

- **No third-party dependencies.** The widget and its tests use the Python
  standard library only. Please keep it that way so it runs anywhere with a
  stock Python.
- **Match the existing style** (plain functions, short comments explaining
  *why*, no frameworks).
- **Tests must pass and cover your change.** Run:

  ```sh
  python3 -m unittest -v
  ```

  CI runs the same suite on every push and PR.

## Submitting a pull request

1. Fork the repository and create a feature branch.
2. Make your change, adding or updating tests in
   `test_claude_token_genmon.py`.
3. Confirm `python3 -m unittest` is green.
4. Open a PR with a clear description of the change and why.

For larger changes, opening an issue first to discuss the approach is
appreciated.

## Reporting bugs

Open a GitHub issue with:

- what you expected vs. what happened,
- your distro / Xfce / Python versions,
- the widget's output: `./claude-token-genmon.py` (this prints the GenMon XML;
  it does **not** include your token).

## License

By contributing, you agree that your contributions are licensed under the
project's [LGPL-3.0-or-later](COPYING.LESSER) license.
