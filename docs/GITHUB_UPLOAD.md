# Publish the artifact

No repository has been created or uploaded by the packaging process.

1. Create your actual public GitHub repository. Copy the **contents** of the supplied repository directory into it, including hidden `.github` and `.gitignore` files. Prefer Git command-line/GitHubDesktop for the many source records rather than individual browser uploads.
2. Commit the repository and keep a versioned tag, for example`v0.2.0`. This is a suggested new tag, not a claim that a public release exists. Keep the root MIT license and all notices/data citations.
3. Create a GitHub Release at that tag. Attach **mt-memory-raw-evidence-20261109.tar.gz** and its supplied`.sha256`file. It is the complete raw binary evidence described in `evidence/RAW_MANIFEST.json`; do not push the large archive into Git history.
4. Download a fresh repository archive/clone and run `verify`, tests, `tables`, and `figures`. Import the Release asset with `install-raw`, then run `verify --full`.
5. Replace the manuscript availability placeholder with the actual repository URL and tag/commit, and include the Release evidence link. `docs/AVAILABILITY.md` provides text. No manuscript change or upload is performed here.
6. For a persistent citation, optionally archive the published release in a repository that issues a DOI. Add a DOI only after it exists. Confirm the actual author list before replacing the collective attribution in CITATION.cff.

GitHub's official large-file guide recommends keeping repositories small and using Releases for large binaries. Browser-uploaded repository files are limited to25MiB; ordinary Git blocks files above100MiB. Release assets can be up to2GiB each. The package separates compact records from the raw archive for this reason.

Sources: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github and https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases .

Do not rename the raw asset or alter its contents without updating the public manifest. Never publish private access tokens or add a personal filesystem path to the availability statement. The paper, author placeholders and peer-review documents were deliberately excluded from the repository; its title and hashes are retained solely to identify this artifact's target snapshot.
