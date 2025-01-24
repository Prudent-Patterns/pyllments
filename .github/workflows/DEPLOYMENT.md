# Tags

-   v\*: Trigger the docs-publish and pypi-publish workflows which, respectively, build the documentation and publish it to the gh-pages branch, and build+publish the package to pypi.

-   docs\*: Trigger the docs-publish workflow which builds the documentation and publishes it to the gh-pages branch. --- To be used when needing to ONLY update the documentation.

# Versioning

hatch-vcs, which uses setuptools-scm handles version incrementation by analyzing versions in commits. Primarily useful for dynamic version generation for the build and publishing workflows.

When version isn't tagged, commits of the last version that has the pattern 0.0.1 will increment the minor patch field 0.0.2 and add a dev suffix with hash values to show the distance of commits it is from the 0.0.1 0.0.2dev{some_hash}.

Do not self-appoint dev suffix. If you do, use dev0. (read setuptools-scm documentation first!)