# Evaluation results (generated)

Generated 2026-09-25 by `python -m evaluation.cli` from 8 repositories. Do not edit; interpretation lives in EVALUATION.md.

### 1. Dataset and pipeline validity

| repo | commits | span (years) | files | committer identities | bot identities | bot commit share | issues | PRs | reviews | validation |
|---|---|---|---|---|---|---|---|---|---|---|
| flask | 5,557 | 2010–2026 | 642 | 873 | 3 | 3% | 2,767 | 2,910 | 840 | OK |
| requests | 6,495 | 2011–2026 | 466 | 803 | 1 | 1% | 4,183 | 3,095 | 1,953 | OK |
| fastapi | 7,713 | 2018–2026 | 5,449 | 918 | 6 | 44% | 3,553 | 6,359 | 8,643 | OK |
| ripgrep | 2,287 | 2016–2026 | 467 | 497 | 1 | 0% | 1,828 | 1,167 | 920 | OK |
| black | 2,346 | 2018–2026 | 939 | 582 | 3 | 9% | 2,822 | 2,469 | 3,948 | OK |
| express | 6,170 | 2009–2026 | 905 | 394 | 1 | 1% | 4,072 | 2,666 | 2,204 | OK |
| cobra | 1,106 | 2013–2026 | 134 | 345 | 1 | 3% | 1,259 | 1,217 | 1,731 | OK |
| ora | 198 | 2016–2026 | 24 | 57 | 0 | 0% | 155 | 100 | 91 | OK |

### 2. Identity resolution and Git↔GitHub linkage

| repo | human commits with GitHub-login-linked identity | top-10 committers linked to a GitHub login | PRs linked to file changes | reviews linked to file changes | merge commits | commits with no file list |
|---|---|---|---|---|---|---|
| flask | 2% | 0/10 | 48% | 51% | 31% | 0% |
| requests | 3% | 1/10 | 45% | 44% | 25% | 1% |
| fastapi | 14% | 4/10 | 0% | 0% | 0% | 0% |
| ripgrep | 4% | 2/10 | 5% | 3% | 3% | 0% |
| black | 25% | 5/10 | 0% | 0% | 0% | 0% |
| express | 1% | 0/10 | 10% | 15% | 8% | 0% |
| cobra | 10% | 1/10 | 10% | 0% | 10% | 0% |
| ora | 4% | 1/10 | 0% | 0% | 0% | 0% |

### 3. Concentration metric behaviour (files with >= 5 commits ranked; components = depth 2)

| repo | ranked files | median effective contributors (files) | files with top share >= 80% | ρ commits vs recency | ρ commits vs multi-signal | ranked components | components with top share >= 80% |
|---|---|---|---|---|---|---|---|
| flask | 452 | 2.4 | 28% | 0.66 | 0.91 | 39 | 36% |
| requests | 304 | 3.1 | 9% | 0.53 | 0.89 | 25 | 8% |
| fastapi | 1,697 | 2.0 | 29% | 0.80 | 0.87 | 128 | 33% |
| ripgrep | 191 | 1.4 | 58% | 0.93 | 0.88 | 50 | 62% |
| black | 214 | 5.0 | 6% | 0.76 | 0.90 | 25 | 0% |
| express | 492 | 1.8 | 44% | 0.73 | 0.94 | 75 | 43% |
| cobra | 88 | 5.0 | 2% | 0.64 | 0.88 | 9 | 0% |
| ora | 9 | 3.3 | 22% | 0.50 | 0.85 | 3 | 67% |

### 4. Sensitivity of file-level concentration rankings (Spearman ρ; 1.00 = identical ordering)

| repo | half-life 90d vs 365d | 365d vs 1095d | with vs without bots | files whose top committer changes when bots included | conservative vs name-merged identities | identities merged away |
|---|---|---|---|---|---|---|
| flask | 0.81 | 0.87 | 1.00 | 0/452 | 1.00 | 136 |
| requests | 0.61 | 0.69 | 0.99 | 3/304 | 0.99 | 101 |
| fastapi | 0.79 | 0.92 | 0.96 | 14/1697 | 1.00 | 26 |
| ripgrep | 0.92 | 0.97 | 1.00 | 0/191 | 1.00 | 17 |
| black | 0.75 | 0.85 | 0.97 | 16/214 | 0.99 | 16 |
| express | 0.85 | 0.88 | 1.00 | 2/492 | 1.00 | 39 |
| cobra | 0.56 | 0.81 | 1.00 | 4/88 | 0.98 | 19 |
| ora | 0.28 | 0.82 | 1.00 | 0/9 | 1.00 | 0 |

### 5. Risk signals (components, depth 2, 365-day active window) and threshold stability

| repo | high | medium | low | dormant | insufficient | level agreement at 180d | level agreement at 730d |
|---|---|---|---|---|---|---|---|
| flask | 5 | 6 | 0 | 28 | 6 | 91% | 100% |
| requests | 7 | 5 | 0 | 13 | 5 | 100% | 58% |
| fastapi | 8 | 88 | 18 | 14 | 26 | 13% | 82% |
| ripgrep | 1 | 12 | 2 | 35 | 13 | 40% | 80% |
| black | 2 | 15 | 3 | 5 | 4 | 50% | 85% |
| express | 6 | 4 | 0 | 65 | 9 | 50% | 70% |
| cobra | 1 | 3 | 0 | 5 | 1 | 50% | 50% |
| ora | 0 | 2 | 0 | 1 | 0 | 100% | 100% |

Selection rationale per repo:

- **flask**: baseline; Python; two long-time maintainers, hundreds of one-off contributors
- **requests**: Python; mature project, few active maintainers
- **fastapi**: Python; one dominant maintainer, heavy bot and one-off contributor activity
- **ripgrep**: Rust; essentially one maintainer, many direct pushes, fewer PRs
- **black**: Python; community governance, bot-heavy
- **express**: JavaScript; large team, long history
- **cobra**: Go; small, community-maintained
- **ora**: JavaScript; tiny single-maintainer library
