# SHPD Seed Seeker Plus

A phone-first deployment wrapper for the open-source
`akhial/shpd-seed-seeker`.

## Adds

Seed Scout gains per-floor:

- Secret rooms: Yes/No
- Exact secret-room count
- Secret-room type(s)
- Artifact(s) generated on that floor
- Floors with no normal searchable equipment remain visible

The original Seed Seeker remains the base application and continues to run
fully client-side in the browser through WebAssembly.

## Publish it

This repository is designed to build itself in GitHub Actions.

1. Put these files in a new GitHub repository.
2. In **Settings → Pages**, select **GitHub Actions** as the source.
3. Open **Actions → Build and publish Seed Seeker Plus → Run workflow**.
4. When it completes, GitHub gives you a URL similar to:

   `https://YOURNAME.github.io/YOUR-REPOSITORY/`

Open that URL on Android/iPhone just like the original `web.app` site.

## How the build works

The GitHub runner:

1. downloads the current upstream Seed Seeker;
2. applies `patches/secret-rooms-artifacts.patch`;
3. compiles the Rust generator to WebAssembly;
4. builds the React/Vite site;
5. publishes the finished static browser app to GitHub Pages.

You therefore do **not** need Rust, Node, npm or a server on your phone or PC.

## Upstream

Seed Seeker:
https://github.com/akhial/shpd-seed-seeker

The upstream project is GPL-3.0. Its licensing and Shattered Pixel Dungeon
attribution files remain part of the built upstream source.
