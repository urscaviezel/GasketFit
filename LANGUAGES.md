# Language files

English, German and French are bundled and available offline from the first
launch, including the Windows installer. The initial language follows the first
preferred operating-system UI language. Unsupported or unavailable detection
falls back to English. An explicitly saved selection takes precedence on updates.

UTF-8 JSON, maximum 1 MB. Example:

```json
{
  "schema": 1,
  "code": "fr",
  "name": "Fran?ais",
  "messages": {
    "Projekt ?ffnen": "Ouvrir le projet",
    "Neue Version: {v0}": "Nouvelle version : {v0}"
  }
}
```

The existing `lang/en.json` is the complete template; keys are stable German source messages and values are translations. Copy it, change `code` and `name`, then translate values. Keep every `{v0}` / `{v1:.2f}` placeholder and its formatting, line breaks and simple HTML structure. No scripts, remote images or links are accepted. Missing messages fall back to English. Partial files are supported.

Use a filename matching the code, e.g. `fr.json`, `pt-BR.json`. Place it in the portable app's `lang` folder or import through Settings. Files are monitored live. Additional languages can be deleted in Settings. EN/DE/FR remain available through their bundled copies. UI changes do not change the language of reports already saved on disk.

For future GitHub discovery, commit files into the repository's top-level `lang` directory on its default branch. The app lists JSON files through GitHub's contents API and downloads the selected immutable Git blob, verifies its blob hash and validates JSON before saving. Files are never executed. The app never pushes repository changes.
