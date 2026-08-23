# Third-party notices

## WXGF container research

ChatWechat's independently implemented WXGF partition reader was informed by the
Apache-2.0 licensed `dat2img` implementation formerly published in
`github.com/sjzar/chatlog` v0.0.31 and by its public compatibility notes.

- Project/version: `github.com/sjzar/chatlog` v0.0.31
- License: Apache License 2.0
- Package documentation: https://pkg.go.dev/github.com/sjzar/chatlog@v0.0.31/pkg/util/dat2img
- Compatibility notes: https://github.com/sjzar/chatlog/issues/197

No chatlog executable or native binary is bundled or executed by ChatWechat.

## React desktop UI

The offline web user interface bundles the following open-source packages:

- React and React DOM 19.2.7 — Meta Platforms, Inc. (MIT License)
- Zustand 5.0.14 — Paul Henschel and contributors (MIT License)
- Motion 12.42.2 — Framer B.V. (MIT License)
- Lucide React 1.24.0 — Lucide contributors (ISC License)

These packages run only inside the local pywebview window. The production UI does
not load fonts, scripts, styles, analytics, or other assets from the network.

## Portable runtime tools

The Windows portable distribution includes the following command-line runtimes.
They are copied only into build artifacts and are not committed to this repository.

- Node.js 24.16.0 — Node.js contributors (MIT License and bundled third-party
  notices). Source and binary downloads: https://nodejs.org/download/release/v24.16.0/
- FFmpeg 8.0.1 shared GPL build — FFmpeg contributors and BtbN FFmpeg-Builds
  contributors (GNU General Public License, version 3). Source project:
  https://ffmpeg.org/ and build provenance: https://github.com/BtbN/FFmpeg-Builds

The portable folder contains this notice, the FFmpeg distribution license, and
the already vendored `silk-wasm` license. Runtime files are accepted by the build
only when their SHA-256 values match `packaging/runtime.lock.json`.
