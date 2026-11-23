#!/usr/bin/env bash
# Creates a TYPO3 9.5 Composer project with a sitepackage and one public extension.
set -euo pipefail
mkdir -p packages/sitepackage/Classes .ddev
cat > composer.json <<'JSON'
{
  "name": "example/site",
  "type": "project",
  "require": {
    "php": "^7.4",
    "typo3/cms-core": "^9.5",
    "example/sitepackage": "@dev"
  },
  "repositories": [
    {"type": "path", "url": "packages/*"}
  ],
  "extra": {"typo3/cms": {"web-dir": "public"}}
}
JSON
cat > composer.lock <<'JSON'
{
  "packages": [
    {"name": "typo3/cms-core", "version": "v9.5.31", "type": "typo3-cms-framework", "dist": {"type": "zip", "url": "https://api.github.com/repos/TYPO3-CMS/core/zipball/x"}, "notification-url": "https://packagist.org/downloads/", "extra": {"typo3/cms": {"extension-key": "core"}}},
    {"name": "example/sitepackage", "version": "dev-main", "type": "typo3-cms-extension", "dist": {"type": "path", "url": "packages/sitepackage", "reference": "x"}, "require": {"typo3/cms-core": "^9.5"}, "extra": {"typo3/cms": {"extension-key": "sitepackage"}}},
    {"name": "georgringer/news", "version": "v8.0.0", "type": "typo3-cms-extension", "dist": {"type": "zip", "url": "https://api.github.com/repos/georgringer/news/zipball/x"}, "notification-url": "https://packagist.org/downloads/", "require": {"typo3/cms-core": "^9.5 || ^10.4"}, "extra": {"typo3/cms": {"extension-key": "news"}}}
  ],
  "packages-dev": []
}
JSON
cat > packages/sitepackage/composer.json <<'JSON'
{"name": "example/sitepackage", "type": "typo3-cms-extension", "require": {"typo3/cms-core": "^9.5"}, "extra": {"typo3/cms": {"extension-key": "sitepackage"}}}
JSON
touch packages/sitepackage/Classes/.gitkeep
cat > .ddev/config.yaml <<'YAML'
name: example
type: typo3
docroot: public
php_version: "7.4"
database:
  type: mariadb
  version: "10.4"
YAML
git -c init.defaultBranch=main init -q
git add .
git -c user.name=eval -c user.email=eval@example.invalid commit -q -m "initial commit"
printf '/.lockin/\n/.typo3-upgrade/\n' >> .git/info/exclude
