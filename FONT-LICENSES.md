# Atlas font and typography licenses

## Atlas typography policy

Atlas does not bundle, extract, redistribute, or modify any font file from Ubisoft or Assassin's Creed products.

The names `Atlas Kage Display` and `Atlas UI Sans` are CSS family aliases used by the site. They are not bundled proprietary typefaces. The browser resolves them from locally installed fonts and then falls back to the listed open/system families.

## Display stack

Preferred local families:

- Source Han Serif SC
- Noto Serif CJK SC / Noto Serif SC
- Songti SC / STSong system fallbacks

Source Han Serif and Noto CJK releases are distributed under the SIL Open Font License 1.1 by their respective maintainers. No font binaries are stored in this repository as part of Alpha 0.9.3.0.

## Interface stack

Preferred local families:

- Source Han Sans SC
- Noto Sans CJK SC / Noto Sans SC
- PingFang SC, Microsoft YaHei UI, and other platform fallbacks

Source Han Sans and Noto CJK releases are distributed under the SIL Open Font License 1.1 by their respective maintainers. Platform fonts are used through normal CSS local/system fallback and are not redistributed.

## Original Atlas treatment

The Atlas visual treatment consists of independently authored CSS typography rules, including hierarchy, spacing, weight, optical sizing, condensed presentation, tabular-number styling, and restrained title accents. It is inspired by broad Sengoku-era print, carved inscription, and high-contrast serif design language rather than copied game-logo outlines.

## Trademark notice

Assassin's Creed, Ubisoft, and related names and marks belong to their respective owners. Atlas is an unofficial fan-made project and is not affiliated with or endorsed by Ubisoft.

## Future bundled font files

Before any font binary is added later, the repository must record:

1. source URL and upstream project;
2. copyright holder;
3. exact license text;
4. whether a Reserved Font Name applies;
5. modifications and new family name;
6. web-embedding and redistribution permission;
7. generated subset ranges and build process.

Validation: Alpha 0.9.3.0 typography policy and runtime asset checks.
