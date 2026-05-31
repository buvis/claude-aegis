# Coding Style

Two hooks enforce sections of this rule file: `block_suppression_markers.py` (Warnings) and `protect_config.py` (Linter Configs).

## Warnings section

NEVER silence warnings with suppression markers. Fix the root cause.

The hook blocks any Edit/Write/MultiEdit that newly adds a suppression marker. It recognises common forms across Rust, Python (lint, type-checker, and security suppressions), JavaScript, TypeScript, Java, Go, and C/C++. The canonical, version-tracked list of detected patterns lives in `hooks/block_suppression_markers.py` (see `SUPPRESSION_PATTERNS`). Add new languages there, not here.

If you discover pre-existing suppression markers, surface them and push for action. Do not extend them silently.

## Linter Configs section

Editing linter or formatter config files to weaken rules is denied. Fix the source code instead.

The hook blocks Edit/Write/MultiEdit on a fixed list of well-known linter and formatter config filenames covering ESLint, Prettier, Biome, Ruff, Stylelint, Markdownlint, Clippy, SwiftLint, and ShellCheck. The canonical list lives in `hooks/protect_config.py` (see `PROTECTED_BASENAMES`).

To intentionally change linter policy, do so outside an agent session. The block is here to prevent the model from quietly relaxing rules to make warnings go away.
