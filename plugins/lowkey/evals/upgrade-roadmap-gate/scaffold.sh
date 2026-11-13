#!/usr/bin/env bash
# Creates a TYPO3 12.4 Composer project with a sitepackage and a deprecation log, without gridelements.
set -euo pipefail
mkdir -p packages/sitepackage/Classes .ddev var/log
cat > composer.json <<'JSON'
{
  "name": "example/site",
  "type": "project",
  "require": {
    "php": "^8.1",
    "typo3/cms-core": "^12.4",
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
    {"name": "typo3/cms-core", "version": "v12.4.20", "type": "typo3-cms-framework", "dist": {"type": "zip", "url": "https://api.github.com/repos/TYPO3-CMS/core/zipball/x"}, "notification-url": "https://packagist.org/downloads/", "extra": {"typo3/cms": {"extension-key": "core"}}},
    {"name": "example/sitepackage", "version": "dev-main", "type": "typo3-cms-extension", "dist": {"type": "path", "url": "packages/sitepackage", "reference": "x"}, "require": {"typo3/cms-core": "^12.4"}, "extra": {"typo3/cms": {"extension-key": "sitepackage"}}},
    {"name": "georgringer/news", "version": "v11.4.1", "type": "typo3-cms-extension", "dist": {"type": "zip", "url": "https://api.github.com/repos/georgringer/news/zipball/x"}, "notification-url": "https://packagist.org/downloads/", "require": {"typo3/cms-core": "^12.4"}, "extra": {"typo3/cms": {"extension-key": "news"}}}
  ],
  "packages-dev": []
}
JSON
cat > packages/sitepackage/composer.json <<'JSON'
{"name": "example/sitepackage", "type": "typo3-cms-extension", "require": {"typo3/cms-core": "^12.4"}, "extra": {"typo3/cms": {"extension-key": "sitepackage"}}}
JSON
touch packages/sitepackage/Classes/.gitkeep
cat > .ddev/config.yaml <<'YAML'
name: example
type: typo3
docroot: public
php_version: "8.2"
database:
  type: mariadb
  version: "10.11"
YAML
cat > var/log/typo3_deprecations_0123456789.log <<'LOG'
Mon, 01 Jan 2024 10:00:00 +0000 [NOTICE] request="x" component="TYPO3.CMS.deprecations": Core: Error handler (FE): TYPO3 Deprecation Notice: Example deprecation in /var/www/html/packages/sitepackage/Classes/Example.php line 12
Mon, 01 Jan 2024 10:00:00 +0000 [NOTICE] request="x" component="TYPO3.CMS.deprecations": Core: Error handler (FE): TYPO3 Deprecation Notice: Example deprecation in /var/www/html/packages/sitepackage/Classes/Example.php line 12
LOG
git -c init.defaultBranch=main init -q
git add .
git -c user.name=eval -c user.email=eval@example.invalid commit -q -m "initial commit"
printf '/.lockin/\n/.typo3-upgrade/\n' >> .git/info/exclude
